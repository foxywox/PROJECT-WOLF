# PROJECT WOLF

WOLF is the owner's personal AI assistant that learns along with them over time
(`wolf/`, the `wolf` command). This repo also ships a development assistant for working
on WOLF itself (`wolf_assistant/`, `.claude/`).

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
- `wolf_assistant/`: `wolf-dev` CLI built on the Claude API (works outside Claude Code)
- `tests/`: offline tests, run with `python3 -m pytest -q`

## Working rules
- Ground answers in the code; cite `path:line`.
- Match existing conventions; keep changes focused; say how to verify.
- Never commit personal data. WOLF's user memory lives in `~/.wolf/`; tests use temp dirs.
- Record the owner's product decisions under `## Decisions` in the knowledge base.
