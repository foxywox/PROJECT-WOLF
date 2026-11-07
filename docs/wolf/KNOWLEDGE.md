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
- `wolf/config.py`: credentials. `wolf setup` saves the API key in `$WOLF_HOME/config.json`
  (0600); `make_client` prefers env `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN`, then the saved
  key, then an `ant auth login` profile. `check_key` validates with `models.retrieve` (no
  tokens). Commands that need Claude run setup interactively if no credentials (TTY) or print
  `NOT_SET_UP` and exit 2.
- Launchers: `start-wolf.command` (Mac double-click / Linux) and `start-wolf.bat` (Windows)
  create `.venv`, install (output to `.venv/install.log`), then `wolf serve --open`.
- Hosting: `Dockerfile` (python:3.12-slim, `WOLF_HOME=/data`, `WOLF_HOST=0.0.0.0`, `PORT=8080`).
  Env: `WOLF_TOKEN` (fixed access token, >=16 chars), `WOLF_PUBLIC_URL` (printed link).
  SIGTERM is handled like Ctrl+C so open conversations are reflected on before exit.
- `wolf/cli.py`: `wolf` command. Offline subcommands (`memory`, `forget`, `profile`, `journal`)
  touch only `MemoryStore`; `chat`/`ask` build an agent and call `reflect` on exit.
- `wolf/assistant.py`: core only. `SYSTEM_PROMPT` = personality + boundaries (no feature
  rules). `build_toolkit` loads the enabled components; `system_blocks` makes two cached
  blocks: persona + each component's `instructions()`, then all components' `context()`;
  `build_wolf`; `finish_conversation` runs every component's `on_end`. Re-exports
  `MemoryTools`, `reflect`, `REFLECT_PROMPT` for compatibility.
- `wolf/components/__init__.py`: `Component` base (tools/call/server_tools/instructions/
  context/on_end), `ComponentContext` (store, config, `settings(name)` from config.json
  `"settings"`), `Toolkit` (merges components, rejects duplicate tool names, validates inputs,
  freezes tool defs for caching), discovery `resolve()`: built-in name, then
  `$WOLF_HOME/components/<name>.py` (exactly one Component subclass), then entry point group
  `wolf.components`, then `"module:Class"`. Enabled list: config.json `"components"`, default
  `memory, web_search, clock`. CLI: `wolf components [list|enable|disable|reset]`.
- `wolf/components/memory.py`: `MemoryComponent` (tools from `MemoryTools`; learning rules as
  instructions; profile + up to 150 recent memories + last 10 journal lines as context; `on_end`
  = `reflect`). `web.py`: `web_search_20260209` server tool (`max_uses` setting, default 5).
  `clock.py`: `current_time` tool.
- `wolf/hub.py` + `hub/`: project hub shared by people and AI. `plan.json` (phases -> items,
  statuses done/active/next/later/idea, `who` human/claude/either; `plan()` adds a summary,
  `set_item_status`, `plan_text`), `forum/<id>.json` (one file per thread; id =
  `YYYY-MM-DD-<slug>`, posts `{author, kind: human|ai, body, time}`; validated lengths; ids
  regex-checked so paths can't escape), `progress.json` (build tracker, written by
  `claude/tools/progress.py`). `hub_dir()` = `$WOLF_HUB` or `<repo>/hub` (Docker sets
  `WOLF_HUB=/app/hub`). Server: `GET /api/hub`, `GET|POST /api/hub/forum[/<id>]` (app posts are
  always `kind: human`), `GET|POST /api/components` (ability switches). AI: `wolf-dev plan
  [set]`, `wolf-dev forum [list|read|new|reply]` (kind `ai`, default author Claude), and the
  `research` component (off by default; WOLF posts as "WOLF"). The briefing includes the plan
  and the 5 most recent threads.
- `wolf/personality.py`: presets dict (balanced default, coach, calm, playful, brief) or
  `custom` = `$WOLF_HOME/personality.md` (max 4000 chars); config `"personality"`. Goes into
  the system prompt after the fixed Boundaries (which add a crisis rule).
  API `GET|POST /api/personality`; CLI `wolf personality [set NAME]`.
- `wolf/components/reminders.py` (default on): `$WOLF_HOME/reminders.json`, ids `r1..`; due
  = local ISO date (9 AM) or datetime; tools add/list/complete; context lists due + next 7
  days. API `GET|POST /api/reminders`, `POST /api/reminders/<id>/done`; chat shows a due
  banner (polls every 60 s).
- `wolf/components/calendar.py` (off until a calendar is added): read-only via private iCal
  links (`icalendar` + `recurring-ical-events`), stored in config
  `settings.calendar.calendars`; 15-min cache in `$WOLF_HOME/cache/`, last good copy on
  failure. Tool `calendar_events(start_date, days)`; context = today + tomorrow. The app API
  only accepts http(s)/webcal links (`allow_files=False`); local .ics paths are code/CLI only.
  Tests patch `calendar.urlopen` (never the global `urllib.request.urlopen`, which the test
  client also uses).
- Memory reflection is skipped for trivial chats (one user message under 40 chars).
- `wolf/web/`: tabs Chat / Memory / You / Project; header tabs on desktop, fixed bottom bar
  under 640px (`--tabbar`). Chat welcome has suggestion buttons; failed messages get "Try
  again". You tab: "How WOLF works", profile, ability switches, journal with Today/Yesterday.
  Project tab polls `/api/hub` every 20 s while visible.
- `claude/` + `wolf_assistant/workspace.py`: Claude's workspace. `brief()` assembles protocol,
  HANDOFF, last 3 changelog days, knowledge base, tools, git state, components, repo map
  (`--tests` adds test results). `add_log()` keeps CHANGELOG.md newest-day-first. Tools are
  scripts in `claude/tools/` whose first docstring/comment line is the description
  (`check`, `progress`, `ui_smoke`). The `wolf-dev` agent's system prompt is this briefing.
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
  HTTP server on a random port and a SIGTERM test via subprocess)
- Container (verified 2026-11-07: build, auth, volume persistence, graceful stop):
  `docker build -t wolf . && docker run -p 8080:8080 -v wolfdata:/data -e ANTHROPIC_API_KEY=... -e WOLF_TOKEN=... wolf`.
  In Claude Code's cloud sandbox the build needs the proxy CA (`--build-context ca=/root/.ccr`
  plus `PIP_CERT`) via a test-only Dockerfile copy; never commit that.
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
- Progress callbacks (`out`, `on_tool`) go through `AgentLoop._notify`, which swallows errors:
  a closed browser stream must never abort a turn or lose a memory write.
- Without credentials the SDK raises `TypeError("Could not resolve authentication method")`,
  not an API error; `server._friendly` maps it to `NOT_SET_UP`.
- New abilities are components, never core edits; if a component needs something the core
  lacks, add a hook to `Component`.
- New tools: define with `wolf.loop.tool(...)`; `Toolkit.call` validates inputs before running.
- Before committing: `python3 claude/tools/check.py`. For UI changes also
  `python3 claude/tools/ui_smoke.py OUTDIR` and look at the screenshots (it uses a throwaway
  copy of the hub).
- In `.panel`, centering comes from `margin-left/right: auto`; set vertical margins with
  longhands on headings and hints, or they snap to the left edge on desktop.
- A grid item with `position: fixed` still obeys `justify-self`; the phone tab bar needs
  `justify-self: stretch` (a centered bar was caught in screenshots).
- End of session: changelog entry + rewrite `claude/HANDOFF.md`.

## Decisions

- 2026-11-07: WOLF = personal AI assistant that learns over time (owner).
- 2026-11-07: `wolf` command is WOLF itself; the dev assistant moved to `wolf-dev`.
- 2026-11-07: Memory stored as plain files in `~/.wolf` so it's transparent, editable, and private.
- Default model `claude-opus-5-5`, effort `medium` for chat.
- 2026-11-07: Every WOLF ability is a swappable component (owner asked for components
  "completely interchangeable with WOLF").
- 2026-11-07: Personality is a setting (presets or the owner's own words); reminders on by
  default; calendar via private iCal links so no provider has to be chosen (built while the
  owner was away).
- 2026-11-07: The Build Tracker lives in WOLF (Project tab), alongside the production plan
  and a research forum for people and AI (owner's request). Forum posts are public files.
- 2026-11-07: Claude keeps its own workspace in `claude/` (owner's request): handoffs,
  personal changelog, tools.
- 2026-11-07: First interface beyond the terminal is a web app with voice that works on phone
  and desktop (owner chose "where you talk to it" first). Integrations and proactive
  behaviour are deferred until later.

## Open questions

- Hosting provider for the `Dockerfile` (needs a persistent disk at /data): owner's choice.
- Messaging-app interface (e.g. Telegram/SMS)?
- Better voices: browser speech synthesis varies by device; consider Claude-independent TTS.
- Integrations to learn from (calendar, email, notes, files)?
- Semantic (embedding) search once memory grows past a few hundred items?
- Proactive behaviour (reminders, check-ins, scheduled reviews of goals)?
- Personality: owner mentioned "MONTY" personality files; none found (2026-11-07). Persona text is `SYSTEM_PROMPT` in `wolf/assistant.py` until the owner shares it.
- Swappable model backend (e.g. a local model) as a component-style choice?
