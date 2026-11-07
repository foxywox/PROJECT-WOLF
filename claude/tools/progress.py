"""Update build progress: WOLF's Project tab shows it, and claude/TOOLS.md says how to mirror it to the live window."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "hub" / "progress.json"  # shown in WOLF's Project tab


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("percent", type=int, help="0-100; 100 marks the work done (the pup howls)")
    ap.add_argument("active", type=int, help="index of the step in progress (0-based)")
    ap.add_argument("current", help="one line: what's happening right now")
    ap.add_argument("note", nargs="?", help="optional line for the 'Latest notes' list")
    ap.add_argument("--steps", help="'|'-separated plan; starts a new run (clears notes)")
    ap.add_argument("--title", help="window title")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args()

    d = json.loads(a.out.read_text()) if a.out.exists() and not a.steps else {"log": []}
    if a.steps:
        d["plan"] = [s.strip() for s in a.steps.split("|") if s.strip()]
    if a.title:
        d["title"] = a.title
    now = int(time.time() * 1000)
    done = a.percent >= 100
    d.update(percent=a.percent, current=a.current, updated=now, status="done" if done else "working",
             steps=[{"label": s, "state": "done" if done or i < a.active else "active" if i == a.active else "todo"}
                    for i, s in enumerate(d.get("plan", []))])
    if a.note:
        d["log"] = (d.get("log", []) + [{"t": now, "text": a.note}])[-12:]
    a.out.write_text(json.dumps(d))
    print(a.out)


if __name__ == "__main__":
    main()
