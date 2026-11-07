"""Tests for personality, calendar and reminders."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

import wolf.cli as cli
from wolf import personality
from wolf.assistant import build_system, build_toolkit
from wolf.components import calendar, reminders
from wolf.loop import ToolError
from wolf.memory import MemoryStore
from wolf.server import WolfApp, make_handler

ICS = Path(__file__).parent / "data" / "sample.ics"


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    return MemoryStore(tmp_path / "home")


# ---------------------------------------------------------------- personality

def test_personality_presets_and_custom(store):
    home = store.home
    assert personality.current(home) == "balanced"
    assert "Warm, direct" in personality.text(home) or "warm, direct" in personality.text(home)
    personality.choose(home, "coach")
    stable = build_system(store)[0]["text"]
    assert "encouraging coach" in stable and "Boundaries" in stable
    with pytest.raises(ValueError):
        personality.choose(home, "custom")  # nothing written yet
    personality.choose(home, "custom", "Talk like a laid-back friend.")
    assert "laid-back friend" in build_system(store)[0]["text"]
    assert "Never store" in build_system(store)[0]["text"]  # boundaries always stay
    with pytest.raises(ValueError):
        personality.choose(home, "pirate")
    with pytest.raises(ValueError):
        personality.choose(home, "custom", "x" * 5000)


def test_personality_cli(store, capsys):
    home = str(store.home)
    assert cli.main(["--home", home, "personality", "set", "brief"]) == 0
    assert cli.main(["--home", home, "personality"]) == 0
    assert "* brief" in capsys.readouterr().out
    assert cli.main(["--home", home, "personality", "set", "custom"]) == 1


# ---------------------------------------------------------------- calendar

def test_calendar_reads_recurring_and_all_day_events(store):
    assert calendar.add_calendar(store.home, "Work", str(ICS)) == 3
    evs = calendar.events(store.home, datetime(2026, 11, 9), datetime(2026, 11, 13))
    titles = [e["title"] for e in evs]
    assert titles.count("Team standup") == 2 and "Dentist" in titles and "Holiday" in titles
    holiday = next(e for e in evs if e["title"] == "Holiday")
    assert holiday["all_day"] and "all day" in calendar.describe([holiday])


def test_calendar_tool_and_context(store):
    kit = build_toolkit(store, ["calendar"])
    assert "No calendar is connected" in kit.call("calendar_events", {})
    calendar.add_calendar(store.home, "Work", str(ICS))
    out = kit.call("calendar_events", {"start_date": "2026-11-09", "days": 2})
    assert "Dentist" in out and "Team standup" in out and "Holiday" not in out
    with pytest.raises(ToolError):
        kit.call("calendar_events", {"start_date": "next tuesday"})
    assert kit.get("calendar").context().startswith("# Calendar")


def test_calendar_bad_inputs_and_removal(store, tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("not a calendar")
    with pytest.raises(calendar.CalendarError):
        calendar.add_calendar(store.home, "Bad", str(bad))
    with pytest.raises(calendar.CalendarError, match="https"):
        calendar.add_calendar(store.home, "Local", str(ICS), allow_files=False)
    calendar.add_calendar(store.home, "Work", str(ICS))
    assert calendar.public_list(store.home) == [{"name": "Work", "source": "sample.ics"}]
    calendar.remove_calendar(store.home, "Work")
    assert calendar.calendars(store.home) == []
    with pytest.raises(calendar.CalendarError):
        calendar.remove_calendar(store.home, "Work")


def test_calendar_uses_last_good_copy_when_offline(store, monkeypatch):
    url = "https://calendar.example/private.ics"
    monkeypatch.setattr(calendar, "urlopen", _fake_urlopen(ICS.read_bytes()))
    calendar.add_calendar(store.home, "Web", url)
    monkeypatch.setattr(calendar, "urlopen", _fake_urlopen(OSError("offline")))
    monkeypatch.setattr(calendar, "CACHE_SECONDS", 0)
    evs = calendar.events(store.home, datetime(2026, 11, 9), datetime(2026, 11, 13))
    assert any(e["title"] == "Dentist" for e in evs)


def _fake_urlopen(result):
    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            return result

    def opener(req, timeout=0):
        if isinstance(result, Exception):
            raise result
        return Resp()
    return opener


# ---------------------------------------------------------------- reminders

def test_reminders_due_upcoming_and_done(store):
    home = store.home
    past = (datetime.now() - timedelta(hours=1)).isoformat(timespec="minutes")
    soon = (datetime.now() + timedelta(days=2)).isoformat(timespec="minutes")
    r1 = reminders.add(home, "Call the dentist", past)
    reminders.add(home, "Pay rent", soon[:10])
    assert [r["id"] for r in reminders.due(home)] == [r1["id"]]
    assert [r["text"] for r in reminders.upcoming(home)] == ["Pay rent"]
    reminders.complete(home, r1["id"])
    assert reminders.due(home) == []
    with pytest.raises(reminders.ReminderError):
        reminders.add(home, "x", "tomorrow")
    with pytest.raises(reminders.ReminderError):
        reminders.complete(home, "r99")


def test_reminders_tools_and_context(store):
    kit = build_toolkit(store, ["reminders"])
    past = (datetime.now() - timedelta(minutes=5)).isoformat(timespec="minutes")
    assert kit.call("add_reminder", {"text": "Water the plants", "due": past}).startswith("Set r1")
    ctx = kit.get("reminders").context()
    assert "Due now" in ctx and "Water the plants" in ctx
    assert "Water the plants" in kit.call("list_reminders", {})
    assert kit.call("complete_reminder", {"id": "r1"}) == "Done: Water the plants"
    assert kit.get("reminders").context() == ""
    with pytest.raises(ToolError):
        kit.call("add_reminder", {"text": "x", "due": "soonish"})


# ---------------------------------------------------------------- app API

@pytest.fixture
def server(store):
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


def test_personality_api(server):
    assert _req(server, "/api/personality")["current"] == "balanced"
    out = _req(server, "/api/personality", "POST", {"id": "custom", "custom": "Speak like a friendly lighthouse keeper."})
    assert out["current"] == "custom" and "lighthouse" in out["custom"]
    with pytest.raises(urllib.error.HTTPError) as e:
        _req(server, "/api/personality", "POST", {"id": "nope"})
    assert e.value.code == 400


def test_reminders_api(server):
    past = (datetime.now() - timedelta(minutes=1)).isoformat(timespec="minutes")
    out = _req(server, "/api/reminders", "POST", {"text": "Stretch", "due": past})
    assert out["due"][0]["text"] == "Stretch"
    out = _req(server, f"/api/reminders/{out['due'][0]['id']}/done", "POST", {})
    assert out["due"] == [] and out["open"] == []
    with pytest.raises(urllib.error.HTTPError) as e:
        _req(server, "/api/reminders", "POST", {"text": "x", "due": "whenever"})
    assert e.value.code == 400


def test_calendar_api_accepts_links_only(server, monkeypatch):
    with pytest.raises(urllib.error.HTTPError) as e:
        _req(server, "/api/calendar", "POST", {"name": "Local", "url": str(ICS)})
    assert e.value.code == 400  # the app can't make WOLF read files on the computer
    monkeypatch.setattr(calendar, "urlopen", _fake_urlopen(ICS.read_bytes()))
    out = _req(server, "/api/calendar", "POST", {"name": "Work", "url": "webcal://calendar.example/a.ics"})
    assert out["added_events"] == 3 and out["calendars"] == [{"name": "Work", "source": "calendar.example"}]
    assert any(c["name"] == "calendar" and c["enabled"] for c in _req(server, "/api/components")["components"])
    assert _req(server, "/api/calendar/Work", "DELETE")["calendars"] == []
