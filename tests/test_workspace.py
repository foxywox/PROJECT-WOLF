"""Tests for Claude's workspace (claude/) and the wolf-dev brief/log/tools commands."""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

import pytest

from wolf_assistant import workspace
from wolf_assistant.cli import main

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    ws = tmp_path / "claude"
    (ws / "tools").mkdir(parents=True)
    (ws / "HANDOFF.md").write_text("# Handoff\n\nNext: build the calendar component.\n")
    (ws / "TOOLS.md").write_text("- Progress window\n")
    (ws / "tools" / "hello.py").write_text('"""Say hello."""\nimport sys\nprint("hello", *sys.argv[1:])\n')
    (ws / "tools" / "_private.py").write_text('"""Hidden helper."""\n')
    (tmp_path / "docs" / "wolf").mkdir(parents=True)
    (tmp_path / "docs" / "wolf" / "KNOWLEDGE.md").write_text("# WOLF Knowledge Base\n\nUses components.\n")
    return tmp_path


def test_changelog_newest_day_first(repo):
    workspace.add_log(repo, "first thing", today=date(2026, 1, 1))
    workspace.add_log(repo, "second thing", today=date(2026, 1, 1))
    workspace.add_log(repo, "next day", today=date(2026, 1, 2))
    entries = workspace.changelog_entries(repo)
    assert [h for h, _ in entries] == ["2026-01-02", "2026-01-01"]
    assert entries[1][1] == "- first thing\n- second thing"
    with pytest.raises(ValueError):
        workspace.add_log(repo, "   ")


def test_tools_listing_and_running(repo, capfd):
    assert workspace.list_tools(repo) == [("hello", "Say hello.")]
    assert main(["--root", str(repo), "tools", "run", "hello", "wolf"]) == 0
    assert "hello wolf" in capfd.readouterr().out
    assert main(["--root", str(repo), "tools", "run", "nope"]) == 1


def test_brief_contains_everything_a_new_session_needs(repo):
    workspace.add_log(repo, "Built the clock component")
    text = workspace.brief(repo)
    for expected in ("How to work in this repo", "Next: build the calendar component",
                     "Built the clock component", "Uses components", "`hello`: Say hello.",
                     "Progress window", "Branch:", "Built-in components: memory", "Repository map"):
        assert expected in text, expected


def test_cli_brief_and_log(repo, capsys):
    assert main(["--root", str(repo), "log", "did", "a", "thing"]) == 0
    assert main(["--root", str(repo), "brief"]) == 0
    assert "did a thing" in capsys.readouterr().out


def test_real_workspace_is_complete():
    """The committed workspace has every file the briefing relies on, and real tools."""
    for name in ("README.md", "HANDOFF.md", "CHANGELOG.md", "TOOLS.md"):
        assert (REPO / "claude" / name).is_file(), name
    names = {n for n, d in workspace.list_tools(REPO) if d}
    assert {"check", "progress", "ui_smoke"} <= names
    assert workspace.changelog_entries(REPO)
