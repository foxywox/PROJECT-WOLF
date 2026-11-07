"""Tests for the project hub: production plan, research forum, build progress (people + AI)."""

from __future__ import annotations

import json
import shutil
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from wolf import hub
from wolf.assistant import build_toolkit
from wolf.loop import ToolError
from wolf.memory import MemoryStore
from wolf.server import WolfApp, make_handler
from wolf_assistant import workspace
from wolf_assistant.cli import main as dev_main

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def hubdir(tmp_path, monkeypatch):
    """A copy of the real plan in a temp hub, so tests never touch the committed forum."""
    h = tmp_path / "hub"
    (h / "forum").mkdir(parents=True)
    shutil.copy(REPO / "hub" / "plan.json", h / "plan.json")
    (h / "progress.json").write_text(json.dumps({"title": "Test build", "percent": 40, "steps": []}))
    monkeypatch.setenv("WOLF_HUB", str(h))
    return h


def test_committed_plan_is_valid():
    data = hub.plan(REPO / "hub")
    ids = [i["id"] for p in data["phases"] for i in p["items"]]
    assert len(ids) == len(set(ids)), "plan item ids must be unique"
    for phase in data["phases"]:
        assert phase["status"] in hub.STATUSES
        for item in phase["items"]:
            assert item["status"] in hub.STATUSES and item["title"]
    assert data["summary"]["items"] == len(ids)


def test_plan_summary_and_status_updates(hubdir):
    plan = hub.plan()
    before = plan["summary"]["done"]
    todo = next(i for p in plan["phases"] for i in p["items"] if i["status"] != "done")
    item = hub.set_item_status(todo["id"], "active", "Starting on this")
    assert item["status"] == "active" and item["note"] == "Starting on this"
    assert hub.plan()["summary"]["done"] == before
    hub.set_item_status(todo["id"], "done")
    assert hub.plan()["summary"]["done"] == before + 1
    assert todo["title"] in hub.plan_text()
    with pytest.raises(hub.HubError):
        hub.set_item_status(todo["id"], "finished")
    with pytest.raises(hub.HubError):
        hub.set_item_status("nope", "done")


def test_forum_threads_and_replies(hubdir):
    t = hub.new_thread("Should memory use embeddings?", "Keyword search may not scale.", "Claude", "ai",
                       topic="semantic-memory")
    assert t["id"].endswith("should-memory-use-embeddings")
    hub.reply(t["id"], "Agreed, once we pass a few hundred memories.", "Sam", "human")
    again = hub.new_thread("Should memory use embeddings?", "Duplicate title", "Sam", "human")
    assert again["id"] != t["id"]
    rows = hub.threads()
    assert rows[0]["id"] in (t["id"], again["id"])
    full = hub.thread(t["id"])
    assert [p["kind"] for p in full["posts"]] == ["ai", "human"]
    assert "Agreed" in hub.forum_text()


@pytest.mark.parametrize("kwargs, message", [
    ({"title": "", "body": "x", "author": "a", "kind": "human"}, "needs a title"),
    ({"title": "t", "body": " ", "author": "a", "kind": "human"}, "empty"),
    ({"title": "t", "body": "x", "author": "", "kind": "human"}, "author"),
    ({"title": "t", "body": "x", "author": "a", "kind": "robot"}, "kind"),
    ({"title": "t", "body": "x" * 9000, "author": "a", "kind": "human"}, "limited"),
])
def test_forum_validation(hubdir, kwargs, message):
    with pytest.raises(hub.HubError, match=message):
        hub.new_thread(**kwargs)


def test_thread_ids_cannot_escape_the_forum(hubdir):
    for bad in ("../plan", "../../etc/passwd", "", "UPPER"):
        with pytest.raises(hub.HubError):
            hub.thread(bad)


def test_missing_hub_is_reported(monkeypatch, tmp_path):
    monkeypatch.delenv("WOLF_HUB", raising=False)
    monkeypatch.setattr(hub, "__file__", str(tmp_path / "pkg" / "wolf" / "hub.py"))
    assert hub.hub_dir() is None
    with pytest.raises(hub.HubError, match="isn't available"):
        hub.plan()


def test_research_component_lets_wolf_join_the_forum(hubdir, tmp_path):
    kit = build_toolkit(MemoryStore(tmp_path / "home"), ["research"])
    assert "Production plan" in kit.call("read_plan", {}) or "production plan" in kit.call("read_plan", {})
    out = kit.call("post_to_forum", {"title": "Hello from WOLF", "body": "I can read the plan now."})
    thread_id = out.split("(id ")[1].rstrip(").")
    kit.call("post_to_forum", {"thread_id": thread_id, "body": "Second thought."})
    posts = hub.thread(thread_id)["posts"]
    assert [p["author"] for p in posts] == ["WOLF", "WOLF"] and posts[0]["kind"] == "ai"
    assert "Hello from WOLF" in kit.call("list_forum", {})
    with pytest.raises(ToolError):
        kit.call("post_to_forum", {"body": "no title or thread"})


def test_wolf_dev_plan_and_forum_commands(hubdir, capsys):
    assert dev_main(["forum", "new", "Calendar service?", "Which calendar do you use?", "--topic", "calendar"]) == 0
    tid = hub.threads()[0]["id"]
    assert dev_main(["forum", "reply", tid, "Following up."]) == 0
    assert dev_main(["forum", "read", tid]) == 0
    assert dev_main(["plan", "set", "calendar", "next"]) == 0
    assert dev_main(["plan"]) == 0
    out = capsys.readouterr().out
    assert "Following up." in out and "Calendar component" in out
    assert all(p["author"] == "Claude" and p["kind"] == "ai" for p in hub.thread(tid)["posts"])
    assert dev_main(["forum", "read", "missing-thread"]) == 1


def test_briefing_includes_plan_and_forum():
    text = workspace.brief(REPO)
    assert "WOLF production plan" in text and "Welcome to the WOLF research forum" in text


# ---------- the app's Project tab API ----------

@pytest.fixture
def server(hubdir, tmp_path):
    store = MemoryStore(tmp_path / "home")
    app = WolfApp(store, agent_factory=lambda: None)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app, "tok-123"))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield NS(base=f"http://127.0.0.1:{httpd.server_address[1]}", store=store)
    httpd.shutdown()
    httpd.server_close()


def _req(srv, path, method="GET", body=None):
    req = urllib.request.Request(srv.base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer tok-123", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def test_project_tab_api(server):
    data = _req(server, "/api/hub")
    assert data["available"] and data["progress"]["title"] == "Test build"
    assert data["plan"]["summary"]["items"] > 20 and data["threads"] == []

    t = _req(server, "/api/hub/forum", "POST", {"title": "Idea", "body": "Dark mode toggle?", "author": "Sam", "topic": ""})
    assert t["posts"][0]["kind"] == "human" and t["topic"] is None
    t = _req(server, f"/api/hub/forum/{t['id']}", "POST", {"body": "Seconded", "author": "Alex", "kind": "ai"})
    assert [p["kind"] for p in t["posts"]] == ["human", "human"]  # the app can't post as AI
    assert _req(server, f"/api/hub/forum/{t['id']}")["title"] == "Idea"
    for path, body, code in [("/api/hub/forum", {"title": "", "body": "x", "author": "a"}, 400),
                             ("/api/hub/forum/does-not-exist", {"body": "x", "author": "a"}, 404)]:
        with pytest.raises(urllib.error.HTTPError) as e:
            _req(server, path, "POST", body)
        assert e.value.code == code


def test_abilities_api(server):
    comps = {c["name"]: c["enabled"] for c in _req(server, "/api/components")["components"]}
    assert comps == {"memory": True, "web_search": True, "clock": True, "reminders": True,
                     "research": False, "calendar": False}
    after = {c["name"]: c["enabled"] for c in
             _req(server, "/api/components", "POST", {"name": "research", "enabled": True})["components"]}
    assert after["research"] is True
    after = {c["name"]: c["enabled"] for c in
             _req(server, "/api/components", "POST", {"name": "web_search", "enabled": False})["components"]}
    assert after["web_search"] is False
    with pytest.raises(urllib.error.HTTPError) as e:
        _req(server, "/api/components", "POST", {"name": "nope", "enabled": True})
    assert e.value.code == 400
