"""Memory component: WOLF's long-term memory of you (profile, memories, journal)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..loop import ToolError, tool, validate
from ..memory import MemoryStore
from . import Component, ComponentContext

if TYPE_CHECKING:
    from ..loop import AgentLoop

INSTRUCTIONS = """\
You remember the user across conversations. This is how you learn:
- Notice durable things about the user: who they are, their goals, projects, preferences,
  routines, people in their life, what's worked or not worked for them, and how they like you
  to respond. Save each with `remember` as one short, self-contained fact. Don't ask
  permission for ordinary facts; just save them and keep going.
- Keep the profile (`update_profile`) as a concise summary of the most important,
  long-lived facts, organized in sections such as Identity, Goals, Projects, Preferences,
  People, Routines, How to help me. Rewrite a section when it changes.
- When something you remembered is no longer true, use `update_memory` or `forget`.
  Don't keep contradictory memories.
- Before answering anything personal or that depends on context ("what should I...",
  "remember when...", plans, recommendations), check what you know: the profile and memories
  below, and `recall` for anything not shown.
- If the user asks you to forget something, forget it and confirm.
- Never store passwords, API keys, full card or account numbers, government ID numbers, or
  similar secrets, even if asked."""

REFLECT_PROMPT = (
    "[WOLF end-of-conversation reflection, not from the user] The conversation is ending. "
    "Review it and save anything durable you learned about the user that isn't stored yet "
    "(remember / update_memory / update_profile). Then reply with only a one-sentence summary "
    "of this conversation for your journal."
)


class MemoryTools:
    """The memory tools on their own (usable without the component machinery)."""

    def __init__(self, store: MemoryStore):
        self.store = store
        self._defs = [
            tool("remember", "Save one durable fact about the user to long-term memory.",
                 {"text": {"type": "string", "description": "A short, self-contained fact."},
                  "tags": {"type": "array", "items": {"type": "string"},
                           "description": "1-3 lowercase topic tags, e.g. ['health', 'goals']."}},
                 required=["text"]),
            tool("recall", "Search long-term memory for facts relevant to a query.",
                 {"query": {"type": "string"}}, required=["query"]),
            tool("update_memory", "Replace the text of an existing memory (by id, e.g. 'm12').",
                 {"id": {"type": "string"}, "text": {"type": "string"}}, required=["id", "text"]),
            tool("forget", "Delete a memory by id.", {"id": {"type": "string"}}, required=["id"]),
            tool("update_profile", "Create or rewrite one '## section' of the user's profile summary.",
                 {"section": {"type": "string"}, "content": {"type": "string", "description": "Markdown."}},
                 required=["section", "content"]),
        ]

    def definitions(self) -> list[dict[str, Any]]:
        return self._defs

    def call(self, name: str, args: dict[str, Any]) -> str:
        spec = next((d for d in self._defs if d["name"] == name), None)
        if spec is None:
            raise ToolError(f"Unknown tool: {name}")
        validate(spec, args)
        s = self.store
        try:
            if name == "remember":
                m = s.add(args["text"], args.get("tags"))
                return f"Saved {m.id}."
            if name == "recall":
                hits = s.search(args["query"])
                return "\n".join(m.line() for m in hits) or "(nothing relevant in memory)"
            if name == "update_memory":
                return f"Updated {s.update(args['id'], args['text']).id}."
            if name == "forget":
                return f"Forgot {s.forget(args['id']).id}."
            if name == "update_profile":
                s.update_profile(args["section"], args["content"])
                return f"Profile section '{args['section']}' updated."
        except KeyError as e:
            raise ToolError(f"No memory with id {e}") from e
        except ValueError as e:
            raise ToolError(str(e)) from e
        raise ToolError(f"Unhandled tool: {name}")


def memory_snapshot(store: MemoryStore, max_memories: int = 150) -> str:
    profile = store.profile().strip() or "(empty: you haven't learned about the user yet)"
    mems = store.recent(max_memories)
    total = len(store.all())
    mem_text = "\n".join(m.line() for m in mems) or "(none yet)"
    if total > len(mems):
        mem_text += f"\n({total - len(mems)} older memories not shown; use `recall`.)"
    journal = "\n".join(store.recent_journal()) or "(this is your first conversation)"
    return (f"# User profile\n\n{profile}\n\n# Memories (most recent first)\n\n{mem_text}\n\n"
            f"# Recent conversations\n\n{journal}")


TRIVIAL_CHARS = 40


def _user_words(agent: AgentLoop) -> list[str]:
    """What the user actually typed (no date stamps, tool results or the reflection prompt)."""
    out = []
    for m in agent.messages:
        if isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str):
            text = m["content"]
            if text.startswith("[WOLF end-of-conversation"):
                continue
            if text.startswith("[") and "] " in text[:40]:
                text = text.split("] ", 1)[1]
            out.append(text.strip())
    return out


def reflect(agent: AgentLoop, store: MemoryStore) -> str:
    """End-of-conversation pass: save anything missed, then journal a one-line summary.
    Skipped for trivial chats (a single short message like "hi" or "thanks") to save cost."""
    if not any(m["role"] == "assistant" for m in agent.messages if isinstance(m, dict)):
        return ""
    said = _user_words(agent)
    if len(said) <= 1 and sum(len(t) for t in said) < TRIVIAL_CHARS:
        return ""
    saved = agent.out, agent.on_tool
    agent.out = agent.on_tool = lambda *_a: None  # reflection runs silently
    try:
        summary = agent.ask(REFLECT_PROMPT).strip()
    finally:
        agent.out, agent.on_tool = saved
    store.add_journal(summary)
    return summary


class MemoryComponent(Component):
    name = "memory"
    description = "Remembers you across conversations: profile, memories and a journal."

    def __init__(self, ctx: ComponentContext):
        super().__init__(ctx)
        self.impl = MemoryTools(ctx.store)
        self.max_memories = int(ctx.settings("memory").get("max_memories", 150))

    def tools(self) -> list[dict[str, Any]]:
        return self.impl.definitions()

    def call(self, name: str, args: dict[str, Any]) -> str:
        return self.impl.call(name, args)

    def instructions(self) -> str:
        return INSTRUCTIONS

    def context(self) -> str:
        return memory_snapshot(self.ctx.store, self.max_memories)

    def on_end(self, agent: AgentLoop) -> str | None:
        return reflect(agent, self.ctx.store)
