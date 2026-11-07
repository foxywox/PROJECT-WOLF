---
name: wolf-explain
description: Explain how a specific part of PROJECT WOLF works (a file, module, function, feature, or flow), grounded in the code with path:line references. Use for "how does X work in WOLF", "where is X", "what does this file do".
---

Explain the part of WOLF the user named: $ARGUMENTS

1. Check `docs/wolf/KNOWLEDGE.md` for what's already known.
2. Locate it with Grep/Glob, read the relevant code and its callers/callees.
3. Explain: purpose, then how it works step by step, inputs/outputs and side effects,
   and gotchas. Cite `path:line` throughout. Include a short usage example if useful.
4. If you learned something durable, add it to the knowledge base.
