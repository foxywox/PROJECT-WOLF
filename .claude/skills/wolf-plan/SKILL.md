---
name: wolf-plan
description: Turn a goal for PROJECT WOLF (a feature, fix, refactor, or integration) into a concrete implementation plan grounded in the current code, then optionally implement it. Use when the user says "I want WOLF to...", "how would I add...", or "plan/implement X in WOLF".
---

Goal: $ARGUMENTS

1. Read `docs/wolf/KNOWLEDGE.md` and the code areas the goal touches.
2. Write a short plan: files to change/add, the approach, risks, and how to verify
   (tests/commands). Prefer the smallest change that meets the goal and matches conventions.
3. If the user asked to implement (or said to go ahead), implement it, run the checks you
   listed, and report results honestly. Record any new decisions/conventions in the
   knowledge base.
