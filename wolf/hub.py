"""The project hub: WOLF's production plan, its research forum, and build progress.

Everything lives as plain files in the `hub/` folder of the WOLF project, so people (through
WOLF's Project tab) and AI (Claude sessions, `wolf-dev`, or WOLF itself through the `research`
component) read and write exactly the same thing:

  hub/plan.json            the production plan: phases -> items, each with a status
  hub/forum/<id>.json      one file per forum thread: {id, title, topic, created, posts[]}
  hub/progress.json        the current build's progress (the wolf pup tracker)

The project is public: anything written here is published when it's committed.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATUSES = ["done", "active", "next", "later", "idea"]
KINDS = ["human", "ai"]
MAX_TITLE = 140
MAX_BODY = 8000
MAX_AUTHOR = 60

_lock = threading.Lock()


class HubError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hub_dir() -> Path | None:
    """$WOLF_HUB, else the `hub/` folder next to the `wolf` package (a project checkout)."""
    env = os.environ.get("WOLF_HUB")
    if env:
        return Path(env).expanduser()
    candidate = Path(__file__).resolve().parents[1] / "hub"
    return candidate if candidate.is_dir() else None


def _require(hub: Path | None) -> Path:
    hub = hub or hub_dir()
    if hub is None:
        raise HubError("The project hub isn't available here. Run WOLF from the project folder, "
                       "or set WOLF_HUB to the hub folder.")
    return hub


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")
    tmp.replace(path)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


# ---------------------------------------------------------------- plan

def plan(hub: Path | None = None) -> dict[str, Any]:
    data = _read_json(_require(hub) / "plan.json", {"title": "WOLF production plan", "phases": []})
    phases = data.get("phases") if isinstance(data.get("phases"), list) else []
    total = sum(len(p.get("items", [])) for p in phases)
    done = sum(1 for p in phases for i in p.get("items", []) if i.get("status") == "done")
    data["summary"] = {"items": total, "done": done, "percent": round(100 * done / total) if total else 0}
    return data


def set_item_status(item_id: str, status: str, note: str | None = None, hub: Path | None = None) -> dict:
    if status not in STATUSES:
        raise HubError(f"Status must be one of: {', '.join(STATUSES)}")
    path = _require(hub) / "plan.json"
    with _lock:
        data = _read_json(path, None)
        if not isinstance(data, dict):
            raise HubError("plan.json is missing or unreadable")
        for phase in data.get("phases", []):
            for item in phase.get("items", []):
                if item.get("id") == item_id:
                    item["status"] = status
                    if note is not None:
                        item["note"] = note.strip()
                    data["updated"] = _now()[:10]
                    _write_json(path, data)
                    return item
    raise HubError(f"No plan item with id '{item_id}'")


def plan_text(hub: Path | None = None) -> str:
    """The whole plan as readable text (for terminals and AI briefings)."""
    data = plan(hub)
    s = data["summary"]
    marks = {"done": "[x]", "active": "[>]", "next": "[ ]", "later": "[ ]", "idea": "[?]"}
    lines = [f"{data.get('title', 'Production plan')} ({s['done']}/{s['items']} done, {s['percent']}%)",
             f"Updated {data.get('updated', '?')}. Legend: [x] done  [>] in progress  [ ] planned  [?] idea", ""]
    for phase in data.get("phases", []):
        lines.append(f"## {phase.get('name')}  ({phase.get('status', '')})")
        if phase.get("goal"):
            lines.append(f"   {phase['goal']}")
        for item in phase.get("items", []):
            who = f"  [{item['who']}]" if item.get("who") else ""
            lines.append(f"   {marks.get(item.get('status'), '[ ]')} {item.get('title')}  ({item.get('id')}, "
                         f"{item.get('status')}){who}")
            if item.get("note"):
                lines.append(f"       {item['note']}")
        lines.append("")
    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------- forum

def _slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if len(slug) > 40:  # cut on a word boundary
        slug = slug[:41].rsplit("-", 1)[0]
    return slug or "thread"


def _post(author: str, kind: str, body: str) -> dict[str, str]:
    author, body = " ".join(str(author).split())[:MAX_AUTHOR], str(body).strip()
    if kind not in KINDS:
        raise HubError("Post kind must be 'human' or 'ai'")
    if not author:
        raise HubError("Every post needs an author name")
    if not body:
        raise HubError("The post is empty")
    if len(body) > MAX_BODY:
        raise HubError(f"Posts are limited to {MAX_BODY} characters")
    return {"author": author, "kind": kind, "body": body, "time": _now()}


def _thread_path(hub: Path, thread_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,80}", thread_id or ""):
        raise HubError("Bad thread id")
    return hub / "forum" / f"{thread_id}.json"


def threads(hub: Path | None = None) -> list[dict[str, Any]]:
    """Thread summaries, most recently active first."""
    hub = _require(hub)
    out = []
    for path in (hub / "forum").glob("*.json"):
        t = _read_json(path, None)
        if not isinstance(t, dict) or not t.get("posts"):
            continue
        last = t["posts"][-1]
        out.append({"id": t["id"], "title": t["title"], "topic": t.get("topic"), "created": t.get("created"),
                    "replies": len(t["posts"]) - 1, "last_time": last["time"], "last_author": last["author"],
                    "last_kind": last["kind"], "started_by": t["posts"][0]["author"],
                    "started_kind": t["posts"][0]["kind"], "preview": t["posts"][0]["body"][:200]})
    return sorted(out, key=lambda t: t["last_time"], reverse=True)


def thread(thread_id: str, hub: Path | None = None) -> dict[str, Any]:
    t = _read_json(_thread_path(_require(hub), thread_id), None)
    if not isinstance(t, dict):
        raise HubError(f"No thread '{thread_id}'")
    return t


def new_thread(title: str, body: str, author: str, kind: str, topic: str | None = None,
               hub: Path | None = None) -> dict[str, Any]:
    hub = _require(hub)
    title = " ".join(str(title).split())[:MAX_TITLE]
    if not title:
        raise HubError("The thread needs a title")
    first = _post(author, kind, body)
    with _lock:
        base = f"{first['time'][:10]}-{_slug(title)}"
        thread_id, n = base, 2
        while (hub / "forum" / f"{thread_id}.json").exists():
            thread_id, n = f"{base}-{n}", n + 1
        t = {"id": thread_id, "title": title, "topic": (topic or None), "created": first["time"], "posts": [first]}
        _write_json(hub / "forum" / f"{thread_id}.json", t)
    return t


def reply(thread_id: str, body: str, author: str, kind: str, hub: Path | None = None) -> dict[str, Any]:
    hub = _require(hub)
    post = _post(author, kind, body)
    path = _thread_path(hub, thread_id)
    with _lock:
        t = _read_json(path, None)
        if not isinstance(t, dict):
            raise HubError(f"No thread '{thread_id}'")
        t["posts"].append(post)
        _write_json(path, t)
    return t


def forum_text(limit: int = 5, hub: Path | None = None) -> str:
    """Recent threads with their latest posts, for AI briefings."""
    items = threads(hub)[:limit]
    if not items:
        return "(no forum threads yet)"
    out = []
    for s in items:
        t = thread(s["id"], hub)
        out.append(f"### {t['title']}  (id: {t['id']}{', topic: ' + t['topic'] if t.get('topic') else ''}, "
                   f"{len(t['posts'])} posts)")
        for p in t["posts"][-3:]:
            out.append(f"- {p['author']} ({p['kind']}, {p['time'][:16].replace('T', ' ')}): {p['body'][:600]}")
        out.append("")
    return "\n".join(out).rstrip()


# ---------------------------------------------------------------- progress

def progress(hub: Path | None = None) -> dict[str, Any] | None:
    data = _read_json(_require(hub) / "progress.json", None)
    return data if isinstance(data, dict) else None
