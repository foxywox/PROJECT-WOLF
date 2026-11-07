"""Web search component: lets WOLF look things up (runs on Anthropic's servers)."""

from __future__ import annotations

from typing import Any

from . import Component


class WebSearchComponent(Component):
    name = "web_search"
    description = "Searches the web for current information."

    def server_tools(self) -> list[dict[str, Any]]:
        max_uses = int(self.ctx.settings("web_search").get("max_uses", 5))
        return [{"type": "web_search_20260209", "name": "web_search", "max_uses": max_uses}]

    def instructions(self) -> str:
        return ("Use `web_search` for anything current or that you aren't sure of (news, prices, "
                "opening hours, facts that change). Say where information came from.")
