---
name: wolf-analyze
description: Full analysis of PROJECT WOLF (purpose, architecture, data/control flow, how to run and test, quality risks, prioritized next steps), saved to the WOLF knowledge base. Use when the user asks to analyze, audit, assess, or get an overview of WOLF.
---

Analyze PROJECT WOLF end to end. Delegate the investigation to the `wolf` subagent when the
codebase is large; otherwise do it directly.

1. Read `docs/wolf/KNOWLEDGE.md` and run `python3 -m wolf_assistant.scanner .`.
2. Identify entry points, manifests and main modules; read them. Trace the main flows.
3. Try the build/test commands you find (note which passed, failed, or couldn't run).
4. Produce a report with these sections:
   - **What WOLF is** (2-3 sentences)
   - **Architecture** (components and how they connect; a small diagram if it helps)
   - **How to run / test** (exact commands, and whether you verified them)
   - **Risks** (bugs, security, tech debt, each with `path:line`, most severe first)
   - **Next steps** (top 3-5, highest value first)
5. Update the knowledge base sections Overview, Architecture, How to run, Conventions,
   Open questions to match what you found.

If the repo has no WOLF code yet, say so and switch to helping define WOLF: ask the owner
what it should do, then propose a stack and initial structure, and record it under Decisions.
