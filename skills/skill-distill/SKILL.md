---
name: skill-distill
description: >-
  Turns the workflow just completed in the current session into a reusable
  Agent Skill, capturing the steps that worked, the dead ends, the user's
  corrections and the verification into a new SKILL.md with supporting
  scripts. Use when the user says to save this as a skill, make a skill from
  this, remember how to do this next time or turn this into a reusable
  workflow, or after finishing a hard-won multi-step task that is likely to
  recur.
license: MIT
metadata:
  version: "1.0.0"
---

# Skill distill

The most valuable skill content is what this session learned the hard way:
the approach that failed, the flag that mattered, the correction the user had
to make. That knowledge is in the conversation now and gone when it ends. This
skill extracts it while it is still available.

## 1. Decide whether it should be a skill

A skill earns its place when all three hold:

- **It will recur.** The same kind of task is likely to come up again.
- **It is not obvious.** A capable agent starting cold would get it wrong, or
  get it right only after the same detours.
- **It is a procedure.** There are steps, a decision or a check, not one fact.

If it fails the test, say so and suggest the better home:

| What was learned | Better home |
|---|---|
| One fact or preference ("use pnpm here") | The project's agent instruction file, or memory |
| A rule that must hold every time, mechanically | A hook, linter rule or CI check |
| A one-off | Nothing |

## 2. Mine the session

Go back through the conversation and collect, in this order of value:

1. **User corrections.** Every time the user redirected the work. Each is a
   mistake a future agent will repeat unless the skill prevents it.
2. **Dead ends.** What was tried and abandoned, and the reason. Record as
   "do not do X, because Y; do Z".
3. **The path that worked.** The steps in their final order, not the order
   they were discovered in.
4. **Exact commands and values that were fragile**: a flag, a version, an
   order of operations, a path that had to be exactly so.
5. **How success was verified.** The command or observation that proved it.
6. **Preconditions.** Tools, access, state that had to be true first.

If the session was compacted or the early part is no longer visible, say what
is missing and ask the user to fill the gap. Do not invent steps.

## 3. Generalise, carefully

- Replace this session's specifics (file names, ticket numbers, branch names)
  with a description of the input.
- Keep specifics that are true of the environment and not of the task, such as
  the test command for this repository.
- Leave out anything a capable agent already knows. The skill holds what is
  particular to this workflow.
- Match strictness to fragility. Where any reasonable approach works, state
  the goal. Where one exact sequence works and the others fail, give the exact
  sequence and say why.
- Give the reason with each rule. An agent that knows why can handle the case
  the rule did not foresee.

## 4. Extract scripts

Anything that was run the same way more than once, or that must be run exactly
right, becomes a script in the skill's `scripts/` directory. The agent then
runs it and does not retype it. A script must take its inputs as arguments,
fail with a clear message and need no editing before use.

Do not ship a script that was never run. Run it once on the real case first.

## 5. Write the skill

Choose where it goes. A skill tied to one repository belongs in that
repository's skills directory so the team gets it. A skill for the user's own
habits belongs at user level. If the session does not make the choice clear,
ask.

Start from [assets/SKILL.template.md](assets/SKILL.template.md). Fill it in;
delete sections that have nothing real to say.

For the description, which decides whether the skill is ever loaded:

- First sentence: what it does, with a concrete verb and object.
- Then "Use when ..." with the situations and the words a user would type.
  Take those words from how the user actually phrased the request in this
  session.
- Third person. No summary of the steps; an agent that reads the steps in the
  description may follow that summary and skip the body.

Name: lowercase words joined by hyphens, the same as the directory, saying
what it does (`release-notes`, not `helper`).

## 6. Check it

1. If the `skill-lint` skill is installed, run it with `--strict` and fix what
   it reports.
2. Read the skill as an agent with no memory of this session. For each step,
   ask: could it be done from the page alone? Every "it knows what I mean" is
   a gap.
3. If subagents are available, give one only the skill and a fresh instance of
   the task, and watch where it stalls. That is the strongest test. Otherwise
   offer the user the choice to try it in a new session.

## 7. Hand over

Tell the user where the skill was written, what triggers it, what was left out
on purpose, and what was not tested. If writing it revealed that an existing
skill already covers part of this, say so and offer to extend that one.
