"""Tests for `wolf serve` against a real HTTP server with a fake Claude client."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace as NS

import pytest

from wolf.assistant import build_wolf
from wolf.memory import MemoryStore
from wolf.server import WolfApp, load_token, make_handler


class _FakeStream:
    def __init__(self, msg):
        self.msg = msg
        self.text_stream = [b.text for b in msg.content if b.type == "text"]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


class _ScriptedClient:
    """Each conversation turn: remember what the user said, then reply."""

    def __init__(self):
        self.n = 0
        self.beta = NS(messages=NS(stream=self._stream))

    def _stream(self, messages, **kwargs):
        self.n += 1
        last = messages[-1]["content"]
        if isinstance(last, str) and last.startswith("[WOLF end-of-conversation"):
            return _FakeStream(NS(stop_reason="end_turn", content=[NS(type="text", text="Chatted about Juno.")]))
        if isinstance(last, str):
            return _FakeStream(NS(stop_reason="tool_use", content=[
                NS(type="tool_use", id=f"t{self.n}", name="remember", input={"text": "Has a dog named Juno"})]))
        return _FakeStream(NS(stop_reason="end_turn", content=[NS(type="text", text="Got it, "),
                                                               NS(type="text", text="Juno!")]))


@pytest.fixture
def server(tmp_path):
    store = MemoryStore(tmp_path / "home")
    client = _ScriptedClient()
    app = WolfApp(store, agent_factory=lambda: build_wolf(store, client=client, out=lambda s: None))
    token = load_token(store)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app, token))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield NS(base=f"http://127.0.0.1:{httpd.server_address[1]}", token=token, app=app, store=store)
    httpd.shutdown()
    httpd.server_close()


def _req(srv, path, method="GET", body=None, token=True):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {srv.token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(srv.base + path, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, r.headers.get("Content-Type"), r.read().decode()


def _events(raw):
    out = []
    for chunk in raw.strip().split("\n\n"):
        ev = chunk.split("\n")[0].removeprefix("event: ")
        out.append((ev, json.loads(chunk.split("\n")[1].removeprefix("data: "))))
    return out


def test_static_app_is_public_but_api_needs_token(server):
    status, ctype, html = _req(server, "/", token=False)
    assert status == 200 and "text/html" in ctype and "WOLF" in html
    for path in ("/app.js", "/style.css", "/manifest.webmanifest", "/icon.svg", "/sw.js"):
        assert _req(server, path, token=False)[0] == 200
    with pytest.raises(urllib.error.HTTPError) as e:
        _req(server, "/api/memory", token=False)
    assert e.value.code == 401
    server.token = "wrong"
    with pytest.raises(urllib.error.HTTPError):
        _req(server, "/api/profile")


def test_token_file_is_private_and_stable(server):
    path = server.store.home / "web_token"
    assert oct(path.stat().st_mode)[-3:] == "600"
    assert load_token(server.store) == server.token


def test_chat_streams_learns_and_continues(server):
    _, ctype, raw = _req(server, "/api/chat", "POST", {"message": "I adopted a dog named Juno"})
    assert "text/event-stream" in ctype
    events = _events(raw)
    assert events[0][0] == "start"
    conv = events[0][1]["conversation_id"]
    assert ("tool", {"name": "remember"}) in events
    assert "".join(d["text"] for e, d in events if e == "text") == "Got it, Juno!"
    assert events[-1][0] == "done"
    assert server.store.search("dog")[0].text == "Has a dog named Juno"

    # same conversation continues; first message got the date stamp, later ones don't
    _, _, raw2 = _req(server, "/api/chat", "POST", {"conversation_id": conv, "message": "She's 2"})
    assert _events(raw2)[0][1]["conversation_id"] == conv
    agent = server.app.conversations[conv].agent
    user_texts = [m["content"] for m in agent.messages if m["role"] == "user" and isinstance(m["content"], str)]
    assert user_texts[0].startswith("[") and user_texts[1] == "She's 2"


def test_unknown_conversation_starts_new_one(server):
    _, _, raw = _req(server, "/api/chat", "POST", {"conversation_id": "gone", "message": "hi"})
    assert _events(raw)[0][1]["conversation_id"] != "gone"


def test_end_reflects_and_journals(server):
    _, _, raw = _req(server, "/api/chat", "POST", {"message": "Juno!"})
    conv = _events(raw)[0][1]["conversation_id"]
    _, _, body = _req(server, "/api/end", "POST", {"conversation_id": conv})
    assert json.loads(body)["summary"] == "Chatted about Juno."
    assert conv not in server.app.conversations
    _, _, j = _req(server, "/api/journal")
    assert "Chatted about Juno." in json.loads(j)["journal"][-1]


def test_idle_sweep_saves_conversation(server):
    _, _, raw = _req(server, "/api/chat", "POST", {"message": "Juno!"})
    conv = _events(raw)[0][1]["conversation_id"]
    assert server.app.sweep(now=server.app.conversations[conv].last_active + 10) == 0
    assert server.app.sweep(now=server.app.conversations[conv].last_active + 99_999) == 1
    assert "Chatted about Juno." in server.store.recent_journal()[-1]


def test_memory_profile_and_forget_endpoints(server):
    server.store.add("Likes jazz", ["music"])
    server.store.update_profile("Identity", "Name: Sam")
    mems = json.loads(_req(server, "/api/memory?q=music")[2])["memories"]
    assert mems[0]["text"] == "Likes jazz"
    assert "Name: Sam" in json.loads(_req(server, "/api/profile")[2])["profile"]
    assert json.loads(_req(server, "/api/memory/m1", "DELETE")[2]) == {"forgot": "m1"}
    with pytest.raises(urllib.error.HTTPError) as e:
        _req(server, "/api/memory/m1", "DELETE")
    assert e.value.code == 404


def test_bad_requests(server):
    for body in ({"message": "  "}, {"message": "x" * 30_000}):
        with pytest.raises(urllib.error.HTTPError) as e:
            _req(server, "/api/chat", "POST", body)
        assert e.value.code == 400
