---
name: skill-tune
description: >-
  Diagnoses and fixes when an Agent Skill is selected, by testing its
  description against realistic requests and rewriting it. Use when a skill
  does not trigger or is ignored, when a skill fires on requests it should
  not handle, when two skills compete for the same request, or when asked to
  improve, optimise or rewrite a skill description.
license: MIT
compatibility: Requires python3 (3.10 or later, standard library only).
metadata:
  version: "1.1.0"
---

# Skill tune

An agent chooses a skill from its name and description alone. The body is not
read until after that choice. So a skill that never fires, or fires at the
wrong time, has a description problem, and the fix is tested the way any
classifier is: against examples.

This skill changes the description only. If the skill triggers correctly and
then does the wrong thing, the problem is in the body; use `skill-retro` if it
is installed.

## 1. Name the symptom

| Symptom | Meaning |
|---|---|
| Never fires on requests it should handle | Under-triggering: the description lacks the words and situations users bring. |
| Fires on requests it should not handle | Over-triggering: the description is broader than the skill. |
| A different skill fires instead | Collision: two descriptions claim the same ground. |

Get one or two real requests where it went wrong. Without a concrete failure
there is nothing to tune against.

First rule out causes that are not the description: the skill is not installed
where the harness looks, its frontmatter does not parse, or the harness has it
disabled. Listing the available skills in a fresh session settles all three.

## 2. Build a test set

Write 16 to 20 requests as a user would type them: varied length, some terse,
some with typos or indirect phrasing, most not naming the skill.

- **Should trigger (half).** Cover each distinct use of the skill. Include
  the real failures from step 1. Include indirect requests that describe the
  problem and not the solution.
- **Should not trigger (half).** Near misses are the only useful negatives:
  requests that share vocabulary with the skill but belong to another skill
  or to no skill. "What is the weather" tests nothing.

Save the set next to the skill, outside the skill directory, using the format
in [assets/trigger-evals.template.json](assets/trigger-evals.template.json).
Set aside a quarter of each half as a holdout and do not look at those while
rewriting.

Validate the test set and check lexical coverage with the helper script
(paths below are relative to this skill's directory):

```bash
python3 scripts/eval_triggers.py <skill-dir> --evals <evals.json> [--root <skills-dir>] [--json]
```

The script checks that both halves and the holdout are populated, flags
should-trigger queries that share no keywords with the description (blind
spots), flags should-not queries that heavily overlap the description, and
warns when a competing skill under `--root` has a stronger lexical match.

Show the set to the user before going on. They know which requests are
realistic.

## 3. Measure the current description

Pick the strongest method available and use the same one before and after.

1. **Real runs.** If the harness can run headless or spawn a fresh session,
   send each request to a new session and record whether the skill loaded.
   Repeat each request three times; triggering is not deterministic.
2. **Blind judge.** If subagents are available, give a subagent only the list
   of names and descriptions of all installed skills, plus one request, and
   ask which skill, if any, it would load. It must not see the expected
   answer or the skill bodies.
3. **Self-review.** If neither is available, judge each request yourself
   against the full list of descriptions, and tell the user this is the
   weakest method because you know the intended answer.

For collisions, the other skills' descriptions must be in the list. If the
`skill-inventory` skill is installed, it produces that list and flags
overlapping pairs.

Record a score for each half: how many should-trigger requests fired, how many
should-not requests stayed quiet.

## 4. Rewrite

Change the description to fix the failures seen in step 3, not in general.

**For under-triggering:**

- Add the situations and words from the missed requests. Users describe
  symptoms ("the build is red"), not skill names.
- Name the file types, tools and artefacts involved.
- Put the main use first. Listings can cut a long description short.

**For over-triggering:**

- Replace category words ("documents", "data") with the specific things the
  skill handles.
- State the boundary: "Not for X; use Y for that."

**For collisions:**

- Edit both descriptions so each names what the other is for. A boundary
  stated on one side only still leaves the choice ambiguous.
- If the two skills cannot be told apart in a sentence each, they should
  probably be one skill.

**Always:**

- What it does, then when to use it. Third person.
- Do not summarise the body's steps in the description. An agent may act on
  the summary and never read the body.
- Stay within 1024 characters, and avoid unquoted `: ` and ` #`, which break
  YAML. A folded block scalar (`description: >-`) avoids the quoting problem.
- Resist adding "ALWAYS" and "MUST" to force a trigger. It raises false
  triggers and competes with every other skill doing the same.

## 5. Re-measure and iterate

Before editing `SKILL.md`, you can test a candidate description against the
evaluation set with:

```bash
python3 scripts/eval_triggers.py <skill-dir> --evals <evals.json> --description "<candidate>"
```

Run the same test with the new description. Keep the change only if the score
improved without the other half getting worse. Up to three rounds; if it is
not converging, the skill's scope is the problem, not its wording. Say so.

Then run the holdout once. A description that passes the working set and
fails the holdout was fitted to the examples; generalise it and re-test.

## 6. Report

Show the user the old and new description, the scores before and after for
both halves and the holdout, the method used, and any request that still
fails. Apply the change only when they agree. Keep the test set; it is the
regression test for the next edit.
