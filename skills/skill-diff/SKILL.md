---
name: skill-diff
description: >-
  Compares two versions of an Agent Skill and explains the change in terms of
  trigger reach, procedure steps, verification, context budget and security
  surface. Use when reviewing a pull request or commit that edits a skill,
  when comparing two duplicate copies of a skill before merging them, or when
  asked what changed in a skill.
license: MIT
compatibility: Requires python3 (3.10 or later, standard library only); git is needed for --git-ref.
metadata:
  version: "1.0.0"
---

# Skill diff

A line-by-line text diff of `SKILL.md` shows which words moved, not what the
agent will do differently. This skill translates an edit into its effect on
triggering, behaviour, context cost and trust.

## 1. Run the structural diff

Paths below are relative to this skill's directory.

To compare two skill directories on disk:

```bash
python3 scripts/diff_skill.py <old-skill-dir> <new-skill-dir> [--json]
```

To compare a skill in a git repository against an earlier revision:

```bash
python3 scripts/diff_skill.py <skill-dir> --git-ref <ref> [--json]
```

The script reports:

- **Trigger keywords added and removed** from `name` and `description`.
- **Frontmatter fields** added, removed or altered.
- **Context budget delta** across the always-loaded listing, the body and
  bundled resources.
- **Sections and files** added, removed or modified.
- **New external hosts** and any newly introduced specification errors.

Exit status is `1` when the new version introduces a frontmatter or
specification error, and `0` otherwise.

## 2. Read the behavioural changes

Open every file listed under `files.modified` or `files.added` and read the
changed passages. Answer four questions:

1. **When does it fire now?** Look at `trigger.keywords_added` and
   `trigger.keywords_removed`, and read the old and new `description` side by
   side. Did the scope widen, narrow, or shift? Could the new wording collide
   with another skill?
2. **What will the agent do differently?** Walk through the steps from top to
   bottom. Note any step that was added, dropped, reordered, or softened from
   a requirement into a suggestion.
3. **Was a check or guardrail weakened?** Pay special attention to deleted
   pitfalls, removed verification steps, broadened `allowed-tools`, or a rule
   whose reason ("because ...") was edited out.
4. **Did the trust surface grow?** If `hosts.added` is non-empty, or if a
   script under `scripts/` was added or changed, review those additions with
   the same care as a newly installed skill. If the `skill-audit` skill is
   installed, run it on the new version.

## 3. Check for regressions

- If the `skill-lint` skill is installed, run it with `--strict` on the new
  version to catch broken links or orphaned files created by the edit.
- If the `skill-port` skill is installed, check whether the edit introduced
  tool names or substitutions tied to a single harness.
- If the skill has a trigger evaluation file from `skill-tune`, check that the
  new description still covers the test cases.

## 4. Report

Present the review in this order:

1. **Summary in one sentence**: the intent and net effect of the change.
2. **Trigger change**: requests that will now fire (or stop firing) because of
   the description edit.
3. **Behavioural change**: steps, scripts, or verification checks added,
   changed or removed.
4. **Budget and risk**: token delta, new files or external hosts, and any
   lint, portability or audit findings.
