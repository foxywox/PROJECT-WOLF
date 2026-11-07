# Claude's changelog

Newest first. One heading per day; each bullet says what changed and why.

## 2026-11-07

- Built the WOLF development assistant first, because the repo was empty and "WOLF" was undefined: CLAUDE.md, the `wolf` subagent, `/wolf-*` skills, a knowledge base, and a CLI on the Claude API.
- Owner defined WOLF as "my personal AI assistant that learns along with me over time". Built WOLF v1 around plain-file memory in ~/.wolf (profile, memories, journal, end-of-conversation reflection) so memory stays private and editable. Renamed the dev CLI to `wolf-dev` so `wolf` is WOLF itself.
- Owner chose "where you talk to it" as the next phase. Built `wolf serve`: a standard-library web app for phone and desktop with streaming replies, voice in and out, and memory/profile views, protected by an access token. A browser test caught a CSS bug (the lock screen covered the app).
- While the owner was away: added `wolf setup`, double-click launchers, and a Dockerfile. Fixed two bugs that lost conversation summaries (closed browser stream; SIGTERM on hosts). Verified the container end to end.
- Searched for "MONTY" personality files at the owner's request. Found none; asked the owner for them.
- Made every WOLF ability a swappable component (`wolf/components/`): memory, web search, and a new clock. Components can be enabled/disabled with `wolf components`, dropped in as files in ~/.wolf/components, installed as packages, or swapped for another implementation. The core prompt now holds only personality; each component brings its own instructions and context.
- Created this workspace (`claude/`): handoff, changelog, tools catalog, `wolf-dev brief/log/tools`, and the `check`, `progress` and `ui_smoke` tools. The `wolf-dev` agent now reads the same briefing. Added a live progress window for the owner.
