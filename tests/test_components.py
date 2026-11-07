"""Tests for WOLF's swappable components."""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

import wolf.cli as cli
from wolf.assistant import build_system, build_toolkit, build_wolf, finish_conversation
from wolf.components import Component, ComponentError, Toolkit, available
from wolf.config import load_config
from wolf.loop import ToolError, tool
from wolf.memory import MemoryStore

PLUGIN = '''
from wolf.components import Component
from wolf.loop import tool

class Mood(Component):
    name = "mood"
    description = "Tracks how the user feels."

    def tools(self):
        return [tool("log_mood", "Log the user's mood.", {"mood": {"type": "string"}}, required=["mood"])]

    def call(self, name, args):
        return "logged " + args["mood"]

    def instructions(self):
        return "Ask about mood now and then."
'''


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    return MemoryStore(tmp_path / "home")


def test_default_components(store):
    kit = build_toolkit(store)
    assert [c.name for c in kit.components] == ["memory", "web_search", "clock", "reminders"]
    names = {d["name"] for d in kit.definitions()}
    assert {"remember", "recall", "current_time"} <= names
    assert kit.server_tools()[0]["type"] == "web_search_20260209"
    assert "current_time" not in build_toolkit(store, ["memory"]).definitions().__repr__()


def test_system_prompt_is_assembled_from_components(store):
    store.add("Has a dog named Juno")
    stable, snapshot = (b["text"] for b in build_system(store))
    assert "You are WOLF" in stable and "## memory" in stable and "## clock" in stable
    assert "Juno" in snapshot
    # without memory there is no memory guidance and no snapshot block
    blocks = build_system(store, ["clock"])
    assert len(blocks) == 1 and "remember" not in blocks[0]["text"]


def test_clock_tool(store):
    out = build_toolkit(store, ["clock"]).call("current_time", {})
    assert any(day in out for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"))


def test_drop_in_plugin_and_cli(store, capsys):
    plugins = store.home / "components"
    plugins.mkdir()
    (plugins / "mood.py").write_text(PLUGIN)
    assert available(store.home)["mood"] == "Tracks how the user feels."

    home = str(store.home)
    assert cli.main(["--home", home, "components", "enable", "mood"]) == 0
    assert load_config(store.home)["components"] == ["memory", "web_search", "clock", "reminders", "mood"]
    kit = build_toolkit(store)
    assert kit.call("log_mood", {"mood": "great"}) == "logged great"
    with pytest.raises(ToolError):
        kit.call("log_mood", {})  # validated against the plugin's schema
    assert "## mood" in build_system(store)[0]["text"]

    assert cli.main(["--home", home, "components", "disable", "web_search"]) == 0
    assert "web_search" not in load_config(store.home)["components"]
    assert cli.main(["--home", home, "components"]) == 0
    out = capsys.readouterr().out
    assert "* mood" in out and "  web_search" in out
    assert cli.main(["--home", home, "components", "enable", "nope"]) == 1
    assert cli.main(["--home", home, "components", "reset"]) == 0
    assert "components" not in load_config(store.home)


def test_swap_memory_for_another_implementation(store):
    """Interchangeable: a different memory component replaces the built-in one entirely."""
    class NotebookMemory(Component):
        name = "memory"
        description = "Keeps memory in a notebook."

        def tools(self):
            return [tool("remember", "Write it down.", {"text": {"type": "string"}}, required=["text"])]

        def call(self, name, args):
            return "noted"

    import sys
    import types
    mod = types.ModuleType("my_notebook")
    mod.NotebookMemory = NotebookMemory
    sys.modules["my_notebook"] = mod
    kit = build_toolkit(store, ["my_notebook:NotebookMemory", "clock"])
    assert kit.call("remember", {"text": "x"}) == "noted"
    assert store.all() == []  # the built-in store was never touched


def test_tool_name_clash_is_reported(store):
    with pytest.raises(ComponentError, match="both define a tool named 'remember'"):
        build_toolkit(store, ["memory", "memory"])


def test_broken_plugin_does_not_hide_others(store):
    (store.home / "components").mkdir()
    (store.home / "components" / "broken.py").write_text("raise RuntimeError('oops')")
    found = available(store.home)
    assert "can't load" in found["broken"] and "memory" in found


def test_finish_conversation_runs_component_hooks(store):
    class Hook(Component):
        name = "hook"

        def on_end(self, agent):
            return "hook summary"

    kit = Toolkit([Hook(NS(store=store))])
    agent = NS(toolbox=kit)
    assert finish_conversation(agent) == "hook summary"


def test_web_flag_still_disables_search(store):
    agent = build_wolf(store, web=False, client=object())
    assert agent.server_tools == []
