# Claude's workspace

This folder belongs to Claude, the AI that builds WOLF with its owner. It is how one Claude
session hands its work and thinking to the next, so nothing is lost between conversations.

| File | What it is |
|---|---|
| `HANDOFF.md` | Where things stand, what's next, and the last session's thinking. Rewritten at the end of every session. |
| `CHANGELOG.md` | What each session did and why, newest first. Only ever added to. |
| `TOOLS.md` | Tools and services Claude uses outside this repo, and how. |
| `tools/` | Helper scripts. Each starts with a one-line description. |

## For a new Claude session

Run this and read all of it before doing anything else:

```bash
python3 -m wolf_assistant brief          # add --tests to include test results
```

It combines this folder, the knowledge base (`docs/wolf/KNOWLEDGE.md`), git state, the
component list and the repo map into one briefing. The `wolf-dev` CLI loads the same briefing
into its own context automatically. In a plain Claude chat with no file access, paste the
output in.

Other commands (all offline):

```bash
python3 -m wolf_assistant log "what I did and why"   # changelog entry under today's date
python3 -m wolf_assistant tools                      # list helper scripts
python3 -m wolf_assistant tools run check            # run one
```

(`wolf-dev` works in place of `python3 -m wolf_assistant` once the package is installed.)
