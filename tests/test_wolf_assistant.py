"""Offline tests for the WOLF assistant (no API key or network needed)."""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from wolf_assistant.agent import WolfAgent
from wolf_assistant.cli import main
from wolf_assistant.scanner import scan
from wolf_assistant.tools import Toolbox, ToolError


@pytest.fixture
def repo(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("secret")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def howl():\n    return 'awoo'\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='wolf'\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("x")
    return tmp_path


def test_scan_finds_languages_entry_points_and_skips_ignored(repo):
    m = scan(repo)
    assert "src/main.py" in m.files
    assert not any(f.startswith(("node_modules", ".git")) for f in m.files)
    assert m.languages["Python"] == 1
    assert "src/main.py" in m.entry_points
    assert "pyproject.toml" in m.manifests
    assert "src/main.py" in m.render()


def test_scan_reports_empty_project(tmp_path):
    (tmp_path / "wolf_assistant").mkdir()
    (tmp_path / "wolf_assistant" / "x.py").write_text("")
    assert "no source files yet" in scan(tmp_path).render()


def test_read_and_search(repo):
    tb = Toolbox(repo)
    assert "return 'awoo'" in tb.call("read_file", {"path": "src/main.py"})
    assert "src/main.py:1:" in tb.call("search", {"pattern": r"def \w+"})
    assert "src/main.py" in tb.call("list_files", {"glob": "src/*.py"})


def test_sandbox_blocks_escape_and_git(repo):
    tb = Toolbox(repo)
    with pytest.raises(ToolError):
        tb.call("read_file", {"path": "../outside.txt"})
    with pytest.raises(ToolError):
        tb.call("read_file", {"path": ".git/config"})


def test_input_validation(repo):
    tb = Toolbox(repo)
    with pytest.raises(ToolError, match="Missing"):
        tb.call("read_file", {})
    with pytest.raises(ToolError, match="must be a string"):
        tb.call("read_file", {"path": 3})
    with pytest.raises(ToolError, match="Unexpected"):
        tb.call("read_file", {"path": "src/main.py", "rm": "-rf"})


def test_write_and_run_disabled_by_default(repo):
    tb = Toolbox(repo)
    names = {d["name"] for d in tb.definitions()}
    assert "write_file" not in names and "run_command" not in names
    with pytest.raises(ToolError):
        tb.call("write_file", {"path": "a.txt", "content": "x"})


def test_write_and_run_when_enabled(repo):
    tb = Toolbox(repo, allow_write=True, allow_run=True)
    tb.call("write_file", {"path": "notes/a.txt", "content": "hi"})
    assert (repo / "notes" / "a.txt").read_text() == "hi"
    assert "exit code 0" in tb.call("run_command", {"command": "echo ok"})
    declined = Toolbox(repo, allow_write=True, confirm=lambda _m: False)
    assert "declined" in declined.call("write_file", {"path": "b.txt", "content": "x"})


def test_update_knowledge_replaces_sections(repo):
    tb = Toolbox(repo)
    tb.call("update_knowledge", {"section": "Overview", "content": "v1"})
    tb.call("update_knowledge", {"section": "Risks", "content": "none"})
    tb.call("update_knowledge", {"section": "Overview", "content": "v2"})
    kb = tb.read_knowledge()
    assert kb.count("## Overview") == 1 and "v2" in kb and "v1" not in kb
    assert "## Risks" in kb


def test_cli_map_is_offline(repo, capsys):
    assert main(["--root", str(repo), "map"]) == 0
    assert "src/main.py" in capsys.readouterr().out


# ---------- agent loop with a fake client ----------

class _FakeStream:
    def __init__(self, msg):
        self.msg = msg
        self.text_stream = [b.text for b in msg.content if b.type == "text"]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


class _FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.beta = NS(messages=NS(stream=self._stream))

    def _stream(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeStream(self.responses.pop(0))


def test_agent_runs_tool_loop(repo):
    tool_turn = NS(stop_reason="tool_use", content=[
        NS(type="text", text="Looking."),
        NS(type="tool_use", id="t1", name="read_file", input={"path": "src/main.py"}),
    ])
    final = NS(stop_reason="end_turn", content=[NS(type="text", text="howl() returns 'awoo'.")])
    client = _FakeClient([tool_turn, final])
    out = []
    agent = WolfAgent(Toolbox(repo), client=client, out=out.append)

    answer = agent.ask("What does howl do?")

    assert answer == "howl() returns 'awoo'."
    tool_result = agent.messages[2]["content"][0]
    assert tool_result["tool_use_id"] == "t1" and not tool_result["is_error"]
    assert "awoo" in tool_result["content"]
    req = client.calls[0]
    assert req["model"] == "claude-opus-5-5"
    assert req["thinking"] == {"type": "adaptive"}
    assert "src/main.py" in req["system"][1]["text"]


def test_agent_does_not_run_tools_on_truncated_turn(repo):
    truncated = NS(stop_reason="max_tokens", content=[
        NS(type="tool_use", id="t1", name="write_file", input={"path": "x"}),
    ])
    final = NS(stop_reason="end_turn", content=[NS(type="text", text="done")])
    agent = WolfAgent(Toolbox(repo, allow_write=True), client=_FakeClient([truncated, final]),
                      out=lambda s: None)
    assert agent.ask("go") == "done"
    assert agent.messages[2]["content"][0]["is_error"] is True
    assert not (repo / "x").exists()
