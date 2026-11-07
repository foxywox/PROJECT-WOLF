"""WOLF's personality: how it sounds, chosen by the owner.

Pick a preset, or write your own in plain words (`$WOLF_HOME/personality.md`). The choice is
stored in config.json as "personality": "<preset id>" or "custom". WOLF's boundaries (no
storing secrets, honesty) are not part of the personality and always apply.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import load_config, save_config

DEFAULT = "balanced"
MAX_CUSTOM = 4000

PRESETS: dict[str, dict[str, str]] = {
    "balanced": {
        "name": "Balanced",
        "summary": "Warm, direct and practical.",
        "text": "Be warm, direct and practical. Use what you know about the user to tailor answers "
                "without reciting it back. Ask a short clarifying question when it would change "
                "your answer.",
    },
    "coach": {
        "name": "Coach",
        "summary": "Encouraging, keeps you accountable, always ends with a next step.",
        "text": "Be an encouraging coach. Celebrate progress specifically, not generically. Gently "
                "hold the user to what they said they'd do, and notice when they're avoiding "
                "something. End most replies with one small, concrete next step they can take today.",
    },
    "calm": {
        "name": "Calm",
        "summary": "Gentle, unhurried and reflective.",
        "text": "Be calm and unhurried. Speak gently and plainly, leave room for the user to think, "
                "and reflect back what you hear before offering advice. Never pile on tasks; one "
                "thing at a time.",
    },
    "playful": {
        "name": "Playful",
        "summary": "Light humor and dry wit, still genuinely useful.",
        "text": "Be playful: light humor and dry wit, the occasional unexpected comparison. Keep "
                "jokes short and never at the user's expense, and drop the humor entirely when "
                "they're stressed, sad or dealing with something serious. Usefulness comes first.",
    },
    "brief": {
        "name": "Brief",
        "summary": "As few words as possible.",
        "text": "Be brief. Answer in as few words as will do, usually one to three sentences. Use "
                "lists only when they save words. Skip pleasantries. Expand only when asked.",
    },
}


def custom_path(home: Path) -> Path:
    return home / "personality.md"


def custom_text(home: Path) -> str:
    try:
        return custom_path(home).read_text("utf-8").strip()[:MAX_CUSTOM]
    except OSError:
        return ""


def current(home: Path) -> str:
    choice = load_config(home).get("personality", DEFAULT)
    if choice == "custom" and custom_text(home):
        return "custom"
    return choice if choice in PRESETS else DEFAULT


def text(home: Path) -> str:
    """The style instructions for WOLF's system prompt."""
    choice = current(home)
    return custom_text(home) if choice == "custom" else PRESETS[choice]["text"]


def choose(home: Path, choice: str, custom: str | None = None) -> str:
    """Set the personality. `custom` (with choice "custom") saves the owner's own description."""
    if choice == "custom":
        if custom is not None:
            custom = custom.strip()
            if not custom:
                raise ValueError("Describe the personality you want first.")
            if len(custom) > MAX_CUSTOM:
                raise ValueError(f"Keep the description under {MAX_CUSTOM} characters.")
            custom_path(home).write_text(custom + "\n", "utf-8")
        elif not custom_text(home):
            raise ValueError("Describe the personality you want first.")
    elif choice not in PRESETS:
        raise ValueError(f"Unknown personality '{choice}'. Choose one of: {', '.join(PRESETS)}, custom.")
    config = load_config(home)
    config["personality"] = choice
    save_config(config, home)
    return choice


def overview(home: Path) -> dict[str, Any]:
    return {
        "current": current(home),
        "presets": [{"id": k, "name": v["name"], "summary": v["summary"]} for k, v in PRESETS.items()],
        "custom": custom_text(home),
    }
