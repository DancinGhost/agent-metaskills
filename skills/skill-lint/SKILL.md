---
name: skill-lint
description: >-
  Validates Agent Skills against the agentskills.io specification and reports
  frontmatter errors, YAML traps, broken file references, orphaned files and
  context-budget overruns. Use when a skill was just written or edited, when
  a skill fails to load or never appears in the skill list, before publishing
  or committing a skill, or when asked to check, validate, lint or review the
  structure of a SKILL.md.
license: MIT
compatibility: Requires python3 (3.9 or later, standard library only).
metadata:
  version: "1.0.0"
---

# Skill lint

Checks that a skill will load in any spec-compliant agent and that the agent
will be able to find everything in it. The linter is deterministic; the fixes
are yours to make.

## Run it

Paths below are relative to this skill's directory.

```bash
python3 scripts/lint_skill.py <skill-dir-or-parent-dir> [more paths] [--strict] [--json]
```

- A path may be one skill directory or a directory holding many skills.
- Exit status is `1` when there is at least one error. With `--strict`,
  warnings fail too. Use `--strict` before publishing and in CI.
- `--json` gives the same findings as structured data, for scripting.

## Read the output

Each line is `level code file:line message`, followed by one budget line per
skill.

| Level | Meaning | What to do |
|---|---|---|
| `error` | The skill breaks the specification or points at a file that is not there. Some agents will refuse to load it. | Fix every one. |
| `warning` | The skill loads, but will trigger badly, waste context or confuse the agent. | Fix, or be able to say why not. |
| `info` | Portability notes. | Read once; no action needed for a single-harness skill. |

The budget line estimates tokens at three stages: the listing (name and
description, loaded into every session), the body (loaded on activation) and
the resources (loaded only when read). A large listing figure costs every
session, whether or not the skill is used.

The full rule list with the reasoning behind each rule is in
[references/rules.md](references/rules.md). Read it when a finding is unclear
or you believe it is a false positive.

## Fix in this order

1. **Errors in the frontmatter (`E00x`, `E01x`, `E02x`, `E03x`).** Until these
   are fixed, the skill may be invisible, and later findings are unreliable.
   `E003` is the most common cause of a skill that silently never loads: an
   unquoted `description` containing `: ` or ` #`. Rewrite the value as a
   block scalar:

   ```yaml
   description: >-
     Does X. Use when: the user asks for Y.
   ```

2. **Broken references (`E040`, `W041`, `W042`).** Either create the file,
   correct the path, or delete the mention. Never leave an instruction that
   sends the agent to a file that does not exist.
3. **Orphans (`W030`).** A file nothing mentions is a file the agent will
   never open. Link it from SKILL.md with a sentence saying when to read it,
   or delete it.
4. **Description quality (`W010`, `W011`, `W012`).** State what the skill does
   and when to use it, in the third person, using words a user would type.
5. **Budget (`W020`, `W021`).** Move reference material, long examples and
   rarely used branches into separate files that SKILL.md links to, one level
   deep.

Re-run after each round. Stop when the output is clean or every remaining
warning has a reason.

## Limits

- The linter checks structure, not whether the instructions are any good. A
  clean result does not mean the skill works; test it on a real task.
- Token counts are estimates (about four characters per token).
- Rules marked as heuristics in the reference can misfire on unusual phrasing.
  Do not contort a good description to silence a heuristic.
