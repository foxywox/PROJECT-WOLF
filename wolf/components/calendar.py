"""Calendar component: WOLF can see your calendar (read-only), from any service.

Works with the private iCal (.ics) link that Google Calendar, Outlook and Apple Calendar all
provide, or with a local .ics file. Links are kept in $WOLF_HOME/config.json (owner-only) under
settings.calendar.calendars and are never shown back in full. Calendars are fetched at most
every 15 minutes; if a fetch fails, the last good copy is used.

Add one in the app under Settings, Calendar.
"""

from __future__ import annotations

import hashlib
import time
from urllib.request import Request, urlopen
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from ..config import load_config, save_config
from ..loop import ToolError, tool
from . import Component

CACHE_SECONDS = 15 * 60
MAX_BYTES = 5 * 1024 * 1024
HOW_TO = ("Google Calendar: Settings, pick the calendar, 'Secret address in iCal format'. "
          "Outlook: Settings, Calendar, Shared calendars, Publish a calendar, copy the ICS link. "
          "Apple: in Calendar, share the calendar as a public calendar and copy the link.")


class CalendarError(Exception):
    pass


# ---------------------------------------------------------------- settings

def calendars(home: Path) -> list[dict[str, str]]:
    cals = ((load_config(home).get("settings") or {}).get("calendar") or {}).get("calendars") or []
    return [c for c in cals if isinstance(c, dict) and c.get("url")]


def _save(home: Path, cals: list[dict[str, str]]) -> None:
    config = load_config(home)
    config.setdefault("settings", {}).setdefault("calendar", {})["calendars"] = cals
    save_config(config, home)


def add_calendar(home: Path, name: str, url: str, allow_files: bool = True) -> int:
    """Validate by fetching and parsing, then save. Returns how many events the calendar has.
    The web app passes allow_files=False so it can only add web links, never local paths."""
    name, url = " ".join(name.split())[:40] or "Calendar", url.strip()
    if not url:
        raise CalendarError("Paste the calendar's private link first.")
    if not allow_files and not url.lower().startswith(("https://", "http://", "webcal://")):
        raise CalendarError("Paste a web link that starts with https:// or webcal://.")
    count = len(_parse(_fetch(url, home, force=True)).walk("VEVENT"))
    cals = [c for c in calendars(home) if c["url"] != url and c["name"] != name] + [{"name": name, "url": url}]
    _save(home, cals)
    return count


def remove_calendar(home: Path, name: str) -> None:
    cals = calendars(home)
    if not any(c["name"] == name for c in cals):
        raise CalendarError(f"No calendar named '{name}'.")
    _save(home, [c for c in cals if c["name"] != name])


def public_list(home: Path) -> list[dict[str, str]]:
    """Names and a masked hint of each link, safe to show in the app."""
    out = []
    for c in calendars(home):
        url = c["url"]
        host = url.split("//", 1)[-1].split("/", 1)[0] if "//" in url else Path(url).name
        out.append({"name": c["name"], "source": host})
    return out


# ---------------------------------------------------------------- fetching

def _fetch(url: str, home: Path, force: bool = False) -> bytes:
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    if not url.startswith(("https://", "http://", "file://")):
        path = Path(url).expanduser()
        if not path.is_file():
            raise CalendarError("That doesn't look like a calendar link or an .ics file.")
        return path.read_bytes()[:MAX_BYTES]
    cache = home / "cache" / f"calendar-{hashlib.sha256(url.encode()).hexdigest()[:16]}.ics"
    if not force and cache.exists() and time.time() - cache.stat().st_mtime < CACHE_SECONDS:
        return cache.read_bytes()
    try:
        req = Request(url, headers={"User-Agent": "WOLF personal assistant (calendar)"})
        with urlopen(req, timeout=10) as r:
            data = r.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise CalendarError("That calendar is too large (over 5 MB).")
        if b"BEGIN:VCALENDAR" not in data[:2000]:
            raise CalendarError("That link didn't return a calendar. Use the private iCal (.ics) link.")
    except (OSError, ValueError) as e:
        if cache.exists() and not force:
            return cache.read_bytes()  # last good copy
        raise CalendarError(f"Couldn't fetch the calendar ({e.__class__.__name__}). Check the link.") from e
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(data)
    return data


def _parse(data: bytes):
    import icalendar

    try:
        return icalendar.Calendar.from_ical(data)
    except Exception as e:  # icalendar raises ValueError and friends on bad input
        raise CalendarError("That file isn't a valid calendar.") from e


def _local(dt: date | datetime) -> tuple[datetime, bool]:
    """Return (local naive datetime, is_all_day)."""
    if isinstance(dt, datetime):
        return (dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt), False
    return datetime(dt.year, dt.month, dt.day), True


def events(home: Path, start: datetime, end: datetime) -> list[dict[str, Any]]:
    import recurring_ical_events

    out: list[dict[str, Any]] = []
    errors = []
    for cal in calendars(home):
        try:
            parsed = _parse(_fetch(cal["url"], home))
            for ev in recurring_ical_events.of(parsed).between(start, end):
                s, all_day = _local(ev.get("DTSTART").dt)
                e = _local(ev.get("DTEND").dt)[0] if ev.get("DTEND") else None
                out.append({"calendar": cal["name"], "title": str(ev.get("SUMMARY", "(no title)")),
                            "start": s, "end": e, "all_day": all_day,
                            "location": str(ev.get("LOCATION", "") or "")})
        except CalendarError as e:
            errors.append(f"{cal['name']}: {e}")
    out.sort(key=lambda x: (x["start"], not x["all_day"]))
    if errors and not out:
        raise CalendarError("; ".join(errors))
    return out


def _clock(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def describe(evs: list[dict[str, Any]]) -> str:
    lines = []
    for e in evs:
        day = e["start"].strftime("%a %b %d").replace(" 0", " ")
        when = "all day" if e["all_day"] else _clock(e["start"]) + (f"-{_clock(e['end'])}" if e["end"] else "")
        where = f" @ {e['location']}" if e["location"] else ""
        lines.append(f"- {day}, {when}: {e['title']}{where} [{e['calendar']}]")
    return "\n".join(lines)


# ---------------------------------------------------------------- component

class CalendarComponent(Component):
    name = "calendar"
    description = "Sees your calendar (read-only) from Google, Outlook, Apple or an .ics file."

    def tools(self) -> list[dict[str, Any]]:
        return [tool("calendar_events",
                     "List the user's calendar events in a date range (read-only). Times are local.",
                     {"start_date": {"type": "string", "description": "YYYY-MM-DD; default today."},
                      "days": {"type": "integer", "description": "How many days to cover, 1-62; default 7."}})]

    def call(self, name: str, args: dict[str, Any]) -> str:
        if not calendars(self.ctx.home):
            return "No calendar is connected. The user can connect one in WOLF's app under Settings, Calendar."
        try:
            start = datetime.fromisoformat(args["start_date"]) if args.get("start_date") else None
        except ValueError as e:
            raise ToolError("start_date must look like 2026-11-09") from e
        start = (start or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
        days = max(1, min(62, int(args.get("days") or 7)))
        try:
            evs = events(self.ctx.home, start, start + timedelta(days=days))
        except CalendarError as e:
            raise ToolError(str(e)) from e
        span = f"{start:%a %b %d} to {(start + timedelta(days=days - 1)):%a %b %d}".replace(" 0", " ")
        return f"Events {span}:\n{describe(evs)}" if evs else f"No events {span}."

    def instructions(self) -> str:
        return ("You can read the user's calendar (read-only) with `calendar_events`. Use it for anything "
                "about their schedule, free time or upcoming plans. You can't add or change events; say "
                "so if asked, and offer a reminder instead if that ability is on.")

    def context(self) -> str:
        if not calendars(self.ctx.home):
            return ""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            evs = events(self.ctx.home, today, today + timedelta(days=2))
        except CalendarError:
            return "# Calendar\n\n(The calendar couldn't be read just now; use `calendar_events` to retry.)"
        return "# Calendar: today and tomorrow\n\n" + (describe(evs) or "(nothing scheduled)")
