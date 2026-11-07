"""The wolf-dev assistant: the shared WOLF agent loop pointed at this repository."""

from __future__ import annotations

from typing import Any

from wolf.loop import DEFAULT_MODEL, AgentLoop

from .prompts import SYSTEM_PROMPT
from .scanner import scan
from .tools import Toolbox

__all__ = ["WolfAgent", "DEFAULT_MODEL"]


class WolfAgent(AgentLoop):
    def __init__(self, toolbox: Toolbox, **kwargs: Any):
        # Stable, cacheable context frozen at session start: prompt + repo map + knowledge base.
        system = [
            {"type": "text", "text": SYSTEM_PROMPT},
            {"type": "text", "text": scan(toolbox.root).render(max_tree=400)},
            {"type": "text", "text": "# Current WOLF knowledge base\n\n" + toolbox.read_knowledge()},
        ]
        super().__init__(toolbox, system, **kwargs)
