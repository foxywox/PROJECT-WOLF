"""The wolf-dev assistant: the shared WOLF agent loop pointed at this repository."""

from __future__ import annotations

from typing import Any

from wolf.loop import DEFAULT_MODEL, AgentLoop

from .prompts import SYSTEM_PROMPT
from . import workspace
from .tools import Toolbox

__all__ = ["WolfAgent", "DEFAULT_MODEL"]


class WolfAgent(AgentLoop):
    def __init__(self, toolbox: Toolbox, **kwargs: Any):
            # The same briefing a Claude Code session reads: handoff, changelog, knowledge base,
        # tools, git state and repo map.
        system = [
            {"type": "text", "text": SYSTEM_PROMPT},
            {"type": "text", "text": workspace.brief(toolbox.root, tree_files=400)},
        ]
        super().__init__(toolbox, system, **kwargs)
