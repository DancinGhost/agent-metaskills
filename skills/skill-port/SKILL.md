---
name: skill-port
description: >-
  Makes an Agent Skill work in other agent harnesses by finding and rewriting
  the parts tied to one tool, such as Claude Code frontmatter extensions,
  argument substitutions, load-time command injection, tool names and
  hard-coded config paths. Use when porting, converting or migrating a skill
  between Claude Code, Codex, Gemini CLI, Antigravity or another agent, when
  a skill works in one tool but not another, or when preparing a skill to be
  shared publicly.
license: MIT
compatibility: Requires python3 (3.10 or later, standard library only).
metadata:
  version: "1.0.0"
---

# Skill port

The SKILL.md format is shared across harnesses. The things a skill body
refers to (tool names, substitution variables, config files, hooks) are not.
Porting means finding those references and restating them as capabilities.

## Procedure

Paths below are relative to this skill's directory.

### 1. Settle the target

Ask only if it is unclear: is the goal one specific target harness, or one
skill that works everywhere? Prefer a single portable skill. Maintain separate
variants only when the skill depends on a feature with no equivalent.

### 2. Find what is harness-specific

```bash
python3 scripts/portability_check.py <skill-dir> [--json]
```

Findings come in three levels:

| Level | Meaning |
|---|---|
| `breaks` | Fails or misleads elsewhere: the agent sees literal placeholder text, a hook never runs, a trigger hint is never read. |
| `adapt` | Works after rewording: a tool name, a config path, a field to move. |
| `note` | Worth declaring: required programs, platform limits. |

Each finding carries a suggested fix. Exit status is `1` when anything is at
`breaks` level.

### 3. Rewrite

Work on a copy if the original must keep working where it is.

- **Tools become actions.** Name what to do, not which tool does it: "search
  the repository for the symbol", "ask the user which environment", "run the
  script". Every harness maps that to its own tools. Keep an exact tool name
  only where no description would be unambiguous, and then give the
  per-harness names side by side.
- **Substitutions become sentences.** Replace an argument placeholder with a
  description of the input ("the file the user named") and tell the agent to
  ask when it is missing. Replace skill-directory variables with paths
  relative to the skill directory.
- **Load-time commands become step one.** State the command and what to take
  from its output.
- **Trigger hints move into `description`.** It is the only field every
  harness reads when choosing a skill.
- **Behaviour carried by frontmatter moves into the body.** If a hook
  enforced a rule, write the rule as an instruction and say how to verify it.
  If the skill ran in a forked subagent, say "delegate this to a subagent if
  one is available; otherwise do it inline and keep the output brief". Say
  plainly to the user when a guarantee became a request: an instruction is
  weaker than a hook.
- **Config paths become roles**, such as "the project's agent instruction
  file", or a short table of the per-harness equivalents.
- **Requirements go in `compatibility`**: interpreters, command-line tools,
  network access.

Do not delete a harness-specific feature the user relies on without saying
so. If dropping it changes behaviour, report that.

### 4. Place it

[references/harnesses.md](references/harnesses.md) lists where each harness
looks for skills, which frontmatter each understands, and how to confirm a
skill was picked up. Read it before choosing an install path. If the target is
not listed, or the reference looks out of date, check the harness's own
documentation; these locations change.

A directory named `.agents/skills` is read by several harnesses. Use it when
one copy should serve more than one tool.

### 5. Verify

1. Run the portability check again. No `breaks` findings should remain.
2. If the `skill-lint` skill is installed, run it with `--strict`.
3. In the target harness, list the skills and confirm this one appears with
   the expected description.
4. Run one real task that should trigger it. Listing proves discovery, not
   behaviour.

If the target harness is not available in this session, say so and hand the
user steps 3 and 4 to run themselves. Do not report the port as verified.

## Limits

- The check recognises known Claude Code, Gemini CLI and Codex constructs. A
  skill written for another harness may carry specifics it does not know.
- Tool-name detection is a heuristic. An ordinary word that happens to match
  a tool name ("Read the file") is ignored unless the text clearly means the
  tool.
