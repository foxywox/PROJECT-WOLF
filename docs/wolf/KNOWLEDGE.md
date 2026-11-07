# WOLF Knowledge Base

Persistent memory for the WOLF development assistant. Both the Claude Code skills and the
`wolf-dev` CLI read this file at the start of every session and update it as they learn.
(This is about developing WOLF. WOLF's memory of its *user* lives in `~/.wolf/`, never here.)

## Overview

WOLF is the owner's personal AI assistant that learns along with them over time (owner's
definition, 2026-11-07). It runs on the Claude API with persistent, file-based long-term
memory, and you can talk to it in a web app (`wolf serve`, phone + desktop, voice) or the terminal.

## Architecture

- `wolf/server.py`: `wolf serve`. `WolfApp` (HTTP-independent: `open`, `chat`, `end`, `sweep`,
  `end_all`; one global lock serializes model turns so memory files never race) and
  `make_handler` (stdlib `ThreadingHTTPServer`). Static app is public; every `/api/*` route
  needs `Authorization: Bearer <token>` from `$WOLF_HOME/web_token` (0600). `/api/chat` streams
  SSE events `start`/`text`/`tool`/`done`/`error`. Idle conversations (20 min) are reflected on
  by a sweeper thread; all open ones on shutdown. Optional TLS via `--cert/--key`.
- `wolf/web/`: no-build single-page app (`app.js` vanilla JS). Token is read from `?token=`,
  stored in localStorage, stripped from the URL. Voice uses the browser Web Speech API
  (SpeechRecognition + speechSynthesis), so it needs a secure context: localhost or https.
  Transcript is kept in localStorage for display only; the server holds the real conversation.
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
  thinking, `output_config.effort`, `out` (text) and `on_tool` (tool-start) callbacks, top-level `cache_control`, `fallbacks="default"`
  (beta `server-side-fallback-2026-07-01`). Handles `refusal`, `pause_turn`, and `max_tokens`
  (never runs a possibly-truncated tool call). Also `tool()` / `validate()` helpers.
- `wolf_assistant/`: `wolf-dev` dev assistant (repo scanner + sandboxed read tools, opt-in
  write/run). `WolfAgent` subclasses `AgentLoop`.

## How to run

- Tests (offline, fake client): `python3 -m pytest -q` (`tests/test_server.py` runs a real
  HTTP server on a random port)
- Web app: `wolf serve` (localhost) or `wolf serve --host 0.0.0.0` (phone on same Wi-Fi)
- Install: `pip install -e .` gives `wolf` and `wolf-dev`
- Live use needs `ANTHROPIC_API_KEY` or `ant auth login`

## Conventions

- Personal data never goes in the repo; tests use `tmp_path` stores.
- Volatile values (current date/time) go in the user message, not the system prompt, so the
  cached prefix stays stable (`wolf/cli.py`, `stamp`).
- CSS: `[hidden] { display: none !important; }` is required because components set `display`
  (a missing rule once left the lock screen covering the app).
- The loop emits raw text only; terminal newlines are printed by the CLIs, not the loop.
- New tools: define with `wolf.loop.tool(...)`, validate with `validate(...)` before running.

## Decisions

- 2026-11-07: WOLF = personal AI assistant that learns over time (owner).
- 2026-11-07: `wolf` command is WOLF itself; the dev assistant moved to `wolf-dev`.
- 2026-11-07: Memory stored as plain files in `~/.wolf` so it's transparent, editable, and private.
- Default model `claude-opus-5-5`, effort `medium` for chat.
- 2026-11-07: First interface beyond the terminal is a web app with voice that works on phone
  and desktop (owner chose "where you talk to it" first). Integrations and proactive
  behaviour are deferred until later.

## Open questions

- Hosting WOLF so it's reachable without a computer running at home (currently: Tailscale).
- Messaging-app interface (e.g. Telegram/SMS)?
- Better voices: browser speech synthesis varies by device; consider Claude-independent TTS.
- Integrations to learn from (calendar, email, notes, files)?
- Semantic (embedding) search once memory grows past a few hundred items?
- Proactive behaviour (reminders, check-ins, scheduled reviews of goals)?
