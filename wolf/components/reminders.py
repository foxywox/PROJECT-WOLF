"""Reminders component: "remind me to..." and WOLF brings it up when it's due.

Reminders live in $WOLF_HOME/reminders.json. WOLF sees what's due (and coming up) at the
start of every conversation, the app shows due reminders above the chat, and they can be
ticked off in either place.
"""

from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from ..loop import ToolError, tool
from . import Component

_lock = threading.Lock()
UPCOMING_DAYS = 7


class ReminderError(ValueError):
    pass


def _path(home: Path) -> Path:
    return home / "reminders.json"


def load(home: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(_path(home).read_text("utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save(home: Path, items: list[dict[str, Any]]) -> None:
    path = _path(home)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", "utf-8")
    tmp.replace(path)


def parse_due(due: str) -> datetime:
    """'2026-11-09' (a whole day, due from 9 AM) or '2026-11-09T15:30'."""
    try:
        if len(due.strip()) == 10:
            d = date.fromisoformat(due.strip())
            return datetime(d.year, d.month, d.day, 9, 0)
        dt = datetime.fromisoformat(due.strip())
        return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt
    except ValueError as e:
        raise ReminderError("Give the time like 2026-11-09 or 2026-11-09T15:30.") from e


def add(home: Path, text: str, due: str) -> dict[str, Any]:
    text = " ".join(str(text).split())
    if not text:
        raise ReminderError("What should I remind you about?")
    when = parse_due(due)
    with _lock:
        items = load(home)
        next_id = 1 + max((int(r["id"][1:]) for r in items if str(r.get("id", ""))[1:].isdigit()), default=0)
        item = {"id": f"r{next_id}", "text": text[:300], "due": when.isoformat(timespec="minutes"),
                "done": False, "created": datetime.now().isoformat(timespec="minutes")}
        items.append(item)
        _save(home, items)
    return item


def complete(home: Path, rid: str) -> dict[str, Any]:
    with _lock:
        items = load(home)
        for r in items:
            if r.get("id") == rid:
                r["done"] = True
                _save(home, items)
                return r
    raise ReminderError(f"No reminder with id {rid}")


def due(home: Path, now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now()
    return sorted((r for r in load(home) if not r.get("done") and datetime.fromisoformat(r["due"]) <= now),
                  key=lambda r: r["due"])


def upcoming(home: Path, now: datetime | None = None, days: int = UPCOMING_DAYS) -> list[dict[str, Any]]:
    now = now or datetime.now()
    end = now + timedelta(days=days)
    return sorted((r for r in load(home) if not r.get("done") and now < datetime.fromisoformat(r["due"]) <= end),
                  key=lambda r: r["due"])


def describe(r: dict[str, Any]) -> str:
    when = datetime.fromisoformat(r["due"])
    return f"{r['id']}: {r['text']} (due {when:%a %b %d, %I:%M %p})".replace(" 0", " ")


class RemindersComponent(Component):
    name = "reminders"
    description = "Keeps reminders and brings them up when they're due."

    def tools(self) -> list[dict[str, Any]]:
        return [
            tool("add_reminder", "Set a reminder for the user.",
                 {"text": {"type": "string", "description": "What to remind them about, short."},
                  "due": {"type": "string", "description": "Local date 'YYYY-MM-DD' or date and time 'YYYY-MM-DDTHH:MM'."}},
                 required=["text", "due"]),
            tool("list_reminders", "List the user's open reminders.", {}),
            tool("complete_reminder", "Mark a reminder as done (or cancel it).",
                 {"id": {"type": "string", "description": "Reminder id, e.g. 'r3'."}}, required=["id"]),
        ]

    def call(self, name: str, args: dict[str, Any]) -> str:
        home = self.ctx.home
        try:
            if name == "add_reminder":
                return "Set " + describe(add(home, args["text"], args["due"]))
            if name == "list_reminders":
                open_items = sorted((r for r in load(home) if not r.get("done")), key=lambda r: r["due"])
                return "\n".join(describe(r) for r in open_items) or "(no open reminders)"
            if name == "complete_reminder":
                return "Done: " + complete(home, args["id"])["text"]
        except ReminderError as e:
            raise ToolError(str(e)) from e
        raise ToolError(f"Unknown tool: {name}")

    def instructions(self) -> str:
        return ("When the user asks to be reminded of something, use `add_reminder` with a concrete local "
                "date or time (work it out from today's date; if they gave no time, pick a sensible one "
                "and say which). If reminders are due, bring them up near the start of your reply, briefly, "
                "and mark them done with `complete_reminder` once the user has dealt with them.")

    def context(self) -> str:
        now_due, soon = due(self.ctx.home), upcoming(self.ctx.home)
        if not (now_due or soon):
            return ""
        parts = ["# Reminders"]
        if now_due:
            parts.append("Due now:\n" + "\n".join("- " + describe(r) for r in now_due))
        if soon:
            parts.append(f"Coming up (next {UPCOMING_DAYS} days):\n" + "\n".join("- " + describe(r) for r in soon))
        return "\n\n".join(parts)
