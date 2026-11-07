"""Tools the WOLF assistant can call. All file access is sandboxed to the repo root.

Read tools are always available. Write tools (`write_file`, `run_command`) are
only exposed when the assistant runs with --allow-write / --allow-run, and each
call is confirmed by the user unless --yes is passed.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from .scanner import IGNORED_DIRS, scan

MAX_READ_BYTES = 200_000
MAX_OUTPUT_CHARS = 30_000
KNOWLEDGE_FILE = Path("docs/wolf/KNOWLEDGE.md")


class ToolError(Exception):
    pass


class Toolbox:
    def __init__(
        self,
        root: str | Path,
        allow_write: bool = False,
        allow_run: bool = False,
        confirm: Callable[[str], bool] | None = None,
    ):
        self.root = Path(root).resolve()
        self.allow_write = allow_write
        self.allow_run = allow_run
        self.confirm = confirm or (lambda _msg: True)

    # ---------- helpers ----------
    def _resolve(self, path: str) -> Path:
        p = (self.root / path).resolve()
        if p != self.root and self.root not in p.parents:
            raise ToolError(f"Path escapes the repository: {path}")
        if ".git" in p.relative_to(self.root).parts:
            raise ToolError("Access to .git internals is not allowed")
        return p

    @staticmethod
    def _clip(text: str) -> str:
        if len(text) > MAX_OUTPUT_CHARS:
            return text[:MAX_OUTPUT_CHARS] + f"\n... [truncated, {len(text) - MAX_OUTPUT_CHARS} more chars]"
        return text

    # ---------- tools ----------
    def repo_map(self) -> str:
        return scan(self.root).render()

    def list_files(self, glob: str = "**/*") -> str:
        files = [f for f in scan(self.root).files if fnmatch.fnmatch(f, glob) or fnmatch.fnmatch(f, glob.replace("**/", ""))]
        return self._clip("\n".join(files) or "(no matching files)")

    def read_file(self, path: str, start_line: int = 1, end_line: int | None = None) -> str:
        p = self._resolve(path)
        if not p.is_file():
            raise ToolError(f"Not a file: {path}")
        data = p.read_bytes()[:MAX_READ_BYTES]
        if b"\x00" in data[:4096]:
            return f"(binary file, {p.stat().st_size} bytes)"
        lines = data.decode("utf-8", errors="replace").splitlines()
        start = max(start_line, 1)
        end = min(end_line or len(lines), len(lines))
        body = "\n".join(f"{i:>5}  {lines[i - 1]}" for i in range(start, end + 1))
        return self._clip(f"{path} (lines {start}-{end} of {len(lines)})\n{body}")

    def search(self, pattern: str, glob: str = "*", max_results: int = 200) -> str:
        try:
            rx = re.compile(pattern)
        except re.error as e:
            raise ToolError(f"Bad regex: {e}") from e
        hits: list[str] = []
        for rel in scan(self.root).files:
            if not fnmatch.fnmatch(Path(rel).name, glob) and not fnmatch.fnmatch(rel, glob):
                continue
            p = self.root / rel
            try:
                if p.stat().st_size > MAX_READ_BYTES:
                    continue
                text = p.read_text("utf-8", errors="ignore")
            except OSError:
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{rel}:{n}: {line.strip()[:200]}")
                    if len(hits) >= max_results:
                        return self._clip("\n".join(hits) + "\n... (result limit reached)")
        return self._clip("\n".join(hits) or "(no matches)")

    def read_knowledge(self) -> str:
        p = self.root / KNOWLEDGE_FILE
        return p.read_text("utf-8") if p.exists() else "(knowledge base is empty)"

    def update_knowledge(self, section: str, content: str) -> str:
        """Replace (or append) a `## section` in the WOLF knowledge base. Always allowed:
        it's the assistant's own memory, kept in version control so you can review it."""
        p = self.root / KNOWLEDGE_FILE
        p.parent.mkdir(parents=True, exist_ok=True)
        text = p.read_text("utf-8") if p.exists() else "# WOLF Knowledge Base\n"
        header = f"## {section.strip()}"
        block = f"{header}\n\n{content.strip()}\n"
        pattern = re.compile(rf"^{re.escape(header)}\s*\n.*?(?=^## |\Z)", re.S | re.M)
        if pattern.search(text):
            text = pattern.sub(lambda _m: block + "\n", text, count=1)
        else:
            text = text.rstrip() + "\n\n" + block
        p.write_text(text.rstrip() + "\n", "utf-8")
        return f"Updated section '{section}' in {KNOWLEDGE_FILE}"

    def write_file(self, path: str, content: str) -> str:
        if not self.allow_write:
            raise ToolError("Writing is disabled. Re-run with --allow-write.")
        p = self._resolve(path)
        if not self.confirm(f"Write {len(content)} chars to {path}?"):
            return "User declined the write."
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, "utf-8")
        return f"Wrote {path}"

    def run_command(self, command: str, timeout: int = 120) -> str:
        if not self.allow_run:
            raise ToolError("Running commands is disabled. Re-run with --allow-run.")
        if not self.confirm(f"Run: {command}"):
            return "User declined to run the command."
        try:
            r = subprocess.run(command, shell=True, cwd=self.root, capture_output=True,
                               text=True, timeout=min(int(timeout), 600))
        except subprocess.TimeoutExpired:
            return f"Command timed out after {timeout}s"
        return self._clip(f"exit code {r.returncode}\n--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}")

    # ---------- schema / dispatch ----------
    def definitions(self) -> list[dict[str, Any]]:
        defs: list[dict[str, Any]] = [
            _tool("repo_map", "Compact map of the WOLF repository: languages, manifests, entry points, file tree.", {}),
            _tool("list_files", "List repository files matching a glob (e.g. 'src/**/*.py').",
                  {"glob": {"type": "string", "description": "Glob pattern; default '**/*'."}}),
            _tool("read_file", "Read a text file (with line numbers). Use start_line/end_line for large files.",
                  {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}},
                  required=["path"]),
            _tool("search", "Regex search across repository files. Returns path:line: text.",
                  {"pattern": {"type": "string", "description": "Python regex."},
                   "glob": {"type": "string", "description": "Filename glob filter, e.g. '*.py'."}},
                  required=["pattern"]),
            _tool("read_knowledge", "Read the persistent WOLF knowledge base (docs/wolf/KNOWLEDGE.md).", {}),
            _tool("update_knowledge",
                  "Create or replace a '## section' in the WOLF knowledge base. Use it to record durable "
                  "findings (architecture, conventions, gotchas, how to run things) for future sessions.",
                  {"section": {"type": "string"}, "content": {"type": "string", "description": "Markdown body."}},
                  required=["section", "content"]),
        ]
        if self.allow_write:
            defs.append(_tool("write_file", "Create or overwrite a file in the repository with the full content.",
                              {"path": {"type": "string"}, "content": {"type": "string"}},
                              required=["path", "content"]))
        if self.allow_run:
            defs.append(_tool("run_command", "Run a shell command at the repo root (tests, builds, linters).",
                              {"command": {"type": "string"}, "timeout": {"type": "integer"}},
                              required=["command"]))
        return defs

    def call(self, name: str, args: dict[str, Any]) -> str:
        spec = next((d for d in self.definitions() if d["name"] == name), None)
        if spec is None:
            raise ToolError(f"Unknown or disabled tool: {name}")
        if not isinstance(args, dict):
            raise ToolError("Tool input must be a JSON object")
        missing = [k for k in spec["input_schema"].get("required", []) if k not in args]
        if missing:
            raise ToolError(f"Missing required argument(s): {', '.join(missing)}")
        props = spec["input_schema"]["properties"]
        for key, value in args.items():
            if key not in props:
                raise ToolError(f"Unexpected argument: {key}")
            expected = props[key]["type"]
            if expected == "string" and not isinstance(value, str):
                raise ToolError(f"Argument '{key}' must be a string")
            if expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
                raise ToolError(f"Argument '{key}' must be an integer")
        return getattr(self, name)(**args)


def _tool(name: str, description: str, props: dict, required: list[str] | None = None) -> dict:
    return {
        "name": name,
        "description": description,
        "input_schema": {"type": "object", "properties": props, "required": required or [],
                         "additionalProperties": False},
        # Stream large tool inputs (e.g. file contents) as they are generated; inputs are
        # validated in Toolbox.call before anything runs.
        "eager_input_streaming": True,
    }


__all__ = ["Toolbox", "ToolError", "IGNORED_DIRS"]
