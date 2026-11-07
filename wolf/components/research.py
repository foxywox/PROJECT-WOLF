"""Research component: lets WOLF take part in the project's research forum and read the plan.

Off by default (it's about building WOLF, not about the owner's life). Turn it on with
`wolf components enable research` or the switch on the You tab.
"""

from __future__ import annotations

from typing import Any

from .. import hub
from ..loop import ToolError, tool
from . import Component

AUTHOR = "WOLF"


class ResearchComponent(Component):
    name = "research"
    description = "Reads WOLF's production plan and takes part in the project's research forum."

    def tools(self) -> list[dict[str, Any]]:
        return [
            tool("read_plan", "Read WOLF's whole production plan with each item's status.", {}),
            tool("list_forum", "List the research forum's threads, most recently active first.", {}),
            tool("read_thread", "Read one forum thread with all its posts.",
                 {"id": {"type": "string", "description": "Thread id from list_forum."}}, required=["id"]),
            tool("post_to_forum",
                 "Post in the research forum as WOLF. Give a thread id to reply, or a title to start a new "
                 "thread. Only post when the user asks you to. The forum is public: never include personal "
                 "details about the user.",
                 {"body": {"type": "string"}, "thread_id": {"type": "string"}, "title": {"type": "string"},
                  "topic": {"type": "string", "description": "Optional plan item id this is about."}},
                 required=["body"]),
        ]

    def call(self, name: str, args: dict[str, Any]) -> str:
        try:
            if name == "read_plan":
                return hub.plan_text()
            if name == "list_forum":
                rows = hub.threads()
                return "\n".join(f"{t['id']}: {t['title']} ({t['replies']} replies, last by {t['last_author']})"
                                 for t in rows) or "(no threads yet)"
            if name == "read_thread":
                t = hub.thread(args["id"])
                return f"{t['title']}\n\n" + "\n\n".join(f"{p['author']} ({p['kind']}): {p['body']}" for p in t["posts"])
            if name == "post_to_forum":
                if args.get("thread_id"):
                    t = hub.reply(args["thread_id"], args["body"], AUTHOR, "ai")
                    return f"Replied in '{t['title']}'."
                if not args.get("title"):
                    raise ToolError("Give a thread_id to reply, or a title to start a new thread.")
                t = hub.new_thread(args["title"], args["body"], AUTHOR, "ai", args.get("topic"))
                return f"Started thread '{t['title']}' (id {t['id']})."
        except hub.HubError as e:
            raise ToolError(str(e)) from e
        raise ToolError(f"Unknown tool: {name}")

    def instructions(self) -> str:
        return ("You can read WOLF's own production plan and research forum. Use them when the user asks "
                "about WOLF's development. Post in the forum only when the user asks; it is public, so never "
                "include personal details about the user.")
