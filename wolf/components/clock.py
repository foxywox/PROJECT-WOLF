"""Clock component: the current date and time, so WOLF never guesses what day it is."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..loop import tool
from . import Component


class ClockComponent(Component):
    name = "clock"
    description = "Tells WOLF the current date and time."

    def tools(self) -> list[dict[str, Any]]:
        return [tool("current_time", "The user's current local date, time, weekday and time zone.", {})]

    def call(self, name: str, args: dict[str, Any]) -> str:
        now = datetime.now().astimezone()
        return now.strftime("%A, %B %d, %Y, %I:%M %p (%Z, UTC%z)").replace(" 0", " ")

    def instructions(self) -> str:
        return ("The first message of a conversation is stamped with the date and time. For anything "
                "time-sensitive later in a long conversation (deadlines, \"how long until...\"), "
                "call `current_time` instead of assuming.")
