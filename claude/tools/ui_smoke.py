"""Screenshot the WOLF web app on phone and desktop with a fake Claude (no API key, no cost).

Usage: python3 claude/tools/ui_smoke.py [OUTPUT_DIR]
Needs Node.js with Playwright (pre-installed in Claude Code's cloud sandbox). It starts
`wolf serve` on a temporary memory folder with sample data, sends one chat message, opens
every tab (Chat, Schedule, Memory, Settings) and the project page (where it posts a test
thread to a throwaway copy of the hub), then prints any page errors. Look at the PNGs it writes before shipping UI changes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from wolf.assistant import build_wolf  # noqa: E402
from wolf.memory import MemoryStore  # noqa: E402
from wolf.server import WolfApp, make_handler  # noqa: E402

TOKEN = "smoke-test-token-123"
REPLY = ("That's a great goal! Here's a simple **12-week** outline:\n\n1. Weeks 1-4: easy base runs\n"
         "2. Weeks 5-8: add a long run\n3. Weeks 9-12: taper\n\nWant a weekly check-in?")

BROWSER_SCRIPT = r"""
const { chromium, devices } = require('playwright');
(async () => {
  const [base, dir] = process.argv.slice(2);
  const b = await chromium.launch(); const errors = [];
  for (const [name, opts] of [["phone", devices["iPhone 13"]], ["desktop", { viewport: { width: 1200, height: 800 }, colorScheme: "dark" }]]) {
    const ctx = await b.newContext(opts); const p = await ctx.newPage();
    p.on("pageerror", e => errors.push(name + ": " + e.message));
    p.on("console", m => { if (m.type() === "error") errors.push(name + " console: " + m.text()); });
    await p.goto(base + "/?token=TOKEN");
    await p.fill("#input", "I'm training for a half marathon in March"); await p.click("#send");
    await p.waitForSelector(".msg.wolf .chip"); await p.waitForSelector("#due-banner .row");
    await p.screenshot({ path: `${dir}/${name}-chat.png` });
    await p.click('[data-view="schedule"]'); await p.waitForSelector("#cal-events .event");
    await p.screenshot({ path: `${dir}/${name}-schedule.png` });
    await p.click("#add-reminder summary"); await p.fill("#rm-text", "Smoke test reminder"); await p.click("#reminder-form [type=submit]");
    await p.waitForSelector("#reminders li >> text=Smoke test reminder");
    await p.click('[data-view="memory"]'); await p.waitForSelector(".mem-list li .forget"); await p.waitForSelector("#journal li");
    await p.screenshot({ path: `${dir}/${name}-memory.png` });
    await p.click('[data-view="settings"]'); await p.waitForSelector("#personality .choice"); await p.waitForSelector("#abilities .switch");
    await p.screenshot({ path: `${dir}/${name}-settings.png` });
    await p.click("#open-project"); await p.waitForSelector("#plan details");
    await p.screenshot({ path: `${dir}/${name}-project.png` });
    await p.click("#new-thread-btn");
    await p.fill("#tf-title", "Smoke test thread"); await p.fill("#tf-body", "Posted by the UI smoke test.");
    await p.fill("#tf-author", "Tester"); await p.click('#thread-form [type=submit]');
    await p.waitForSelector("#posts li");
    await p.click("#close-project"); await p.waitForSelector("#view-settings.active");
    await ctx.close();
  }
  console.log(JSON.stringify({ errors })); await b.close();
})().catch(e => { console.log(JSON.stringify({ errors: ["script: " + e.message] })); process.exit(1); });
""".replace("TOKEN", TOKEN)


class _Stream:
    def __init__(self, msg):
        self.msg = msg
        self.text_stream = [b.text for b in msg.content if b.type == "text"]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


class FakeClaude:
    """Saves one memory, then replies with REPLY."""

    def __init__(self):
        self.beta = NS(messages=NS(stream=self.stream))

    def stream(self, messages, **_kw):
        if isinstance(messages[-1]["content"], str):
            return _Stream(NS(stop_reason="tool_use", content=[NS(type="tool_use", id="t1", name="remember",
                              input={"text": "Training for a half marathon in March", "tags": ["goals"]})]))
        return _Stream(NS(stop_reason="end_turn", content=[NS(type="text", text=REPLY)]))


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="wolf-ui-")).resolve()
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as home:
        # A throwaway copy of the hub, so the test thread never lands in the real forum.
        hub_copy = Path(home) / "hub"
        shutil.copytree(ROOT / "hub", hub_copy)
        os.environ["WOLF_HUB"] = str(hub_copy)
        store = MemoryStore(Path(home) / "memory")
        store.add("Has a dog named Juno", ["pets"])
        store.update_profile("Goals", "- Run a half marathon in March")
        store.add_journal("Talked about getting back into running.")
        from datetime import datetime, timedelta
        from wolf.components import calendar, reminders
        reminders.add(store.home, "Stretch before the long run", (datetime.now() - timedelta(minutes=5)).isoformat(timespec="minutes"))
        reminders.add(store.home, "Book a physio appointment", (datetime.now() + timedelta(days=2)).isoformat(timespec="minutes"))
        calendar.add_calendar(store.home, "Training", str(ROOT / "tests" / "data" / "sample.ics"))
        client = FakeClaude()
        app = WolfApp(store, agent_factory=lambda: build_wolf(store, client=client, out=lambda s: None))
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app, TOKEN))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(BROWSER_SCRIPT)
        r = subprocess.run(["node", f.name, base, str(out)], capture_output=True, text=True, timeout=180)
        httpd.shutdown()
    try:
        errors = json.loads(r.stdout.strip().splitlines()[-1])["errors"]
    except (ValueError, IndexError, KeyError):
        print(r.stdout + r.stderr)
        return 1
    print(f"Screenshots in {out}")
    print("No page errors." if not errors else "Page errors:\n  " + "\n  ".join(errors))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
