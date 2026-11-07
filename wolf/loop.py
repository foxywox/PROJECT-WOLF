"""Shared Claude agent loop (streaming, manual tool loop) used by WOLF and wolf-dev.

A "toolbox" is any object with:
  definitions() -> list[dict]          client tool schemas
  call(name, args) -> str              runs a tool; raises ToolError on bad input
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable, Protocol

import anthropic

DEFAULT_MODEL = "claude-opus-5-5"
MAX_TURNS = 40


class ToolError(Exception):
    pass


class Toolbox(Protocol):
    def definitions(self) -> list[dict[str, Any]]: ...
    def call(self, name: str, args: dict[str, Any]) -> str: ...


def tool(name: str, description: str, props: dict, required: list[str] | None = None) -> dict:
    """Build a client tool definition. Inputs are validated with `validate` before running."""
    return {
        "name": name,
        "description": description,
        "input_schema": {"type": "object", "properties": props, "required": required or [],
                         "additionalProperties": False},
        # Stream large tool inputs as they're generated; validated before anything runs.
        "eager_input_streaming": True,
    }


def validate(spec: dict, args: Any) -> None:
    """Minimal JSON-schema check for the shapes our tools use."""
    if not isinstance(args, dict):
        raise ToolError("Tool input must be a JSON object")
    schema = spec["input_schema"]
    missing = [k for k in schema.get("required", []) if k not in args]
    if missing:
        raise ToolError(f"Missing required argument(s): {', '.join(missing)}")
    props = schema["properties"]
    for key, value in args.items():
        if key not in props:
            raise ToolError(f"Unexpected argument: {key}")
        t = props[key]["type"]
        if t == "string" and not isinstance(value, str):
            raise ToolError(f"Argument '{key}' must be a string")
        if t == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            raise ToolError(f"Argument '{key}' must be an integer")
        if t == "array" and not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
            raise ToolError(f"Argument '{key}' must be a list of strings")


class AgentLoop:
    def __init__(
        self,
        toolbox: Toolbox,
        system: list[dict[str, Any]],
        model: str = DEFAULT_MODEL,
        effort: str = "high",
        server_tools: list[dict[str, Any]] | None = None,
        client: anthropic.Anthropic | None = None,
        out: Callable[[str], None] | None = None,
    ):
        self.toolbox = toolbox
        self.system = system  # frozen for the session so the prefix stays cached
        self.model = model
        self.effort = effort
        self.server_tools = server_tools or []
        self.client = client or anthropic.Anthropic()
        self.out = out or (lambda s: (sys.stdout.write(s), sys.stdout.flush()))
        self.messages: list[Any] = []

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

            # Append the full content (thinking/fallback/server-tool blocks) unchanged.
            self.messages.append({"role": "assistant", "content": response.content})
            final_text = "".join(b.text for b in response.content if b.type == "text")

            if response.stop_reason == "refusal":
                self.out("\n[the request was declined by the model's safeguards]\n")
                return final_text
            if response.stop_reason == "pause_turn":  # long server-tool turn; let it continue
                continue
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
            tools=[*self.toolbox.definitions(), *self.server_tools],
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
