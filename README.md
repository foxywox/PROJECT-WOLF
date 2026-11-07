# PROJECT WOLF

PROJECT WOLF comes with a built-in **development assistant** that analyzes WOLF, explains
how it works, plans and implements changes, and keeps a running knowledge base of
everything it learns. You can use it two ways.

## 1. Inside Claude Code (no setup)

Open this repo in Claude Code (web, desktop, or CLI) and use:

| Command | What it does |
|---|---|
| `/wolf-analyze` | Full analysis: what WOLF is, architecture, how to run/test, risks, next steps |
| `/wolf-explain <thing>` | Explains a file, function, feature or flow, citing `path:line` |
| `/wolf-plan <goal>` | Turns a goal into a plan grounded in the code, and implements it on request |
| `/wolf-learn` | Brings the knowledge base up to date with the code |

You can also just ask. The `wolf` subagent (`.claude/agents/wolf.md`) is picked up
automatically for WOLF questions, and `CLAUDE.md` tells every session to read and maintain
the knowledge base.

## 2. The `wolf` command-line assistant (Claude API)

```bash
pip install -e .                 # installs the `wolf` command
export ANTHROPIC_API_KEY=...     # or: ant auth login

wolf map                         # offline repo map, no API call
wolf analyze                     # full analysis, saved to the knowledge base
wolf ask "How does X work?"      # one question
wolf chat                        # interactive session
wolf learn                       # refresh the knowledge base
wolf --allow-run review          # review recent changes using git
wolf --allow-write --allow-run chat   # let it edit files and run tests (asks before each one)
```

Options: `--model` (default `claude-opus-5-5`), `--effort low|medium|high|xhigh|max`
(default `high`), `-y` to skip per-action confirmations.

By default the assistant can only **read** the repo. File reads are sandboxed to the
repository, and `.git` is off-limits. Writing files and running commands are opt-in flags,
and each action asks for confirmation unless you pass `-y`. The knowledge base is the one
file it always updates. It's version-controlled, so you can review every change.

## The knowledge base

`docs/wolf/KNOWLEDGE.md` is the assistant's long-term memory of WOLF: overview,
architecture, how to run things, conventions, decisions, and open questions. Both the
Claude Code skills and the CLI read it at the start of a session and update it when they
learn something. Commit it like any other file.

## Layout

```
CLAUDE.md                     instructions every Claude Code session follows
.claude/agents/wolf.md        the `wolf` subagent
.claude/skills/wolf-*/        /wolf-analyze, /wolf-explain, /wolf-plan, /wolf-learn
docs/wolf/KNOWLEDGE.md        persistent WOLF knowledge base
wolf_assistant/               the `wolf` CLI (scanner, sandboxed tools, agent loop)
tests/                        offline tests: python3 -m pytest -q
```
