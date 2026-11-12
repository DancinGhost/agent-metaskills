---
name: skill-inventory
description: >-
  Lists every Agent Skill installed for the current user and project across
  Claude Code, Codex, Gemini CLI and Antigravity, and reports duplicate names,
  skills that fail to load, descriptions that compete for the same request,
  and the context cost of the skill listing. Use when asked which skills are
  installed or available, when the wrong skill fires or two skills conflict,
  when a skill seems to be shadowed or missing, or when cleaning up, pruning
  or deduplicating skills.
license: MIT
compatibility: Requires python3 (3.10 or later, standard library only).
metadata:
  version: "1.0.0"
---

# Skill inventory

Answers "what skills are actually in play here, and are any of them getting
in each other's way?" from the file system, not from memory of what is
installed.

## Run it

Paths below are relative to this skill's directory.

```bash
python3 scripts/inventory.py [--project <dir>] [--root <dir> ...] [--no-user] [--threshold 0.4] [--json]
```

- `--project` is the project to inspect; it defaults to the current directory.
- `--root` adds a directory the script does not know about. Repeatable.
- `--no-user` limits the scan to the project.
- `--threshold` sets how similar two descriptions must be (0 to 1) to be
  reported as competing. Lower it to see more candidate pairs.
- The script only reads. It never changes or removes a skill.

The last section of the output, "Searched", shows each location and whether it
exists. If the user's harness keeps skills somewhere not listed there, find
that directory and pass it with `--root`.

## Read the output

1. **The listing**, grouped by location. A trailing `!` marks a skill with a
   load problem.
2. **Always-loaded listing cost.** Every installed skill's name and
   description is placed in the context of every session. This is the
   estimated total. It is the price of having skills installed, paid whether
   or not they are used.
3. **Same name in more than one place.** Only one copy wins in a given
   harness, and which one depends on that harness's precedence rules. In
   Gemini CLI, for example, workspace skills override user skills. Do not
   guess for other harnesses; check their documentation or ask the harness
   to list its skills.
4. **Skills that break the specification.** Missing or invalid frontmatter,
   or a name that does not match its directory. Strict harnesses skip these,
   so a skill can be installed and still invisible.
5. **Descriptions that may compete.** Pairs with heavy keyword overlap. This
   is a lexical measure; treat each pair as a question, not a verdict.

## Act on it

Report findings first. Change nothing until the user agrees.

| Finding | Recommendation |
|---|---|
| Duplicate name, identical content | Keep one copy at the widest scope that needs it; remove the others. |
| Duplicate name, different content | Show the differences. The user picks one or renames one. |
| Broken skill | Fix the frontmatter. If the `skill-lint` skill is installed, use it for the exact errors. |
| Competing pair, same job | Merge them, or retire the weaker one. |
| Competing pair, different jobs | Sharpen both descriptions so each says what it is not for. If the `skill-tune` skill is installed, use it. |
| Large listing cost | Suggest removing skills that are never used, moving project-only skills out of the user scope, and shortening long descriptions. |

Before deleting or moving anything:

- Confirm with the user, naming the exact paths.
- Do not edit skills inside a plugin cache, a synced folder or a built-in
  directory. The owning tool overwrites them. Disable or uninstall through
  that tool.
- A symlinked skill is shared with wherever the link points. Removing the
  link is safe; editing through it changes the original.

## Limits

- The script knows the locations listed in its "Searched" output. Enterprise
  or managed locations and unusual installs need `--root`.
- Finding a skill on disk does not prove the harness has it enabled; a harness
  can disable skills through its own settings.
- Token figures are estimates (about four characters per token).
