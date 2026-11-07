"""The WOLF assistant agent loop (Claude API, streaming, manual tool loop)."""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

import anthropic

from .prompts import SYSTEM_PROMPT
from .scanner import scan
from .tools import Toolbox, ToolError

DEFAULT_MODEL = "claude-opus-5-5"
MAX_TURNS = 40


class WolfAgent:
    def __init__(
        self,
        toolbox: Toolbox,
        model: str = DEFAULT_MODEL,
        effort: str = "high",
        client: anthropic.Anthropic | None = None,
        out: Callable[[str], None] | None = None,
    ):
        self.toolbox = toolbox
        self.model = model
        self.effort = effort
        self.client = client or anthropic.Anthropic()
        self.out = out or (lambda s: (sys.stdout.write(s), sys.stdout.flush()))
        self.messages: list[Any] = []
        # Stable, cacheable context: system prompt + repo map + knowledge base, frozen at
        # session start so every turn reuses the cached prefix.
        self.system = [
            {"type": "text", "text": SYSTEM_PROMPT},
            {"type": "text", "text": scan(toolbox.root).render(max_tree=400)},
            {"type": "text", "text": "# Current WOLF knowledge base\n\n" + toolbox.read_knowledge()},
        ]

    def ask(self, prompt: str) -> str:
        """Send one user message and run the tool loop until Claude finishes. Returns final text."""
        self.messages.append({"role": "user", "content": prompt})
        final_text = ""
        for _ in range(MAX_TURNS):
            try:
                response = self._stream_turn()
            except ValueError as e:  # SDK could not parse a streamed tool input at all
                self.out(f"\n[warn] malformed tool input from the model ({e}); retrying\n")
                continue

            # Append the full content (thinking/fallback blocks included) unchanged.
            self.messages.append({"role": "assistant", "content": response.content})
            final_text = "".join(b.text for b in response.content if b.type == "text")

            if response.stop_reason == "refusal":
                self.out("\n[the request was declined by the model's safeguards]\n")
                return final_text
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason == "max_tokens":
                if tool_uses:  # input may be truncated; don't run it
                    self.messages.append({"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": b.id, "is_error": True,
                         "content": "Output was cut off at max_tokens; tool not run. Retry with a smaller step."}
                        for b in tool_uses]})
                    continue
                self.out("\n[response hit the output limit]\n")
                return final_text
            if not tool_uses:
                return final_text

            results = []
            for block in tool_uses:
                self.out(f"\n  · {block.name}({_short(block.input)})\n")
                try:
                    content, is_error = self.toolbox.call(block.name, block.input), False
                except ToolError as e:
                    content, is_error = f"Error: {e}", True
                except Exception as e:  # tool bug: report to the model rather than crash
                    content, is_error = f"Error: {type(e).__name__}: {e}", True
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": content, "is_error": is_error})
            self.messages.append({"role": "user", "content": results})
        self.out("\n[stopped: reached the turn limit]\n")
        return final_text

    def _stream_turn(self):
        with self.client.beta.messages.stream(
            model=self.model,
            max_tokens=64000,
            system=self.system,
            messages=self.messages,
            tools=self.toolbox.definitions(),
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            cache_control={"type": "ephemeral"},
            # Server-side refusal fallback: if a safeguard declines, the API reroutes the
            # same request to a suitable fallback model inside the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            started = False
            for text in stream.text_stream:
                if not started:
                    self.out("\n")
                    started = True
                self.out(text)
            return stream.get_final_message()


def _short(args: Any, limit: int = 90) -> str:
    s = json.dumps(args, ensure_ascii=False)
    return s if len(s) <= limit else s[: limit - 3] + "..."
