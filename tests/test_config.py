"""Tests for `wolf setup` and credential handling (no network)."""

from __future__ import annotations

import pytest

import wolf.cli as cli
from wolf import config
from wolf.memory import MemoryStore
from wolf.server import load_token


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("WOLF_TOKEN", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))  # no `ant` profile
    return MemoryStore(tmp_path / "home")


def test_saved_key_is_private_and_used(store, monkeypatch):
    assert not config.has_credentials(store.home)
    path = config.save_config({"api_key": "sk-ant-saved"}, store.home)
    assert oct(path.stat().st_mode)[-3:] == "600"
    assert config.has_credentials(store.home)
    assert config.make_client(store.home).api_key == "sk-ant-saved"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env")
    assert config.make_client(store.home).api_key == "sk-ant-env"  # environment wins


def test_setup_saves_a_working_key(store, monkeypatch, capsys):
    monkeypatch.setattr(cli, "check_key", lambda key, model: None if key == "good" else "rejected")
    answers = iter(["bad", "good"])
    assert cli.setup(store, "claude-opus-5-5", read_secret=lambda _p: next(answers)) == 0
    assert config.load_config(store.home)["api_key"] == "good"
    assert "rejected" in capsys.readouterr().out


def test_setup_gives_up_after_three_bad_keys(store, monkeypatch):
    monkeypatch.setattr(cli, "check_key", lambda key, model: "rejected")
    assert cli.setup(store, "m", read_secret=lambda _p: "bad") == 1
    assert "api_key" not in config.load_config(store.home)


def test_setup_cancel(store):
    assert cli.setup(store, "m", read_secret=lambda _p: "") == 1


def test_chat_without_credentials_explains_what_to_do(store, capsys):
    # pytest's stdin isn't a terminal, so WOLF prints guidance instead of prompting
    assert cli.main(["--home", str(store.home), "ask", "hi"]) == 2
    assert "wolf setup" in capsys.readouterr().err
    # offline commands still work without a key
    assert cli.main(["--home", str(store.home), "memory"]) == 0


def test_wolf_token_env(store, monkeypatch):
    monkeypatch.setenv("WOLF_TOKEN", "a-long-enough-token-123")
    assert load_token(store) == "a-long-enough-token-123"
    monkeypatch.setenv("WOLF_TOKEN", "short")
    with pytest.raises(SystemExit):
        load_token(store)
