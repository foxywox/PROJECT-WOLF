# Handoff

Last updated: 2026-11-08, after adding the desktop wallpaper. Rewrite this file at the end of
every session; keep it under about two pages.

## Where things stand

WOLF is the owner's personal AI assistant that learns along with them. It works end to end in
code and tests:

- **Talk to it:** `wolf serve` (web app for phone and desktop, with voice) or `wolf` in a terminal.
- **It remembers:** profile, memories and a journal in `~/.wolf`, updated during and after each
  conversation.
- **It's modular:** every ability is a component (`wolf/components/`). The built-ins are
  memory, web_search and clock. Add one by dropping a file in `~/.wolf/components/`.
- **App layout:** four tabs, Chat, Schedule, Memory and Settings, chosen with the owner after
  they found the earlier layout confusing. Keep new features inside these four; don't add
  tabs without asking.
- **Desktop wallpaper:** `wallpaper/` ("WOLF Den"): the owner's autumn forest wallpaper fused
  with their HUD mockup. WOLF on a rune circle (facets light up as plan items finish), fox
  agents = WOLF's abilities, panels with real data only (GitHub for the build, local
  `/api/wallpaper?key=` for memories and system). The owner watches it: push progress at
  milestones (`progress.py ... --commit`) and keep `hub/plan.json` honest. Never add a panel
  value that isn't backed by real data.
- **Project hub:** a project page (opened from Settings, not a tab) shows build progress as a
  plain bar, the whole production plan (`hub/plan.json`) and a research forum (`hub/forum/`)
  where people and AI post. AI side: `wolf-dev plan`, `wolf-dev forum`, and the `research` component.
- **Personal features:** personality setting (presets or the owner's own words), reminders
  (due banner in chat), read-only calendar from any service's private iCal link.
- **Friendlier app:** bottom tab bar on phones, suggested first messages, ability switches,
  a "How WOLF works" guide (Settings, Help), retry on failures.
- **Easy to start:** `start-wolf.command` / `start-wolf.bat` plus `wolf setup` (saves the API key).
- **Ready to host:** a Dockerfile, verified in a container. The owner hasn't picked a host yet.
- **Quality:** 79 offline tests; `python3 claude/tools/check.py` runs everything.

**Never verified for real:** a live conversation with Claude (no API key in the sandbox), the
microphone and speech on a real device, and the Windows launcher. If the owner reports a
problem, start there.

## What's next (owner's choice; ask if it isn't clear)

The production plan (`wolf-dev plan`) is now the source of truth for what's next; keep it
honest with `wolf-dev plan set`. Check the forum (`wolf-dev forum`) for questions addressed
to AI. As of now:

1. **Real-world check (active, needs the owner):** first real chat, Windows launcher, voice.
2. **Personality content (waiting on the owner):** the setting exists; MONTY just needs
   describing (Settings, Personality, "Your own"), or discussing in the forum thread.
3. **Learn from your life:** calendar is done. Email and notes are next, each a component.
   Email needs a decision on provider and access (IMAP app password vs OAuth); ask first.
4. **Proactive help:** reminders exist, but WOLF can only surface them when the app is open
   or a conversation starts. Real push (phone notifications, email, a messaging app) needs
   WOLF running all the time, which waits on hosting. Weekly goal review could be a
   reminders-style component next.

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
- **Calendar links are secrets.** They're stored in `config.json` (owner-only) and never shown
  back in full; keep it that way in any new UI or API.
- **Risk (now reduced):** reflection is skipped for trivial chats, but still runs for every real conversation.

## How the owner likes to work

- Judges the app by whether it makes sense at a glance. They called the old layout
  confusing; when a request is ambiguous ("night controls"), one quick multiple-choice
  question worked well.
- Wants things automated with minimal effort on their side: do the work, then report.
- Wants progress visible: a live progress window with an animated wolf pup exists (see
  `claude/TOOLS.md`). Update it at real milestones.
- Explain in plain language. The owner isn't necessarily reading code.
