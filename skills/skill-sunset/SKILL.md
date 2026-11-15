---
name: skill-sunset
description: >-
  Finds installed Agent Skills that are never used in session transcripts and
  reports the always-loaded context tokens they cost every session. Use when
  cleaning up, pruning or retiring unused skills, when the skill listing has
  grown too large, or when asked which skills are actually used.
license: MIT
compatibility: Requires python3 (3.10 or later, standard library only).
metadata:
  version: "1.0.0"
---

# Skill sunset

Every installed skill's name and description is injected into the context of
every session, whether or not the skill ever fires. A skill installed months
ago for a one-off task keeps taxing every new conversation and widens the pool
of descriptions that can misfire. This skill checks local session transcripts
to see which skills earn their keep.

## 1. Measure actual usage

Paths below are relative to this skill's directory.

```bash
python3 scripts/usage_report.py [--project <dir>] [--root <skills-dir> ...] [--logs <transcripts-dir> ...] [--days 30] [--no-user] [--json]
```

- `--days` sets the lookback window in days (default `30`; pass `0` to scan
  all available transcripts).
- `--root` adds an extra skills directory to inspect.
- `--logs` adds an extra session transcript directory or file when a harness
  stores logs in a custom location.
- `--no-user` restricts the scan to the current project.
- The script is strictly read-only. It counts a skill as active in a session
  only when the session opened the skill's `SKILL.md`, ran or read one of its
  bundled files, invoked it through a skill-activation tool, or called it as a
  slash command. Passive listings in system prompts are ignored.

## 2. Diagnose why a dormant skill was never used

A skill with zero activations in the window falls into one of three buckets:

| Cause | How to tell | What to do |
|---|---|---|
| **Obsolete or one-off** | The project, tool or migration it was written for is finished. | Retire or archive it. |
| **Wrong scope** | Installed at user level (`~`), so it loads in every project, even though it only applies to one repository. | Move it into that repository's project-level skills directory. |
| **Under-triggering** | The user still does the task by hand, and the skill should have fired. | Keep the skill and fix its description with `skill-tune`. |

Ask the user before treating zero activations as proof that a skill is
unwanted. Some skills are seasonal (for example, quarterly release or incident
runbooks) or have a description too narrow to fire.

## 3. Retire or rescope

Change nothing until the user agrees on the exact path and action for each
dormant skill:

- **Move to project scope**: move a repository-specific skill from the user's
  global skills directory into that repository's skills directory, so other
  projects stop paying its listing cost.
- **Archive instead of deleting**: if the user might want the workflow again
  later, move the skill directory into a `.trash/` or archive folder outside
  the active skills directory (harnesses and `skill-inventory` skip `.trash`).
- **Remove a symlink**: if the skill is a symlink, removing the link leaves
  the source repository intact.
- **Built-in or plugin skills**: do not delete files inside a plugin cache or
  built-in directory; disable or uninstall the plugin through the harness
  instead.

## 4. Report

Show the user:

1. How many session transcripts were scanned and over what time window.
2. Which skills were active and how recently.
3. The dormant skills ranked by their per-session token cost, with a
   recommendation (`retire`, `move to project`, or `tune description`) for
   each.
4. The total always-loaded tokens per session saved once the agreed changes
   are made.
