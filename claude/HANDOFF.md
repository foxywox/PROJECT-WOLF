# Handoff

Last updated: 2026-11-07, after the project-hub build. Rewrite this file at the end of
every session; keep it under about two pages.

## Where things stand

WOLF is the owner's personal AI assistant that learns along with them. It works end to end in
code and tests:

- **Talk to it:** `wolf serve` (web app for phone and desktop, with voice) or `wolf` in a terminal.
- **It remembers:** profile, memories and a journal in `~/.wolf`, updated during and after each
  conversation.
- **It's modular:** every ability is a component (`wolf/components/`). The built-ins are
  memory, web_search and clock. Add one by dropping a file in `~/.wolf/components/`.
- **Project hub:** WOLF's app has a Project tab with the build tracker (wolf pup), the whole
  production plan (`hub/plan.json`) and a research forum (`hub/forum/`) where people and AI
  post. AI side: `wolf-dev plan`, `wolf-dev forum`, and the `research` component.
- **Friendlier app:** bottom tab bar on phones, suggested first messages, ability switches,
  a "How WOLF works" guide, retry on failures.
- **Easy to start:** `start-wolf.command` / `start-wolf.bat` plus `wolf setup` (saves the API key).
- **Ready to host:** a Dockerfile, verified in a container. The owner hasn't picked a host yet.
- **Quality:** 66 offline tests; `python3 claude/tools/check.py` runs everything.

**Never verified for real:** a live conversation with Claude (no API key in the sandbox), the
microphone and speech on a real device, and the Windows launcher. If the owner reports a
problem, start there.

## What's next (owner's choice; ask if it isn't clear)

The production plan (`wolf-dev plan`) is now the source of truth for what's next; keep it
honest with `wolf-dev plan set`. Check the forum (`wolf-dev forum`) for questions addressed
to AI. As of now:

1. **Real-world check (active, needs the owner):** first real chat, Windows launcher, voice.
2. **Personality (waiting on the owner):** the forum thread "what should WOLF's personality
   be?" is where that conversation should happen.
3. **Learn from your life:** calendar first (read-only), then email and notes, each a component.
4. **Proactive help and hosting:** later.

## What I think (the previous session's view)

- **Components are the right spine.** Every new feature should be a component, not a change
  to the core. If a feature seems to need a core change, add a hook to `Component` instead
  (as `on_end` was added for memory's reflection).
- **The model could be swappable too.** The model call lives in `wolf/loop.py`. Making the
  backend a choice (Claude by default, a local model for offline work) would fit the component
  philosophy. Don't start this without the owner asking.
- **Personality is still generic.** The owner asked about a personality called "MONTY"; no
  file containing it was found. Ask the owner for it. The clean place for it is a
  `personality` setting or component that supplies the persona text now hardcoded in
  `wolf/assistant.py` (`SYSTEM_PROMPT`).
- **Memory search is keyword-based.** Fine for hundreds of memories. Revisit (embeddings, or
  letting Claude rank candidates) when someone has real usage.
- **The forum is public files.** Fine for a public research project, but if the owner ever
  wants private discussion, the hub needs a private location (`WOLF_HUB` outside the repo).
- **Hosted forum posts don't persist.** In the Docker image the hub is baked in at
  `/app/hub`; posts made there vanish on redeploy. If WOLF gets hosted, point `WOLF_HUB` at
  the `/data` volume and decide how posts get back into the repo.
- **Risk:** reflection runs a model call at the end of every conversation, which costs a
  little each time. If the owner worries about cost, make reflection skip very short chats.

## How the owner likes to work

- Wants things automated with minimal effort on their side: do the work, then report.
- Wants progress visible: a live progress window with an animated wolf pup exists (see
  `claude/TOOLS.md`). Update it at real milestones.
- Explain in plain language. The owner isn't necessarily reading code.
