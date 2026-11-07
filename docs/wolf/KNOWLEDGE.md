# WOLF Knowledge Base

Persistent memory for the WOLF development assistant. Both the Claude Code skills and the
`wolf-dev` CLI read this file at the start of every session and update it as they learn.
(This is about developing WOLF. WOLF's memory of its *user* lives in `~/.wolf/`, never here.)

## Overview

WOLF is the owner's personal AI assistant that learns along with them over time (owner's
definition, 2026-11-07). v1 is a terminal chat assistant on the Claude API with persistent,
file-based long-term memory.

## Architecture

- `wolf/cli.py`: `wolf` command. Offline subcommands (`memory`, `forget`, `profile`, `journal`)
  touch only `MemoryStore`; `chat`/`ask` build an agent and call `reflect` on exit.
- `wolf/assistant.py`: `SYSTEM_PROMPT` (persona, learning rules, secret-storage ban),
  `MemoryTools` (remember/recall/update_memory/forget/update_profile), `build_system`
  (profile + up to 150 most recent memories + last 10 journal lines, frozen per session for
  prompt caching), `build_wolf` (adds `web_search_20260209` server tool), `reflect`
  (end-of-conversation pass that saves missed facts and journals a one-line summary).
- `wolf/memory.py`: `MemoryStore` over `$WOLF_HOME` (default `~/.wolf`, chmod 700):
  `memories.jsonl` (ids `m1`, `m2`, ...; exact-text dedupe; atomic rewrite), `profile.md`
  (`## section` replace), `journal.md`. `search` is keyword/tag scoring, with no embeddings.
- `wolf/loop.py`: shared `AgentLoop`: streaming `client.beta.messages.stream`, adaptive
  thinking, `output_config.effort`, top-level `cache_control`, `fallbacks="default"`
  (beta `server-side-fallback-2026-07-01`). Handles `refusal`, `pause_turn`, and `max_tokens`
  (never runs a possibly-truncated tool call). Also `tool()` / `validate()` helpers.
- `wolf_assistant/`: `wolf-dev` dev assistant (repo scanner + sandboxed read tools, opt-in
  write/run). `WolfAgent` subclasses `AgentLoop`.

## How to run

- Tests (offline, fake client): `python3 -m pytest -q`
- Install: `pip install -e .` gives `wolf` and `wolf-dev`
- Live use needs `ANTHROPIC_API_KEY` or `ant auth login`

## Conventions

- Personal data never goes in the repo; tests use `tmp_path` stores.
- Volatile values (current date/time) go in the user message, not the system prompt, so the
  cached prefix stays stable (`wolf/cli.py`, `stamp`).
- New tools: define with `wolf.loop.tool(...)`, validate with `validate(...)` before running.

## Decisions

- 2026-11-07: WOLF = personal AI assistant that learns over time (owner).
- 2026-11-07: `wolf` command is WOLF itself; the dev assistant moved to `wolf-dev`.
- 2026-11-07: Memory stored as plain files in `~/.wolf` so it's transparent, editable, and private.
- Default model `claude-opus-5-5`, effort `medium` for chat.

## Open questions

- Interfaces beyond the terminal (web/mobile app, voice, messaging)?
- Integrations to learn from (calendar, email, notes, files)?
- Semantic (embedding) search once memory grows past a few hundred items?
- Proactive behaviour (reminders, check-ins, scheduled reviews of goals)?
