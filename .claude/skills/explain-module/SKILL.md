---
name: explain-module
description: Explain a BrewOps module or directory to a newcomer — what it does, how it fits the ingest → db → api → frontend pipeline, and its key files. Use when someone asks "explain X", "walk me through X", or "what does X do" about a part of the codebase.
---

# Explain a module to a newcomer

Produce a plain-language walkthrough of a module for someone new to BrewOps —
not a line-by-line narration, but enough to orient them: what it's for, how it
connects to the rest of the pipeline (`data/inbox/*.csv` → ingest → db → api →
frontend), and where to look next.

## Steps

1. Identify the target module (a directory like `src/brewops/db/` or a single
   file). If the user didn't name one, ask which part of the codebase they mean.
2. Read every file in the module — don't skim. For a directory, read each file
   in it; for a single file, read it in full.
3. Check `CLAUDE.md` for how this module is described in the architecture
   section, and reconcile that with what the code actually does — note any
   drift instead of assuming the doc is current.
4. Identify what calls into this module and what it calls out to (e.g. `grep`
   for imports of it elsewhere in `src/`), so you can explain its place in the
   pipeline, not just its internals.
5. Write the explanation with this shape:
   - **What it's for** — one or two sentences, plain language.
   - **Where it sits** — which stage of the pipeline (ingest/db/api/frontend),
     what feeds it, what it feeds.
   - **Key files/functions** — the 3-5 things a newcomer would actually touch,
     each with a one-line "why this exists," not a summary of every line.
   - **Conventions to know** — anything non-obvious a newcomer would trip on
     (e.g. naive timestamps, no ORM, dict-based query returns) — pull from
     CLAUDE.md's Conventions section where relevant, don't restate all of it.
   - **Where to look next** — the natural next file/module to read to keep
     following the pipeline.
6. Keep it to what a newcomer needs for orientation — skip exhaustive API
   listings; point them at the file to read those themselves.

## Gotchas

- Don't just paraphrase file contents top to bottom — synthesize the *purpose*
  and *shape*, using well-named functions/files as evidence rather than
  re-explaining what their names already say.
- If the module's actual behavior contradicts `CLAUDE.md`, say so explicitly
  rather than silently trusting the doc.
- Don't scope-creep into reviewing code quality or suggesting changes — this
  skill is explanation only.

## Version

0.1.0
