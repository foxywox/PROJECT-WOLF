"""`wolf serve`: WOLF's web app (phone and desktop, with voice).

Standard library only. Serves the single-page app from `wolf/web/` and a small JSON API.
Every API call needs the access token kept in `$WOLF_HOME/web_token`; the static page
itself contains no personal data.

API (all require `Authorization: Bearer <token>`):
  POST   /api/chat            {"conversation_id"?, "message"} -> text/event-stream
                              events: start {conversation_id}, text {text}, tool {name},
                                      done {}, error {message}
  POST   /api/end             {"conversation_id"} -> {"summary"}   (reflect + journal)
  GET    /api/memory?q=...    -> {"memories": [...]}
  DELETE /api/memory/<id>     -> {"forgot": id}
  GET    /api/profile         -> {"profile": markdown}
  GET    /api/journal         -> {"journal": [lines]}
  GET    /api/components      -> {"components": [{name, description, enabled}]}
  POST   /api/components      {"name", "enabled": bool} -> same as GET (next conversation uses it)
  GET    /api/personality     -> {"current", "presets": [{id, name, summary}], "custom"}
  POST   /api/personality     {"id", "custom"?} -> same as GET (next conversation uses it)
  GET    /api/calendar        -> {"calendars": [{name, source}], "events": [...next 7 days], "how_to"}
  POST   /api/calendar        {"name", "url"} -> checks the link, saves it, turns the calendar on
  DELETE /api/calendar/<name> -> removes that calendar
  GET    /api/reminders       -> {"due": [...], "open": [...]}
  POST   /api/reminders       {"text", "due"} -> adds one;  POST /api/reminders/<id>/done
  GET    /api/hub             -> {"available", "progress", "plan", "threads"}   (project page)
  GET    /api/hub/forum/<id>  -> one forum thread with all posts
  POST   /api/hub/forum       {"title", "body", "author", "topic"?} -> new thread (posted as human)
  POST   /api/hub/forum/<id>  {"body", "author"} -> thread with the reply added (posted as human)
"""

from __future__ import annotations

import hmac
import json
import mimetypes
import os
import secrets
import signal
import socket
import ssl
import threading
import time
import uuid
from datetime import datetime, timedelta
from dataclasses import asdict, dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

from .assistant import build_wolf, finish_conversation, now_stamp
from . import hub, personality
from .components import available, calendar, enabled_names, reminders
from .config import NOT_SET_UP, load_config, save_config
from .loop import AgentLoop
from .memory import MemoryStore

WEB_DIR = Path(__file__).parent / "web"
IDLE_SECONDS = 20 * 60  # conversations idle this long are reflected on and closed
MAX_MESSAGE_CHARS = 20_000
STATIC = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/style.css": "style.css",
          "/manifest.webmanifest": "manifest.webmanifest", "/icon.svg": "icon.svg", "/sw.js": "sw.js"}


def load_token(store: MemoryStore) -> str:
    """The access token for the web app: $WOLF_TOKEN if set (hosted deployments), otherwise a
    random token generated once and kept in $WOLF_HOME/web_token (owner-only)."""
    env = os.environ.get("WOLF_TOKEN", "").strip()
    if env:
        if len(env) < 16:
            raise SystemExit("WOLF_TOKEN must be at least 16 characters.")
        return env
    path = store.home / "web_token"
    if path.exists() and path.read_text().strip():
        return path.read_text().strip()
    token = secrets.token_urlsafe(24)
    path.write_text(token)
    path.chmod(0o600)
    return token


@dataclass
class Conversation:
    agent: AgentLoop
    last_active: float = field(default_factory=time.time)
    started: bool = False


class WolfApp:
    """Holds conversations and memory; independent of HTTP so it can be tested directly."""

    def __init__(self, store: MemoryStore, agent_factory: Callable[[], AgentLoop] | None = None,
                 idle_seconds: int = IDLE_SECONDS):
        self.store = store
        self.agent_factory = agent_factory or (lambda: build_wolf(store, effort="medium"))
        self.idle_seconds = idle_seconds
        self.conversations: dict[str, Conversation] = {}
        # One person, one WOLF: serialize model turns so memory files never race.
        self.lock = threading.Lock()

    def open(self, conversation_id: str | None) -> str:
        """Return the id of an existing conversation, or start a new one."""
        with self.lock:
            if conversation_id and conversation_id in self.conversations:
                return conversation_id
            conv_id = uuid.uuid4().hex
            self.conversations[conv_id] = Conversation(self.agent_factory())
            return conv_id

    def chat(self, conversation_id: str, message: str,
             on_text: Callable[[str], None], on_tool: Callable[[str], None]) -> str:
        with self.lock:
            conv = self.conversations.get(conversation_id)
            if conv is None:
                raise KeyError("This conversation has ended. Start a new one.")
            agent = conv.agent
            agent.out = on_text
            agent.on_tool = lambda name, _args: on_tool(name)
            prompt = message if conv.started else now_stamp() + message
            conv.started = True
            try:
                return agent.ask(prompt)
            finally:
                conv.last_active = time.time()

    def components(self) -> dict[str, Any]:
        enabled = enabled_names(load_config(self.store.home))
        return {"components": [{"name": n, "description": d, "enabled": n in enabled}
                               for n, d in available(self.store.home).items()]}

    def set_component(self, name: str, enabled: bool) -> dict[str, Any]:
        """Turn an ability on or off. Conversations started after this use the new set."""
        if name not in available(self.store.home):
            raise ValueError(f"No ability named '{name}'")
        config = load_config(self.store.home)
        names = enabled_names(config)
        if enabled and name not in names:
            names.append(name)
        if not enabled and name in names:
            names.remove(name)
        config["components"] = names
        save_config(config, self.store.home)
        return self.components()

    def wallpaper_summary(self) -> dict[str, Any]:
        """What the desktop wallpaper shows about the owner's own WOLF (read-only)."""
        from . import __version__

        home = self.store.home
        mems = self.store.recent(1)
        journal = []
        for line in self.store.recent_journal(6):
            parts = line[2:].split(": ", 1)
            if len(parts) == 2:
                journal.append({"time": parts[0].replace(" ", "T"), "text": parts[1]})
        rem = reminders.load(home)
        open_rem = sorted((r for r in rem if not r.get("done")), key=lambda r: r["due"])
        system = None
        try:
            import psutil

            disk_root = str(Path(home).anchor or "/")
            system = {"cpu": psutil.cpu_percent(interval=None), "ram": psutil.virtual_memory().percent,
                      "disk": psutil.disk_usage(disk_root).percent}
        except Exception:
            pass
        return {
            "version": __version__,
            "memories": len(self.store.all()),
            "latest_memory": {"text": mems[0].text, "time": mems[0].updated} if mems else None,
            "journal": journal,
            "reminders_due": len(reminders.due(home)),
            "next_reminder": open_rem[0] if open_rem else None,
            "abilities": self.components()["components"],
            "personality": personality.current(home),
            "conversations_open": len(self.conversations),
            "system": system,
        }

    def calendar_overview(self) -> dict[str, Any]:
        home = self.store.home
        out: dict[str, Any] = {"calendars": calendar.public_list(home), "events": [], "how_to": calendar.HOW_TO}
        if out["calendars"]:
            start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            try:
                evs = calendar.events(home, start, start + timedelta(days=7))
                out["events"] = [{**e, "start": e["start"].isoformat(), "end": e["end"].isoformat() if e["end"] else None}
                                 for e in evs[:20]]
            except calendar.CalendarError as e:
                out["error"] = str(e)
        return out

    def reminders_overview(self) -> dict[str, Any]:
        home = self.store.home
        return {"due": reminders.due(home),
                "open": sorted((r for r in reminders.load(home) if not r.get("done")), key=lambda r: r["due"])}

    def hub_overview(self) -> dict[str, Any]:
        if hub.hub_dir() is None:
            return {"available": False}
        return {"available": True, "progress": hub.progress(), "plan": hub.plan(), "threads": hub.threads()}

    def end(self, conversation_id: str) -> str:
        with self.lock:
            conv = self.conversations.pop(conversation_id, None)
            return finish_conversation(conv.agent) if conv else ""

    def sweep(self, now: float | None = None) -> int:
        """Reflect on and close idle conversations. Returns how many were closed."""
        now = now or time.time()
        stale = [cid for cid, c in list(self.conversations.items()) if now - c.last_active > self.idle_seconds]
        for cid in stale:
            try:
                self.end(cid)
            except Exception:  # an API error must not kill the sweeper
                self.conversations.pop(cid, None)
        return len(stale)

    def end_all(self) -> None:
        for cid in list(self.conversations):
            try:
                self.end(cid)
            except Exception:
                pass


def make_handler(app: WolfApp, token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "WOLF"

        def log_message(self, fmt, *args):  # keep the terminal quiet; no message content in logs
            pass

        # ---------- helpers ----------
        def _json(self, status: int, payload: Any) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _authed(self) -> bool:
            got = self.headers.get("Authorization", "")
            if got.startswith("Bearer ") and hmac.compare_digest(got[7:].encode(), token.encode()):
                return True
            self._json(401, {"error": "Missing or wrong access token. Open the link `wolf serve` printed."})
            return False

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 1_000_000:
                raise ValueError("Request too large")
            data = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
            return data

        # ---------- routes ----------
        def do_GET(self):
            url = urlparse(self.path)
            if url.path in STATIC:
                return self._static(STATIC[url.path])
            if url.path == "/api/wallpaper":
                return self._wallpaper(url)
            if not url.path.startswith("/api/") or not self._authed():
                return None if url.path.startswith("/api/") else self._json(404, {"error": "Not found"})
            if url.path == "/api/memory":
                q = parse_qs(url.query).get("q", [""])[0].strip()
                mems = app.store.search(q, limit=500) if q else app.store.recent(10_000)
                return self._json(200, {"memories": [asdict(m) for m in mems]})
            if url.path == "/api/profile":
                return self._json(200, {"profile": app.store.profile()})
            if url.path == "/api/journal":
                return self._json(200, {"journal": app.store.recent_journal(50)})
            if url.path == "/api/components":
                return self._json(200, app.components())
            if url.path == "/api/personality":
                return self._json(200, personality.overview(app.store.home))
            if url.path == "/api/calendar":
                return self._json(200, app.calendar_overview())
            if url.path == "/api/reminders":
                return self._json(200, app.reminders_overview())
            if url.path == "/api/hub":
                return self._json(200, app.hub_overview())
            if url.path.startswith("/api/hub/forum/"):
                return self._hub_call(lambda: hub.thread(url.path.rsplit("/", 1)[-1]))
            return self._json(404, {"error": "Not found"})

        def do_DELETE(self):
            url = urlparse(self.path)
            if not self._authed():
                return
            if url.path.startswith("/api/calendar/"):
                try:
                    calendar.remove_calendar(app.store.home, unquote(url.path.split("/api/calendar/", 1)[1]))
                except calendar.CalendarError as e:
                    return self._json(404, {"error": str(e)})
                return self._json(200, app.calendar_overview())
            if url.path.startswith("/api/memory/"):
                mem_id = url.path.rsplit("/", 1)[-1]
                with app.lock:
                    try:
                        app.store.forget(mem_id)
                    except KeyError:
                        return self._json(404, {"error": f"No memory {mem_id}"})
                return self._json(200, {"forgot": mem_id})
            return self._json(404, {"error": "Not found"})

        def do_POST(self):
            url = urlparse(self.path)
            if not self._authed():
                return
            try:
                body = self._body()
            except (ValueError, json.JSONDecodeError) as e:
                return self._json(400, {"error": str(e)})
            if url.path == "/api/chat":
                return self._chat(body)
            if url.path == "/api/end":
                try:
                    return self._json(200, {"summary": app.end(str(body.get("conversation_id", "")))})
                except Exception as e:
                    return self._json(502, {"error": _friendly(e)})
            if url.path == "/api/components":
                try:
                    return self._json(200, app.set_component(str(body.get("name", "")), bool(body.get("enabled"))))
                except ValueError as e:
                    return self._json(400, {"error": str(e)})
            if url.path == "/api/personality":
                try:
                    personality.choose(app.store.home, str(body.get("id", "")),
                                       body.get("custom") if isinstance(body.get("custom"), str) else None)
                    return self._json(200, personality.overview(app.store.home))
                except ValueError as e:
                    return self._json(400, {"error": str(e)})
            if url.path == "/api/calendar":
                try:
                    count = calendar.add_calendar(app.store.home, str(body.get("name", "")), str(body.get("url", "")),
                                                  allow_files=False)
                except calendar.CalendarError as e:
                    return self._json(400, {"error": str(e)})
                app.set_component("calendar", True)
                return self._json(200, {**app.calendar_overview(), "added_events": count})
            if url.path == "/api/reminders":
                try:
                    reminders.add(app.store.home, str(body.get("text", "")), str(body.get("due", "")))
                except reminders.ReminderError as e:
                    return self._json(400, {"error": str(e)})
                return self._json(200, app.reminders_overview())
            if url.path.startswith("/api/reminders/") and url.path.endswith("/done"):
                try:
                    reminders.complete(app.store.home, url.path.split("/")[3])
                except reminders.ReminderError as e:
                    return self._json(404, {"error": str(e)})
                return self._json(200, app.reminders_overview())
            if url.path == "/api/hub/forum":
                return self._hub_call(lambda: hub.new_thread(
                    str(body.get("title", "")), str(body.get("body", "")),
                    str(body.get("author", "")), "human", str(body.get("topic") or "") or None))
            if url.path.startswith("/api/hub/forum/"):
                return self._hub_call(lambda: hub.reply(
                    url.path.rsplit("/", 1)[-1], str(body.get("body", "")), str(body.get("author", "")), "human"))
            return self._json(404, {"error": "Not found"})

        def _wallpaper(self, url):
            """Read-only summary for the desktop wallpaper. It runs from a local file, so it can't
            send headers: the key comes in the query string, and the reply allows any origin."""
            key = parse_qs(url.query).get("key", [""])[0]
            if not hmac.compare_digest(key.encode(), token.encode()):
                body, status = {"error": "Wrong WOLF key"}, 401
            else:
                body, status = app.wallpaper_summary(), 200
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)

        def _hub_call(self, fn):
            try:
                return self._json(200, fn())
            except hub.HubError as e:
                return self._json(404 if str(e).startswith("No thread") else 400, {"error": str(e)})

        def _chat(self, body: dict):
            message = str(body.get("message", "")).strip()
            if not message:
                return self._json(400, {"error": "Empty message"})
            if len(message) > MAX_MESSAGE_CHARS:
                return self._json(400, {"error": "Message too long"})
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            def send(event: str, data: dict) -> None:
                try:
                    self.wfile.write(f"event: {event}\ndata: {json.dumps(data)}\n\n".encode())
                    self.wfile.flush()
                except (OSError, ValueError):  # broken pipe, reset, or stream already closed
                    pass  # browser went away; keep the turn running so memory is still saved

            conv_id = app.open(body.get("conversation_id") or None)
            send("start", {"conversation_id": conv_id})
            try:
                app.chat(conv_id, message,
                         on_text=lambda t: send("text", {"text": t}),
                         on_tool=lambda name: send("tool", {"name": name}))
                send("done", {})
            except Exception as e:
                send("error", {"message": _friendly(e)})

        def _static(self, name: str):
            path = WEB_DIR / name
            data = path.read_bytes()
            ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
            if name.endswith(".webmanifest"):
                ctype = "application/manifest+json"
            self.send_response(200)
            self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") or "javascript" in ctype else ""))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(data)

    return Handler


def _friendly(e: Exception) -> str:
    import anthropic

    if isinstance(e, anthropic.AuthenticationError):
        return "Claude rejected WOLF's API key. Run `wolf setup` on the computer running WOLF, then restart `wolf serve`."
    if isinstance(e, TypeError) and "authentication" in str(e).lower():
        return NOT_SET_UP
    if isinstance(e, anthropic.RateLimitError):
        return "Claude is rate-limiting requests right now. Try again in a minute."
    if isinstance(e, anthropic.APIStatusError):
        return f"Claude API error {e.status_code}: {e.message}"
    if isinstance(e, anthropic.APIConnectionError):
        return "Couldn't connect to Claude. Check your internet connection."
    return f"{type(e).__name__}: {e}"


def lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return None


def serve(store: MemoryStore, host: str = "127.0.0.1", port: int = 8765,
          certfile: str | None = None, keyfile: str | None = None, open_browser: bool = False) -> None:
    app = WolfApp(store)
    token = load_token(store)
    httpd = ThreadingHTTPServer((host, port), make_handler(app, token))
    scheme = "http"
    if certfile:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile, keyfile)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        scheme = "https"

    stop = threading.Event()

    def sweeper():
        while not stop.wait(60):
            app.sweep()

    threading.Thread(target=sweeper, daemon=True).start()

    # Hosts and `docker stop` send SIGTERM: treat it like Ctrl+C so open conversations are saved.
    def _terminate(*_a):
        raise KeyboardInterrupt

    try:
        signal.signal(signal.SIGTERM, _terminate)
    except ValueError:  # not in the main thread (e.g. tests)
        pass

    shown_host = "localhost" if host in ("127.0.0.1", "localhost") else host
    public_url = os.environ.get("WOLF_PUBLIC_URL", "").rstrip("/")
    print("WOLF is running. Open this link (it contains your private access token):\n")
    if public_url:
        print(f"  {public_url}/?token={token}")
    elif host in ("0.0.0.0", "::"):
        ip = lan_ip()
        print(f"  this computer:  {scheme}://localhost:{port}/?token={token}")
        if ip:
            print(f"  your phone:     {scheme}://{ip}:{port}/?token={token}   (same Wi-Fi)")
    else:
        print(f"  {scheme}://{shown_host}:{port}/?token={token}")
    print(f"\nDesktop wallpaper: paste this into its 'WOLF key' setting to show your memories and system:\n  {token}")
    print("\nPress Ctrl+C to stop. Open conversations are saved to memory when you stop.")
    if open_browser:
        import webbrowser

        threading.Timer(0.8, webbrowser.open, args=(f"{scheme}://localhost:{port}/?token={token}",)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nSaving open conversations...", flush=True)
    finally:
        stop.set()
        httpd.server_close()
        app.end_all()
