# PROJECT WOLF

**WOLF is a personal AI assistant that learns along with you over time.** It remembers
what matters about you (goals, projects, preferences, people, routines) and uses it to
give you more tailored help the longer you use it. It runs on Claude.

## Get started

You need [Python 3.10+](https://www.python.org/downloads/) and a Claude API key
([create one here](https://console.anthropic.com/settings/keys); WOLF walks you through it).

1. Download this repository: on GitHub, choose **Code → Download ZIP**, then unzip it.
2. Start WOLF:
   - **Mac:** double-click `start-wolf.command`. If macOS says it can't verify the developer,
     right-click the file, choose **Open**, then **Open** again (only needed the first time).
   - **Windows:** double-click `start-wolf.bat`.
   - **Linux:** run `./start-wolf.command`.
3. The first time, it sets itself up (about a minute) and asks you to paste your API key.
   Then WOLF opens in your browser. Next time, it just opens.

Prefer the terminal?

```bash
pip install -e .        # installs the `wolf` command
wolf setup              # connect to Claude (saves your key in ~/.wolf, readable only by you)
wolf serve --open       # open the app in your browser
wolf                    # or talk right in the terminal; type 'bye' when you're done
```

## The WOLF app (phone, desktop, voice)

`wolf serve` starts WOLF as a web app and prints a private link. Open it, and you get:

- **Chat** with replies that stream in as WOLF writes them. A small tag shows when WOLF
  saved or checked something in its memory.
- **Voice**: tap the mic and talk. Turn on the speaker icon and WOLF reads its replies
  aloud. If you started with the mic, it listens again after answering, so you can go
  back and forth hands-free.
- **Memory**: see and search everything WOLF remembers, and delete anything with one tap.
- **You**: WOLF's profile of you, its **personality** (Balanced, Coach, Calm, Playful, Brief,
  or your own words), your **reminders**, your **calendar**, switches for its abilities, a
  plain-language "How WOLF works" guide, and a log of past conversations.
- **Reminders**: say "remind me to…" and WOLF sets one. Due reminders show at the top of the
  chat with a Done button, and WOLF brings them up when you next talk.
- **Calendar**: connect any calendar (Google, Outlook, Apple) with its private calendar link,
  and WOLF can see your schedule. It can't change anything.
- **Project**: how WOLF itself is being built. It shows the current build (a little wolf pup
  runs toward the flag as work progresses), the whole production plan, and a research forum
  where people and AI discuss ideas. The project is public, so forum posts are too once
  they're committed.
- **New conversation** wraps up the current one: WOLF saves what it learned and writes a
  journal line. Conversations left idle for 20 minutes, or open when you stop the server,
  are saved the same way.

**On your phone (same Wi-Fi):** run `wolf serve --host 0.0.0.0` and open the "your phone" link
it prints. To install it like an app, use *Add to Home Screen* (iPhone: Share menu; Android:
browser menu).

**Voice on a phone needs https.** Browsers only allow the microphone on secure connections, and
`localhost` counts as secure, so voice works on the computer running WOLF without setup.
For a phone, the easiest option is [Tailscale](https://tailscale.com): install it on both
devices, then run `wolf serve` and `tailscale serve 8765` and open the https link Tailscale
gives you. This also lets you reach WOLF away from home. Or pass your own certificate with
`wolf serve --cert cert.pem --key key.pem`.

**Privacy:** the link contains an access token (stored in `~/.wolf/web_token`). Every request
for your data needs it, so other people on your network can't read your memories. Don't share
the link. To revoke it, delete that file and restart `wolf serve`.

## Commands

| Command | What it does |
|---|---|
| `wolf setup` | Connect WOLF to Claude (paste your API key once) |
| `wolf components` | See WOLF's abilities; `enable`/`disable NAME` to switch them |
| `wolf personality` | See or `set` WOLF's personality (`set custom` uses `~/.wolf/personality.md`) |
| `wolf serve` | Run the WOLF app (`--open` opens your browser) |
| `wolf` / `wolf chat` | Have a conversation in the terminal |
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
- `reminders.json`, `personality.md`, `config.json` (settings, your API key and calendar links)
- `journal.md`: one line per conversation

It is **never** stored in this repository. WOLF won't save passwords, keys, account numbers,
or similar secrets. Delete or edit any file at any time. To reset WOLF completely, delete the folder.

## Components: WOLF's abilities

Everything WOLF can do beyond talking is a component you can switch on or off:

| Component | What it does |
|---|---|
| `memory` | Remembers you across conversations (profile, memories, journal) |
| `web_search` | Looks things up on the web |
| `clock` | Knows the current date and time |
| `reminders` | Sets reminders and brings them up when due |
| `calendar` | Reads your calendar (turns on when you connect one) |

Switch them on the **You** tab in the app, or with `wolf components` /
`wolf components disable web_search` in a terminal. There's also `research` (off by default):
it lets WOLF read the production plan and post in the research forum when you ask it to.

**Add your own:** put a Python file in `~/.wolf/components/` with one class that extends
`wolf.components.Component`, then `wolf components enable <filename>`. A component can give WOLF
tools, instructions, a snapshot of data at the start of each conversation, and a hook when a
conversation ends. See the docstring in `wolf/components/__init__.py` and
`wolf/components/clock.py` for a 20-line example. Components can also be installed as packages
(entry point group `wolf.components`), or replace a built-in entirely: a different memory
system is just another component named in the list.

## Hosting WOLF online (optional)

To use WOLF from anywhere without leaving a computer on, run it on a hosting service that
runs Docker containers and offers a persistent disk. The included `Dockerfile` is ready:

- Mount a persistent disk at `/data`. That's where WOLF's memory of you lives; without it,
  WOLF forgets everything on each restart.
- Set these secrets:
  - `ANTHROPIC_API_KEY`: your Claude key.
  - `WOLF_TOKEN`: a long random password (at least 16 characters). Your link is
    `https://<your-app-address>/?token=<WOLF_TOKEN>`.
  - `WOLF_PUBLIC_URL` (optional): your app's address, so the startup log prints the full link.
- The container listens on port `8080`, or `$PORT` if your host sets one. Hosts give you
  https automatically, so voice works on your phone.

On shutdown or redeploy, WOLF saves any open conversations to memory first.

## For development

This repo also contains a development assistant for working on WOLF itself:

- In Claude Code: `/wolf-analyze`, `/wolf-explain`, `/wolf-plan`, `/wolf-learn`, and the
  `wolf` subagent. See `CLAUDE.md`.
- From a terminal: `wolf-dev analyze`, `wolf-dev ask "..."`, `wolf-dev chat`
  (`--allow-write` / `--allow-run` to let it edit and test).
- Developer knowledge base: `docs/wolf/KNOWLEDGE.md`.
- Project hub: `hub/` holds the production plan (`plan.json`), the research forum
  (`forum/`, one file per thread) and build progress. People use the Project tab; AI uses
  `wolf-dev plan`, `wolf-dev forum` and the `research` component.
- Claude's workspace: `claude/` (handoff, changelog, tools). `wolf-dev brief` prints everything
  a new Claude session needs; `wolf-dev log`, `wolf-dev tools`. Run all checks with
  `python3 claude/tools/check.py`.
- Tests (offline): `python3 -m pytest -q`

```
wolf/                 WOLF itself
  cli.py              `wolf` command
  server.py           `wolf serve`: web app server + JSON/streaming API (standard library only)
  hub.py              the project hub: production plan, research forum, build progress
  personality.py      personality presets and your own
  web/                the app: index.html, app.js, style.css, PWA manifest, icon, service worker
  assistant.py        WOLF's personality; assembles the enabled components
  components/         swappable abilities: memory, web_search, clock, reminders, calendar,
                      research (+ your own)
  memory.py           file-based long-term memory (profile, memories, journal)
  loop.py             shared Claude agent loop (streaming, tools, fallbacks)
wolf_assistant/       `wolf-dev` development assistant (repo scanner, sandboxed tools, briefing)
claude/               Claude's workspace: handoff, changelog, tools catalog, helper scripts
hub/                  production plan, research forum, build progress (shared by people and AI)
.claude/              Claude Code subagent and skills for developing WOLF
docs/wolf/            developer knowledge base
tests/                offline tests
```
