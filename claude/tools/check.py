"""Run every check before committing: tests, Python syntax, and the web app's JavaScript."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(label: str, cmd: list[str]) -> bool:
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    ok = r.returncode == 0
    tail = (r.stdout + r.stderr).strip().splitlines()[-1:] if (r.stdout or r.stderr) else []
    print(f"{'PASS' if ok else 'FAIL'}  {label}{'  -  ' + tail[0] if tail else ''}")
    if not ok:
        print((r.stdout + r.stderr)[-3000:])
    return ok


def main() -> int:
    results = [
        run("python compiles", [sys.executable, "-m", "compileall", "-q", "wolf", "wolf_assistant", "claude/tools"]),
        run("tests", [sys.executable, "-m", "pytest", "-q"]),
    ]
    if shutil.which("node"):
        for js in sorted((ROOT / "wolf" / "web").glob("*.js")):
            results.append(run(f"javascript {js.name}", ["node", "--check", str(js)]))
    else:
        print("SKIP  javascript (node not installed)")
    print("\nAll checks passed." if all(results) else "\nSome checks failed. Don't commit yet.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
