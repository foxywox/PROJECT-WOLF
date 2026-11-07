"""Offline tests for WOLF, the personal assistant (no API key or network needed)."""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from wolf.assistant import MemoryTools, build_system, build_wolf, reflect
from wolf.cli import main
from wolf.loop import ToolError
from wolf.memory import MemoryStore


@pytest.fixture
def store(tmp_path):
    return MemoryStore(tmp_path / "wolfhome")


def test_add_dedupes_and_assigns_ids(store):
    a = store.add("Prefers concise answers", ["style"])
    b = store.add("prefers concise answers")
    c = store.add("Training for a half marathon in March", ["health", "goals"])
    assert a.id == b.id == "m1" and c.id == "m2"
    assert len(store.all()) == 2


def test_search_ranks_by_terms_and_tags(store):
    store.add("Has a dog named Juno", ["pets"])
    store.add("Training for a half marathon in March", ["health"])
    store.add("Works as a nurse on night shifts", ["work"])
    assert store.search("running marathon")[0].text.startswith("Training")
    assert store.search("pets")[0].text == "Has a dog named Juno"
    assert store.search("quantum chromodynamics") == []


def test_update_forget_and_missing_id(store):
    m = store.add("Lives in Denver")
    store.update(m.id, "Lives in Boulder")
    assert store.all()[0].text == "Lives in Boulder"
    store.forget(m.id)
    assert store.all() == []
    with pytest.raises(KeyError):
        store.forget("m99")


def test_profile_sections_replace(store):
    store.update_profile("Goals", "Run a half marathon")
    store.update_profile("Preferences", "Short answers")
    store.update_profile("Goals", "Run a full marathon")
    p = store.profile()
    assert p.count("## Goals") == 1 and "full marathon" in p and "half" not in p


def test_journal(store):
    store.add_journal("Talked about\n training plans.")
    assert store.recent_journal()[-1].endswith("Talked about training plans.")


def test_memory_tools_validate_and_run(store):
    tools = MemoryTools(store)
    assert "Saved m1" in tools.call("remember", {"text": "Likes jazz", "tags": ["music"]})
    assert "Likes jazz" in tools.call("recall", {"query": "music"})
    with pytest.raises(ToolError):
        tools.call("remember", {"text": "x", "tags": "music"})  # tags must be a list
    with pytest.raises(ToolError):
        tools.call("forget", {"id": "m42"})


def test_system_prompt_includes_what_wolf_knows(store):
    store.add("Has a dog named Juno")
    store.update_profile("Identity", "Name: Sam")
    store.add_journal("First chat")
    ctx = build_system(store)[1]["text"]
    assert "Name: Sam" in ctx and "Juno" in ctx and "First chat" in ctx


def test_cli_offline_commands(store, capsys):
    store.add("Likes jazz", ["music"])
    home = str(store.home)
    assert main(["--home", home, "memory"]) == 0
    assert "m1: Likes jazz [music]" in capsys.readouterr().out
    assert main(["--home", home, "forget", "m1"]) == 0
    assert main(["--home", home, "forget", "m1"]) == 1
    assert main(["--home", home, "profile"]) == 0


# ---------- conversation loop with a fake client ----------

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


def test_wolf_learns_during_conversation_and_reflects(store):
    learn = NS(stop_reason="tool_use", content=[
        NS(type="tool_use", id="t1", name="remember",
           input={"text": "Has a dog named Juno", "tags": ["pets"]}),
    ])
    reply = NS(stop_reason="end_turn", content=[NS(type="text", text="Juno sounds lovely!")])
    paused = NS(stop_reason="pause_turn", content=[NS(type="text", text="")])
    summary = NS(stop_reason="end_turn", content=[NS(type="text", text="User introduced their dog Juno.")])
    client = _FakeClient([learn, reply, paused, summary])
    agent = build_wolf(store, client=client, out=lambda s: None)

    assert agent.ask("I just adopted a dog from the shelter, her name is Juno!") == "Juno sounds lovely!"
    assert store.search("dog")[0].text == "Has a dog named Juno"
    assert reflect(agent, store) == "User introduced their dog Juno."
    assert "dog Juno" in store.recent_journal()[-1]
    req = client.calls[0]
    assert req["model"] == "claude-opus-5-5"
    assert any(t.get("type") == "web_search_20260209" for t in req["tools"])
    assert req["fallbacks"] == "default"


def test_reflect_skips_empty_conversation(store):
    agent = build_wolf(store, client=_FakeClient([]), out=lambda s: None)
    assert reflect(agent, store) == ""


def test_reflection_skips_trivial_chats(store):
    """A lone "hi" or "thanks" doesn't cost an extra model call or clutter the journal."""
    reply = NS(stop_reason="end_turn", content=[NS(type="text", text="Hi! How can I help?")])
    client = _FakeClient([reply])
    agent = build_wolf(store, client=client, out=lambda s: None)
    agent.ask("[Saturday 2026-11-07 10:00] hi")
    assert reflect(agent, store) == ""
    assert len(client.calls) == 1 and store.recent_journal() == []


def test_reflection_runs_after_two_short_messages(store):
    r1 = NS(stop_reason="end_turn", content=[NS(type="text", text="Hi!")])
    r2 = NS(stop_reason="end_turn", content=[NS(type="text", text="Noted.")])
    summary = NS(stop_reason="end_turn", content=[NS(type="text", text="Quick hello.")])
    agent = build_wolf(store, client=_FakeClient([r1, r2, summary]), out=lambda s: None)
    agent.ask("hi")
    agent.ask("I moved to Denver")
    assert reflect(agent, store) == "Quick hello."
