"""Claude's workspace inside WOLF (`claude/`): handoffs, a personal changelog, and tools.

Any Claude session (Claude Code, the `wolf-dev` CLI, or a plain chat with the output pasted
in) can absorb everything earlier sessions learned by reading one document:

    python3 -m wolf_assistant brief

The briefing is assembled from files that live in the repo, so it travels with the code:
  claude/HANDOFF.md      where things stand, what's next, and the previous session's thinking
  claude/CHANGELOG.md    what each session did and why, newest first
  claude/TOOLS.md        tools and services Claude uses outside this repo
  claude/tools/          helper scripts (each starts with a one-line description)
  docs/wolf/KNOWLEDGE.md architecture, conventions, decisions, open questions
  hub/                   the production plan and the research forum (shared with people)
plus live facts: git state, the component list, the repo map, and (optionally) test results.
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import date
from pathlib import Path

from .scanner import scan

WORKSPACE = "claude"
TOOL_SUFFIXES = {".py": [sys.executable], ".sh": ["bash"], ".js": ["node"]}

PROTOCOL = """\
How to work in this repo (read this first, every session):
1. Read this whole briefing before changing anything. It is the memory of every earlier session.
2. Work on the branch named in "Repository state". Run `python3 claude/tools/check.py` before
   committing; never push with failing checks.
3. As you go, record durable facts in docs/wolf/KNOWLEDGE.md (replace stale text, don't append).
4. Keep the production plan honest (`wolf-dev plan set ITEM STATUS`) and read the forum for
   questions addressed to AI; answer with `wolf-dev forum reply`. Report build progress with
   `python3 claude/tools/progress.py` (WOLF's Project tab shows it).
5. Before you finish: add a changelog entry (`python3 -m wolf_assistant log "..."`), then
   rewrite claude/HANDOFF.md so the next session can start cold: what's done, what's next,
   what you'd do and why, and anything you're unsure of. Commit both with your work.
6. This repository is public. Never commit personal data about the owner or anything learned
   from their accounts (email, files, chats). WOLF's memory of them lives in ~/.wolf only.
"""


def ws(root: Path) -> Path:
    return root / WORKSPACE


def _read(path: Path) -> str:
    try:
        return path.read_text("utf-8").strip()
    except OSError:
        return f"(missing: {path.name})"


def _git(root: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=20)
        return (r.stdout or r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"(git unavailable: {e})"


# ---------------------------------------------------------------- changelog

def changelog_entries(root: Path) -> list[tuple[str, str]]:
    """[(heading, body)] for each `## ` section, newest first (file order)."""
    text = _read(ws(root) / "CHANGELOG.md")
    parts = re.split(r"^## ", text, flags=re.M)[1:]
    return [(p.split("\n", 1)[0].strip(), p.split("\n", 1)[1].strip() if "\n" in p else "") for p in parts]


def add_log(root: Path, text: str, today: date | None = None) -> str:
    """Add a bullet under today's heading (created at the top if needed)."""
    text = " ".join(text.split())
    if not text:
        raise ValueError("Empty changelog entry")
    path = ws(root) / "CHANGELOG.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = path.read_text("utf-8") if path.exists() else "# Claude's changelog\n\nNewest first.\n"
    heading = f"## {(today or date.today()).isoformat()}"
    bullet = f"- {text}\n"
    if heading in content:
        idx = content.index(heading)
        end = content.find("\n## ", idx + len(heading))
        end = len(content) if end == -1 else end + 1
        section = content[idx:end].rstrip("\n") + "\n" + bullet
        content = content[:idx] + section + ("\n" if end < len(content) else "") + content[end:]
    else:
        m = re.search(r"^## ", content, flags=re.M)
        block = f"{heading}\n\n{bullet}\n"
        content = content[:m.start()] + block + content[m.start():] if m else content.rstrip() + "\n\n" + block
    path.write_text(content.rstrip() + "\n", "utf-8")
    return heading[3:]


# ---------------------------------------------------------------- tools

def list_tools(root: Path) -> list[tuple[str, str]]:
    """[(name, description)] for scripts in claude/tools (first docstring or comment line)."""
    out = []
    folder = ws(root) / "tools"
    for path in sorted(folder.glob("*")) if folder.is_dir() else []:
        if path.suffix not in TOOL_SUFFIXES or path.name.startswith("_"):
            continue
        desc = ""
        for line in path.read_text("utf-8", errors="ignore").splitlines()[:8]:
            line = line.strip().lstrip("#/").strip().strip('"').strip("'").strip()
            if line and not line.startswith("!") and not line.startswith("use strict"):
                desc = line
                break
        out.append((path.stem, desc))
    return out


def run_tool(root: Path, name: str, args: list[str]) -> int:
    folder = ws(root) / "tools"
    matches = [p for p in folder.glob(f"{name}.*") if p.suffix in TOOL_SUFFIXES]
    if not matches:
        print(f"No tool named '{name}'. Run `wolf-dev tools` to see them.", file=sys.stderr)
        return 1
    path = matches[0]
    return subprocess.call([*TOOL_SUFFIXES[path.suffix], str(path), *args], cwd=root)


# ---------------------------------------------------------------- briefing

def _components_summary() -> str:
    try:
        from wolf.components import BUILTINS, DEFAULT_COMPONENTS
        return (f"Built-in components: {', '.join(BUILTINS)} (default on: {', '.join(DEFAULT_COMPONENTS)}). "
                "Interface: wolf/components/__init__.py.")
    except Exception as e:
        return f"(couldn't load components: {e})"


def _hub_section(root: Path, which: str) -> str:
    try:
        from wolf import hub
        folder = root / "hub"
        if not folder.is_dir():
            return "(no hub/ folder in this checkout)"
        return hub.plan_text(folder) if which == "plan" else hub.forum_text(5, folder)
    except Exception as e:
        return f"(couldn't read the hub: {e})"


def brief(root: Path, tests: bool = False, changelog_sessions: int = 3, tree_files: int = 120) -> str:
    """The full briefing a new Claude session reads to pick up where the last one stopped."""
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    status = _git(root, "status", "--short") or "(clean)"
    log = _git(root, "log", "--oneline", "-10")
    entries = changelog_entries(root)[:changelog_sessions]
    changelog = "\n\n".join(f"### {h}\n{b}" for h, b in entries) or "(no entries yet)"
    tools = "\n".join(f"- `{n}`: {d}" for n, d in list_tools(root)) or "(none)"

    sections = [
        ("WOLF briefing for Claude", PROTOCOL),
        ("Handoff from the previous session (claude/HANDOFF.md)", _read(ws(root) / "HANDOFF.md")),
        (f"Recent changelog (claude/CHANGELOG.md, last {changelog_sessions} days)", changelog),
        ("Knowledge base (docs/wolf/KNOWLEDGE.md)", _read(root / "docs/wolf/KNOWLEDGE.md")),
        ("Production plan (hub/plan.json; `wolf-dev plan`)", _hub_section(root, "plan")),
        ("Research forum, recent threads (hub/forum/; `wolf-dev forum`)", _hub_section(root, "forum")),
        ("Tools", "Scripts in claude/tools (run with `python3 -m wolf_assistant tools run NAME`):\n"
                  + tools + "\n\nOutside the repo (claude/TOOLS.md):\n" + _read(ws(root) / "TOOLS.md")),
        ("Repository state", f"Branch: {branch}\n\nUncommitted changes:\n{status}\n\nRecent commits:\n{log}\n\n"
                             + _components_summary()),
    ]
    if tests:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=root, capture_output=True, text=True)
        sections.append(("Test results", "\n".join((r.stdout or r.stderr).strip().splitlines()[-15:])))
    sections.append(("Repository map", scan(root).render(max_tree=tree_files)))

    out = []
    for title, body in sections:
        out.append(f"{'=' * 78}\n# {title}\n{'=' * 78}\n\n{body.strip()}\n")
    return "\n".join(out)
