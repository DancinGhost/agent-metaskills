---
name: skill-split
description: >-
  Restructures an Agent Skill that has outgrown its context budget into a
  concise SKILL.md entry point plus on-demand reference files and helper
  scripts. Use when SKILL.md exceeds 500 lines or 5000 tokens, when skill-lint
  reports W020 or W021, or when asked to split, slim down, modularise or
  refactor a long skill.
license: MIT
compatibility: Requires python3 (3.10 or later, standard library only).
metadata:
  version: "1.0.0"
---

# Skill split

Every line in `SKILL.md` is loaded into the conversation context the moment the
skill activates. Reference tables for one branch, long example documents and
multi-line scripts that the agent could execute instead of reading all compete
for attention with the core procedure. Splitting moves that weight into files
loaded only when the task needs them.

## 1. Measure the sections

Paths below are relative to this skill's directory.

```bash
python3 scripts/plan_split.py <skill-dir> [--target-lines 300] [--target-tokens 3000] [--json]
```

The planner breaks `SKILL.md` into sections, counts the lines, tokens, fenced
code lines and table rows in each, and classifies every section into one of
three actions:

| Action | Meaning | Destination |
|---|---|---|
| `keep-inline` | Core procedure steps, preconditions and verification needed on every run. | Stays in `SKILL.md`. |
| `extract-script` | A section dominated by executable code that the agent runs the same way each time. | `scripts/<name>.<ext>` |
| `extract-reference` | Lookup tables, error catalogues, schemas, long examples or branch-specific detail. | `references/<topic>.md` |

Show the proposed plan to the user before moving any text, especially if a
section is borderline between core procedure and reference detail.

## 2. Extract executable code into `scripts/`

For each `extract-script` section:

1. Turn the inline code block into a standalone script under `scripts/` that
   accepts its inputs as command-line arguments and exits non-zero with a
   clear message on failure.
2. Add a shebang (`#!/usr/bin/env python3` or `#!/usr/bin/env bash`) and use
   LF line endings.
3. Replace the long code block in `SKILL.md` with a one-line command invocation
   and a short table or list explaining the output.
4. Run the new script once (`--help` or a safe dry run) to prove it parses.

## 3. Extract detail into `references/` and `assets/`

For each `extract-reference` section:

1. Move boilerplate templates and starter files that the agent copies or fills
   in to `assets/`.
2. Move lookup tables, rule lists, edge-case catalogues and per-target guides
   to `references/<topic>.md`.
3. Keep references **one level deep** from `SKILL.md`. Do not chain
   `SKILL.md -> references/<first>.md -> references/<second>.md`; agents rarely
   follow a second hop.
4. In `SKILL.md`, replace the removed section with a direct link and a clause
   saying *when* to open it:

   ```markdown
   Read [references/error-codes.md](references/error-codes.md) when the command
   exits with a non-zero status.
   ```

   A link that never says when to read the file forces the agent either to
   open it every time (saving nothing) or to skip it when it matters.

## 4. Keep the spine in `SKILL.md`

After extraction, `SKILL.md` should still read as a complete procedure from
start to finish without opening any reference file for the common case:

- Preconditions and inputs.
- Numbered steps in execution order.
- Links to `scripts/` and `references/` at the exact step where each is needed.
- How to verify the result.

## 5. Verify

1. Re-run `python3 scripts/plan_split.py <skill-dir>` and confirm the body is
   within the target line and token budget.
2. If the `skill-lint` skill is installed, run it with `--strict` on the split
   skill. It verifies that every extracted file is linked (`W030`), every link
   resolves (`E040`), and no reference chains to another reference (`I002`).
