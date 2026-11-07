"""`wolf-dev` command-line entry point (development assistant for this repo).

Examples:
  wolf-dev map                      # offline repo map (no API call)
  wolf-dev analyze                  # full analysis, saved to the knowledge base
  wolf-dev ask "How does X work?"   # one question
  wolf-dev chat                     # interactive session
  wolf-dev learn                    # refresh the knowledge base
  wolf-dev review --allow-run       # review recent changes (uses git)

Claude's workspace (claude/), all offline:
  wolf-dev brief [--tests]          # everything a new Claude session needs to pick up the work
  wolf-dev log "what I did and why" # add to Claude's changelog (claude/CHANGELOG.md)
  wolf-dev tools [run NAME ...]     # list or run Claude's helper scripts (claude/tools/)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .prompts import TASKS
from . import workspace
from .scanner import scan
from .tools import Toolbox


def _find_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / ".git").exists():
            return p
    return start


def _confirm(auto_yes: bool):
    def ask(msg: str) -> bool:
        if auto_yes:
            return True
        try:
            return input(f"\n[wolf] {msg} [y/N] ").strip().lower() in {"y", "yes"}
        except EOFError:
            return False
    return ask


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="wolf-dev", description="PROJECT WOLF development assistant")
    ap.add_argument("--version", action="version", version=f"wolf-dev {__version__}")
    ap.add_argument("--root", default=None, help="Repository root (default: nearest git root)")
    ap.add_argument("--model", default=None, help="Claude model ID (default: claude-opus-5-5)")
    ap.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--allow-write", action="store_true", help="Let the assistant create/edit files")
    ap.add_argument("--allow-run", action="store_true", help="Let the assistant run shell commands")
    ap.add_argument("-y", "--yes", action="store_true", help="Don't ask before each write/command")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("map", help="Print the offline repository map")
    sub.add_parser("analyze", help="Full analysis of WOLF; saves findings to the knowledge base")
    sub.add_parser("learn", help="Refresh the knowledge base from the current code")
    sub.add_parser("review", help="Review recent changes (best with --allow-run)")
    p_ask = sub.add_parser("ask", help="Ask one question")
    p_ask.add_argument("question", nargs="+")
    sub.add_parser("chat", help="Interactive session")
    p_brief = sub.add_parser("brief", help="Print the full briefing for a new Claude session")
    p_brief.add_argument("--tests", action="store_true", help="Also run the test suite and include results")
    p_log = sub.add_parser("log", help="Add an entry to Claude's changelog")
    p_log.add_argument("text", nargs="+")
    p_tools = sub.add_parser("tools", help="List Claude's helper scripts, or run one")
    p_tools.add_argument("action", nargs="?", choices=["list", "run"], default="list")
    p_tools.add_argument("name", nargs="?")
    p_tools.add_argument("args", nargs=argparse.REMAINDER)
    args = ap.parse_args(argv)

    root = Path(args.root).resolve() if args.root else _find_root(Path.cwd())

    if args.cmd == "map":
        print(scan(root).render())
        return 0
    if args.cmd == "brief":
        print(workspace.brief(root, tests=args.tests))
        return 0
    if args.cmd == "log":
        day = workspace.add_log(root, " ".join(args.text))
        print(f"Logged under {day} in {workspace.WORKSPACE}/CHANGELOG.md")
        return 0
    if args.cmd == "tools":
        if args.action == "run":
            if not args.name:
                print("Which tool? Example: wolf-dev tools run check", file=sys.stderr)
                return 1
            return workspace.run_tool(root, args.name, args.args)
        for name, desc in workspace.list_tools(root):
            print(f"  {name:<12} {desc}")
        return 0

    from .agent import DEFAULT_MODEL, WolfAgent  # imported lazily so `wolf map` works offline

    toolbox = Toolbox(root, allow_write=args.allow_write, allow_run=args.allow_run,
                      confirm=_confirm(args.yes))
    agent = WolfAgent(toolbox, model=args.model or DEFAULT_MODEL, effort=args.effort)

    try:
        print()
        if args.cmd in TASKS:
            agent.ask(TASKS[args.cmd])
        elif args.cmd == "ask":
            agent.ask(" ".join(args.question))
        elif args.cmd == "chat":
            print("WOLF Assistant — type your question, or 'exit' to quit.")
            while True:
                try:
                    q = input("\nwolf> ").strip()
                except EOFError:
                    break
                if q.lower() in {"exit", "quit", ":q"}:
                    break
                if q:
                    print()
                    agent.ask(q)
        print()
    except KeyboardInterrupt:
        print("\n[interrupted]")
        return 130
    except Exception as e:  # surface API/auth errors readably
        import anthropic
        if isinstance(e, anthropic.AuthenticationError):
            print("\n[wolf] Authentication failed. Set ANTHROPIC_API_KEY or run `ant auth login`.",
                  file=sys.stderr)
            return 2
        if isinstance(e, anthropic.APIStatusError):
            print(f"\n[wolf] API error {e.status_code}: {e.message}", file=sys.stderr)
            return 1
        if isinstance(e, anthropic.APIConnectionError):
            print(f"\n[wolf] Could not reach the API: {e}", file=sys.stderr)
            return 1
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
