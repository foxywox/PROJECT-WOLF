"""WOLF: a personal AI assistant that learns about you over time.

The core only knows WOLF's personality. Everything WOLF can *do* (memory, web search, the
clock, ...) comes from interchangeable components in `wolf/components/`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .components import ComponentContext, Toolkit, enabled_names, load_components
from .components.memory import REFLECT_PROMPT, MemoryTools, reflect  # noqa: F401  (public API)
from .config import load_config, make_client
from .loop import AgentLoop
from .memory import MemoryStore

SYSTEM_PROMPT = """\
You are WOLF, a personal AI assistant for one person: the user. You stay with them over
months and years, and you get more useful the more you learn about them.

Boundaries
- Never store or repeat back passwords, API keys, full card or account numbers, government ID
  numbers, or similar secrets, even if asked. Say you won't, and why.
- Be honest about what you know and what you're guessing.

Style
- Warm, direct, and practical. Use what you know to tailor answers without reciting it back.
- Ask a short clarifying question when it would change your answer.
"""


def now_stamp() -> str:
    """Date/time prefix for a conversation's first message (kept out of the cached system prompt)."""
    return f"[{datetime.now().strftime('%A %Y-%m-%d %H:%M')}] "


def build_toolkit(store: MemoryStore, components: list[str] | None = None, web: bool = True) -> Toolkit:
    config = load_config(store.home)
    names = list(components) if components is not None else enabled_names(config)
    if not web:
        names = [n for n in names if n != "web_search"]
    return Toolkit(load_components(ComponentContext(store=store, config=config), names))


def system_blocks(kit: Toolkit) -> list[dict[str, Any]]:
    """Two cacheable blocks, frozen for the conversation: who WOLF is + how to use its
    components, then what the components know right now (e.g. the memory snapshot)."""
    stable = SYSTEM_PROMPT
    if kit.instructions():
        stable += "\n# Your abilities\n\n" + kit.instructions() + "\n"
    blocks = [{"type": "text", "text": stable}]
    if kit.context():
        blocks.append({"type": "text", "text": kit.context()})
    return blocks


def build_system(store: MemoryStore, components: list[str] | None = None) -> list[dict[str, Any]]:
    return system_blocks(build_toolkit(store, components))


def build_wolf(store: MemoryStore, web: bool = True, components: list[str] | None = None,
               **kwargs) -> AgentLoop:
    kit = build_toolkit(store, components, web=web)
    if kwargs.get("client") is None:
        kwargs["client"] = make_client(store.home)
    return AgentLoop(kit, system_blocks(kit), server_tools=kit.server_tools(), **kwargs)


def finish_conversation(agent: AgentLoop) -> str:
    """Run every component's end-of-conversation hook. Returns the journal summary, if any."""
    summary = ""
    for comp in getattr(agent.toolbox, "components", []):
        result = comp.on_end(agent)
        if result and not summary:
            summary = result
    return summary
