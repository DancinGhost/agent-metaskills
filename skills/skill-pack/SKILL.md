---
name: skill-pack
description: >-
  Builds distributable artefacts from one or more Agent Skills: a
  specification-clean directory, a reproducible zip archive for upload, or a
  plugin bundle with manifests. Use when preparing a skill to upload or share,
  when a host rejects non-specification frontmatter fields, or when packaging
  loose skills into a plugin or archive.
license: MIT
compatibility: Requires python3 (3.10 or later, standard library only).
metadata:
  version: "1.0.0"
---

# Skill pack

A skill on your machine often carries extras that strict uploaders reject:
single-harness frontmatter extensions, stray bytecode or editor swap files,
CRLF line endings, or unquoted colons in `description`. This skill builds a
clean distributable from the source without altering the working copy.

## 1. Check the source first

1. If the `skill-lint` skill is installed, run it with `--strict` on the
   source skill and fix any broken links (`E040`) or orphaned files (`W030`).
2. If the `skill-port` skill is installed and the package is meant for users
   on other harnesses, run the portability check so harness-specific tool
   names or substitutions in the body are caught before packaging.

## 2. Build the package

Paths below are relative to this skill's directory.

```bash
# Reproducible .zip archive (one zip per skill, or one combined zip if --output ends in .zip)
python3 scripts/pack_skill.py <skill-dir-or-repo> --output <dest> --format zip [--json]

# Specification-only skill directory
python3 scripts/pack_skill.py <skill-dir-or-repo> --output <dest-dir> --format spec-dir [--json]

# Plugin bundle with skills/<name>/ and plugin manifests
python3 scripts/pack_skill.py <skill-dir-or-repo> --output <dest-dir> --format plugin [--plugin-name <name>] [--json]
```

What the packager does automatically:

- **Merges `when_to_use` into `description`** (if present and within the
  1024-character limit) before stripping non-specification frontmatter fields,
  so trigger cues are not lost.
- **Strips fields outside the specification** (`name`, `description`,
  `license`, `compatibility`, `metadata`, `allowed-tools`), unless
  `--keep-extensions` is passed.
- **Reformats frontmatter YAML** so unquoted `: ` and ` #` traps cannot trip
  strict parsers.
- **Normalises line endings** to LF across `SKILL.md` and text resources.
- **Omits junk files** (`__pycache__`, `.pyc`, `.DS_Store`, swap files) and
  refuses to pack symlinks that point outside the skill directory.

Exit status is `1` when a skill fails validation, `2` on usage errors, and `0`
otherwise.

## 3. Report

Tell the user which output files were written, how many files and bytes each
skill contains, and any frontmatter fields that were merged or stripped so they
know if behaviour enforced by a harness extension (such as `hooks` or
`context: fork`) is not present in the packaged artefact.
