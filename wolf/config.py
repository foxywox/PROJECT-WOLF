"""WOLF settings and Claude credentials.

`wolf setup` saves your API key in `$WOLF_HOME/config.json` (owner-only permissions), so you
don't have to export ANTHROPIC_API_KEY in every terminal. An ANTHROPIC_API_KEY or
ANTHROPIC_AUTH_TOKEN in the environment always wins over the saved key (that's how hosted
deployments pass the key in).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import anthropic

from .memory import default_home

KEYS_URL = "https://console.anthropic.com/settings/keys"
NOT_SET_UP = (
    "WOLF isn't connected to Claude yet. Run `wolf setup` and paste your Anthropic API key "
    f"(create one at {KEYS_URL})."
)


def _path(home: str | Path | None) -> Path:
    return (Path(home).expanduser() if home else default_home()) / "config.json"


def load_config(home: str | Path | None = None) -> dict[str, Any]:
    p = _path(home)
    try:
        data = json.loads(p.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(data: dict[str, Any], home: str | Path | None = None) -> Path:
    p = _path(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    # Create with owner-only permissions before any secret is written.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(p)
    return p


def _env_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def make_client(home: str | Path | None = None) -> anthropic.Anthropic:
    if not _env_credentials():
        key = load_config(home).get("api_key")
        if key:
            return anthropic.Anthropic(api_key=key)
    return anthropic.Anthropic()  # env vars, or an `ant auth login` profile


def has_credentials(home: str | Path | None = None) -> bool:
    if _env_credentials() or load_config(home).get("api_key"):
        return True
    # `ant auth login` stores a profile the SDK picks up automatically.
    cfg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "anthropic"
    return cfg.is_dir() and any(cfg.iterdir())


def check_key(key: str, model: str) -> str | None:
    """Return None if the key works, else a short reason. Costs no tokens."""
    try:
        anthropic.Anthropic(api_key=key).models.retrieve(model)
        return None
    except anthropic.AuthenticationError:
        return "That key was rejected. Check that you copied all of it."
    except anthropic.PermissionDeniedError:
        return "That key works but doesn't have access to the model WOLF uses."
    except anthropic.APIConnectionError:
        return "Couldn't reach Anthropic. Check your internet connection."
    except anthropic.APIStatusError as e:
        return f"Anthropic returned an error ({e.status_code})."
