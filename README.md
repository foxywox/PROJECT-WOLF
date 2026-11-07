# PROJECT WOLF

**WOLF is a personal AI assistant that learns along with you over time.** It remembers
what matters about you (goals, projects, preferences, people, routines) and uses it to
give you more tailored help the longer you use it. It runs on Claude.

## Get started

```bash
pip install -e .                 # installs the `wolf` command
export ANTHROPIC_API_KEY=...     # or: ant auth login

wolf                             # start talking; type 'bye' when you're done
```

## Commands

| Command | What it does |
|---|---|
| `wolf` / `wolf chat` | Have a conversation |
| `wolf ask "..."` | Ask one question |
| `wolf memory [words]` | See everything WOLF remembers, or search it |
| `wolf forget m12` | Delete a memory |
| `wolf profile` | See WOLF's summary of you |
| `wolf journal` | See summaries of past conversations |

Options: `--effort low|medium|high|xhigh|max` (default `medium`), `--model`
(default `claude-opus-5-5`), `--no-web` to turn off web search, `--home DIR` to choose
where memory is stored.

## How WOLF learns

1. **During a conversation** WOLF saves durable facts about you as it notices them
   (`remember`), corrects them when they change (`update_memory`, `forget`), and keeps a short
   profile of the most important ones (`update_profile`).
2. **At the start of every conversation** it loads your profile, your memories, and summaries
   of recent conversations, so it picks up where you left off.
3. **When you say `bye`** it reviews the conversation, saves anything it missed, and writes a
   one-line journal entry.

## Your data

Memory is stored as plain, editable files in `~/.wolf/` (or `$WOLF_HOME`), readable only by
your user account:

- `profile.md`: WOLF's summary of you
- `memories.jsonl`: individual memories
- `journal.md`: one line per conversation

It is **never** stored in this repository. WOLF won't save passwords, keys, account numbers,
or similar secrets. Delete or edit any file at any time. To reset WOLF completely, delete the folder.

## For development

This repo also contains a development assistant for working on WOLF itself:

- In Claude Code: `/wolf-analyze`, `/wolf-explain`, `/wolf-plan`, `/wolf-learn`, and the
  `wolf` subagent. See `CLAUDE.md`.
- From a terminal: `wolf-dev analyze`, `wolf-dev ask "..."`, `wolf-dev chat`
  (`--allow-write` / `--allow-run` to let it edit and test).
- Developer knowledge base: `docs/wolf/KNOWLEDGE.md`.
- Tests (offline): `python3 -m pytest -q`

```
wolf/                 WOLF itself
  cli.py              `wolf` command
  assistant.py        persona, memory tools, end-of-conversation reflection
  memory.py           file-based long-term memory (profile, memories, journal)
  loop.py             shared Claude agent loop (streaming, tools, fallbacks)
wolf_assistant/       `wolf-dev` development assistant (repo scanner + sandboxed tools)
.claude/              Claude Code subagent and skills for developing WOLF
docs/wolf/            developer knowledge base
tests/                offline tests
```
