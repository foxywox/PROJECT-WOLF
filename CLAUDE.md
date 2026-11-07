# PROJECT WOLF

This repository is PROJECT WOLF. It ships with a built-in development assistant
whose job is to help analyze and use WOLF.

## Start here
- Read `docs/wolf/KNOWLEDGE.md` first: it's the assistant's persistent memory of WOLF
  (architecture, how to run things, conventions, decisions, open questions).
- Get a current repo map with `python3 -m wolf_assistant.scanner .`

## Keep the knowledge base current
Whenever you learn something durable about WOLF (how a component works, a build/test
command, a convention, a pitfall, a decision the owner made), update the matching
`## section` of `docs/wolf/KNOWLEDGE.md` in the same change. Replace stale text rather
than appending duplicates. Keep it short and factual, with `path:line` references.

## Assistant layout (not part of WOLF itself)
- `.claude/agents/wolf.md`: the `wolf` subagent (deep analysis of WOLF)
- `.claude/skills/wolf-*`: `/wolf-analyze`, `/wolf-explain`, `/wolf-plan`, `/wolf-learn`
- `wolf_assistant/`: standalone `wolf` CLI built on the Claude API (works outside Claude Code)
- `tests/test_wolf_assistant.py`: offline tests, run with `python3 -m pytest -q`

## Working rules
- Ground answers in the code; cite `path:line`.
- Match existing conventions; keep changes focused; say how to verify.
- If WOLF has no code yet, help the owner define it and record decisions in the knowledge base.
