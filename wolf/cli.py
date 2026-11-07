"""`wolf`: talk to WOLF, your personal assistant.

  wolf                        start a conversation (same as `wolf chat`)
  wolf ask "..."              one question, then WOLF reflects and saves what it learned
  wolf memory [query]         list (or search) what WOLF remembers; no API call
  wolf forget m12             delete a memory
  wolf profile                show WOLF's profile of you
  wolf journal                show recent conversation summaries
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from . import __version__
from .memory import MemoryStore


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="wolf", description="WOLF: your personal AI assistant")
    ap.add_argument("--version", action="version", version=f"wolf {__version__}")
    ap.add_argument("--home", default=None, help="Where WOLF keeps its memory (default: $WOLF_HOME or ~/.wolf)")
    ap.add_argument("--model", default=None, help="Claude model ID (default: claude-opus-5-5)")
    ap.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--no-web", action="store_true", help="Disable web search")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("chat", help="Start a conversation (default)")
    p_ask = sub.add_parser("ask", help="Ask one question")
    p_ask.add_argument("question", nargs="+")
    p_mem = sub.add_parser("memory", help="List or search memories")
    p_mem.add_argument("query", nargs="*")
    p_forget = sub.add_parser("forget", help="Delete a memory by id")
    p_forget.add_argument("id")
    sub.add_parser("profile", help="Show your profile")
    sub.add_parser("journal", help="Show recent conversation summaries")
    args = ap.parse_args(argv)

    store = MemoryStore(args.home)
    cmd = args.cmd or "chat"

    # ---- offline commands ----
    if cmd == "memory":
        mems = store.search(" ".join(args.query)) if args.query else store.recent(10_000)
        print("\n".join(m.line() for m in mems) or "(no memories)")
        return 0
    if cmd == "forget":
        try:
            print(f"Forgot: {store.forget(args.id).text}")
            return 0
        except KeyError:
            print(f"No memory with id {args.id}", file=sys.stderr)
            return 1
    if cmd == "profile":
        print(store.profile() or "(empty: talk to WOLF and it will build this)")
        return 0
    if cmd == "journal":
        print("\n".join(store.recent_journal(30)) or "(no conversations yet)")
        return 0

    # ---- conversations ----
    import anthropic

    from .assistant import build_wolf, reflect
    from .loop import DEFAULT_MODEL

    agent = build_wolf(store, web=not args.no_web, model=args.model or DEFAULT_MODEL, effort=args.effort)
    stamp = f"[{datetime.now().strftime('%A %Y-%m-%d %H:%M')}] "  # kept out of the cached system prompt
    try:
        if cmd == "ask":
            agent.ask(stamp + " ".join(args.question))
        else:
            print("WOLF is listening. Type 'bye' to end (WOLF saves what it learned).")
            first = True
            while True:
                try:
                    q = input("\nyou> ").strip()
                except EOFError:
                    break
                if q.lower() in {"bye", "exit", "quit", ":q"}:
                    break
                if q:
                    agent.ask((stamp if first else "") + q)
                    first = False
        print()
        summary = reflect(agent, store)
        if summary:
            print(f"[saved to journal] {summary}")
    except KeyboardInterrupt:
        print("\n[interrupted: nothing further saved]")
        return 130
    except anthropic.AuthenticationError:
        print("\n[wolf] Authentication failed. Set ANTHROPIC_API_KEY or run `ant auth login`.", file=sys.stderr)
        return 2
    except anthropic.APIStatusError as e:
        print(f"\n[wolf] API error {e.status_code}: {e.message}", file=sys.stderr)
        return 1
    except anthropic.APIConnectionError as e:
        print(f"\n[wolf] Could not reach the API: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
