# Lint rules

Limits come from the Agent Skills specification at
<https://agentskills.io/specification>. Rules marked *heuristic* are pattern
matches and can misfire.

## Errors

| Code | Rule | Why it matters |
|---|---|---|
| E001 | The directory has a file named exactly `SKILL.md`. | Discovery is by exact file name; `skill.md` is not found on case-sensitive file systems. |
| E002 | `SKILL.md` starts with YAML frontmatter between two `---` lines. | Without it there is no name or description to list. |
| E003 | The frontmatter is valid YAML. | See "YAML traps" below. Harnesses differ: some fail loudly, some drop the skill silently, some load a truncated value. |
| E010 | `name` is present. | Required field. |
| E011 | `name` is 1-64 characters of `a-z`, `0-9` and single hyphens, with no leading or trailing hyphen. | Required by the specification. |
| E012 | `name` equals the directory name. | Required by the specification; several harnesses key the skill by directory. |
| E020 | `description` is present and not empty. | It is the only thing the agent sees when deciding whether to load the skill. |
| E021 | `description` is at most 1024 characters. | Specification limit. Listings may truncate earlier, so put the main use case first. |
| E030 | `compatibility`, if present, is 1-500 characters. | Specification limit. |
| E031 | `metadata`, if present, maps string keys to string values. | Nested structures are not portable. Quote numbers such as `"1.0"`. |
| E040 | Every Markdown link to a local file resolves. | A dead link sends the agent to read something that is not there. |

## Warnings

| Code | Rule | Why it matters |
|---|---|---|
| W001 | No frontmatter fields beyond the specification and known harness extensions. | Unknown fields are ignored at best and rejected by strict packagers. Put custom data under `metadata`. |
| W002 | `allowed-tools` is one space-separated string. | That is the form the specification defines. |
| W010 | The description is at least 40 characters and says when to use the skill. *Heuristic.* | "Helps with PDFs" gives the agent nothing to match a request against. |
| W011 | The description is in the third person. *Heuristic.* | It is injected into a system prompt next to other descriptions; "I can" and "you can" read as speech from the wrong party. |
| W012 | The description contains no XML-style tags. | Some hosts reject them. |
| W013 | The name does not contain `anthropic` or `claude`. | Some hosts reserve those words. |
| W020 | The body is at most 500 lines. | Recommended ceiling; the whole body loads on activation. |
| W021 | The body is at most about 5000 tokens. | Same reason. Estimated at four characters per token. |
| W022 | The body has at least 20 words. | A skill with no instructions does nothing. |
| W030 | Every bundled file is mentioned by SKILL.md or another file in the skill. | Agents open files they are pointed to. Unmentioned files are dead weight. |
| W040 | Shell scripts start with a shebang. | Otherwise the interpreter is whatever the caller's shell happens to be. |
| W041 | Plain-text mentions such as `scripts/run.py` resolve. *Heuristic.* | Same as E040, for paths that are not Markdown links. Only checked under `scripts/`, `references/`, `assets/`, `resources/` and `examples/`. |
| W042 | Links stay inside the skill directory. | Anything outside is missing after installation. |
| W050 | No machine-specific absolute paths in prose. | `/home/alex/...` exists on one machine. |
| W060 | No leftover placeholders (`TODO`, `TBD`, `[describe ...]`). *Heuristic.* | Template residue reads as an instruction. |

## Info

| Code | Rule |
|---|---|
| I001 | A frontmatter field is a Claude Code extension. Fine for a Claude Code skill; other agents ignore it. |
| I002 | A reference file links to another Markdown file. Keep references one level deep from SKILL.md so the agent can find everything from the entry point. |

## YAML traps

These account for most skills that "exist but never load".

**Colon followed by a space in an unquoted value.**

```yaml
description: Formats code. Use when: the user asks for formatting.   # invalid
```

**Space followed by `#` in an unquoted value.** YAML reads the rest as a
comment, so the description is silently cut short.

```yaml
description: Triages issues tagged #bug and #regression.   # truncated at "tagged"
```

**A value that starts with a reserved character** such as `@`, `` ` ``, `%`,
`*`, `&` or `!`.

The fix for all three is a folded block scalar, which needs no escaping:

```yaml
description: >-
  Formats code. Use when: the user asks for formatting of #bug fixes.
```

**Tabs for indentation** are not valid YAML. Use spaces.

## False positives

- W010 and W011 are keyword heuristics. If the description is specific and
  already says when to use the skill in words the rule does not know, leave it.
- W041 can fire on an example path quoted in prose. Rephrase with a placeholder
  such as `references/<topic>.md`, which the rule skips.
- W030 only sees literal file names. A file loaded through a computed path
  will be reported; mention it by name in SKILL.md anyway, for the agent's sake.
