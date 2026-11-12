---
name: skill-retro
description: >-
  Runs a post-mortem on an Agent Skill that loaded but produced the wrong
  behaviour, traces the failure to specific lines in the skill, and patches
  the skill so it does not recur. Use when a skill gave a wrong, incomplete
  or unexpected result, when the agent skipped or misread a step in a skill,
  when the user says the skill got it wrong or to fix the skill, or right
  after correcting output that a skill produced.
license: MIT
metadata:
  version: "1.0.0"
---

# Skill retro

When a skill produces a bad result, the usual response is to fix the result.
The skill stays as it was and fails the same way next time. This skill fixes
the cause.

If the skill never loaded at all, that is a description problem; use
`skill-tune` if it is installed. This skill is for skills that loaded and then
went wrong.

## 1. Collect the evidence

Before forming a theory, write down four things:

- **Request.** What the user asked for.
- **Expected.** What should have happened. Ask the user if unsure.
- **Actual.** What happened: the action taken, the output, the error.
- **Skill text.** Re-read the whole skill now, including any reference file
  or script involved. Do not work from memory of it.

If the failure happened in an earlier session and the details are gone, ask
the user for the output or reproduce it. A fix for a failure nobody can
describe is a guess.

## 2. Classify the failure

Find the row that matches. If two match, the earlier one is usually the cause.

| Class | Evidence | Remedy |
|---|---|---|
| **Stale** | The skill names a command, flag, path or API that no longer exists or changed. | Update it, and add the check that would catch the next change (a version test, an existence check). |
| **Wrong** | The skill was followed correctly and the result was still wrong. | Correct the instruction. Find out whether it was ever right. |
| **Missing case** | The situation is not covered; the agent improvised. | Add the case. If cases are piling up, state the principle behind them. |
| **Ambiguous** | The text supports the wrong reading as well as the right one. | Rewrite so only one reading is possible. Add an example of the right outcome. |
| **Buried** | The right instruction exists, far down or inside a long paragraph, and was not applied. | Move it to where the decision is made. Shorten what surrounds it. |
| **Skipped** | A clear, visible step was not done. | Say why the step matters and what breaks without it. Make its result required by the next step, or have a script perform it. |
| **Contradiction** | Two parts of the skill, or the skill and its script, disagree. | Decide which is right and remove the other. |
| **Script defect** | A bundled script failed or returned bad output. | Fix the script, with the failing input as a test. |
| **Over-constrained** | The skill forced a method that did not fit this case. | State the goal and the reason, and loosen the method. |
| **Not the skill** | The skill was right and was followed; the fault lies in the request, the environment or another skill. | Do not edit the skill. Say where the fault lies. |

## 3. Point at the lines

Quote the exact lines of the skill that caused the failure, or state exactly
where a missing instruction should have been. If no line can be pointed at,
the diagnosis is not finished. Go back to step 2.

Show the user the classification and the quoted lines before editing. One
sentence each is enough.

## 4. Patch

- **Change as little as possible.** Fix the cause. Leave the rest alone.
- **Prefer editing to appending.** A new warning added at the end, on top of
  the text that caused the problem, leaves the cause in place and makes the
  skill longer. Rewrite the faulty passage.
- **Give the reason.** "Run the migration before the tests, because the tests
  read the new schema" survives situations that "ALWAYS run the migration
  FIRST" does not.
- **Do not escalate emphasis.** Capitals and "CRITICAL" help once. A skill
  full of them has no way left to mark what matters, and the agent weighs
  them all the same.
- **Move mechanical steps into a script.** A step that must happen exactly
  the same way every time is better executed than remembered.
- **Generalise one level, no more.** Fix the class of situation this failure
  belongs to. Do not add rules for failures that have not happened.

Check who owns the skill before editing it:

- A skill inside a plugin cache, a synced folder or a built-in directory is
  overwritten when its owner updates it. Do not edit it in place. Offer to
  report the problem upstream, or to copy the skill to the user or project
  level and fix the copy.
- A skill in a shared repository is changed the way that repository changes:
  on a branch, with the reason in the commit message.

## 5. Prove the fix

1. **Replay the failure.** Take the original request through the patched
   skill. With subagents available, give a fresh one only the patched skill
   and the request, so the test does not benefit from this conversation.
   Without them, walk through the patched text step by step and show where
   the path now differs.
2. **Check for regressions.** Run one request the skill handled well before.
   A fix that breaks the common case is not a fix.
3. If the `skill-lint` skill is installed, run it on the patched skill.

If the replay cannot be run here, say so. Report the patch as untested, not
as fixed.

## 6. Record it

Report to the user: the class of failure, the lines changed, how it was
tested, and what remains untested.

If the skill keeps a version under `metadata`, increase it. If the same skill
has now needed three or more retros, say so: repeated patching is a sign that
its scope or structure is the real problem, and a rewrite will cost less than
the next patch.
