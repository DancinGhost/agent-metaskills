#!/usr/bin/env python3
"""Lint Agent Skills against the agentskills.io specification.

    python3 lint_skill.py PATH [PATH ...] [--strict] [--json]

PATH is a skill directory or a directory that contains skills. Exit status
is 1 when any error is found (or any warning with --strict), 2 on usage
errors, and 0 otherwise. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # keep the skill directory free of __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _skillmeta as meta  # noqa: E402

ERROR, WARNING, INFO = "error", "warning", "info"

RESOURCE_DIRS = ("scripts", "references", "assets", "resources", "examples")

LINK_RE = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
BARE_PATH_RE = re.compile(
    r"(?<![\w/.<{*-])((?:%s)/[\w./-]*\w\.\w+)" % "|".join(RESOURCE_DIRS)
)
MACHINE_PATH_RE = re.compile(
    r"(/home/[a-z_][\w.-]*/|/Users/[A-Za-z_][\w.-]*/|[A-Z]:\\Users\\)"
)
PLACEHOLDER_RE = re.compile(
    r"\b(TODO|TBD|FIXME|XXX)\b|lorem ipsum|\[(?:describe|insert|your)[^\]]*\]",
    re.IGNORECASE,
)
TRIGGER_CUE_RE = re.compile(
    r"\b(use (?:this |it )?(?:skill )?(?:when|whenever|for|if|before|after|to)"
    r"|when(?:ever)? (?:the |a |an )?(?:user|agent|task|request|you)"
    r"|triggers? (?:on|when|for)|activate (?:this skill )?(?:when|for)"
    r"|invoke (?:when|for)|should be used)\b",
    re.IGNORECASE,
)
FIRST_SECOND_PERSON_RE = re.compile(
    r"\b(I can|I will|I'll|I help|I am)\b|"
    r"(?i:\b(you can use this|helps you|lets you|allows you|i can help)\b)"
)
RESERVED_NAME_WORDS = ("anthropic", "claude")
SCRIPT_SUFFIXES = {".sh", ".bash", ".zsh"}
SAMPLE_LANGUAGES = {
    "markdown", "md", "mdx", "yaml", "yml", "json", "toml", "xml", "html",
    "diff", "text", "txt",
}
IGNORED_FILES = {"LICENSE", "LICENSE.txt", "LICENSE.md", "NOTICE", ".gitignore"}


class Report:
    def __init__(self, skill_dir: Path):
        self.skill_dir = skill_dir
        self.findings: list = []
        self.budget: dict = {}

    def add(self, level, code, message, file="SKILL.md", line=None):
        self.findings.append(
            {
                "level": level,
                "code": code,
                "message": message,
                "file": file,
                "line": line,
            }
        )

    def count(self, level) -> int:
        return sum(1 for f in self.findings if f["level"] == level)


def check_frontmatter(skill, report: Report) -> None:
    fm = skill.frontmatter
    for line, message in skill.problems:
        report.add(ERROR, "E003", f"frontmatter YAML: {message}", line=line)

    name = fm.get("name")
    if not isinstance(name, str) or not name:
        report.add(ERROR, "E010", "frontmatter is missing a 'name' string")
    else:
        if len(name) > meta.NAME_MAX or not meta.NAME_RE.match(name):
            report.add(
                ERROR,
                "E011",
                f"name {name!r} must be 1-{meta.NAME_MAX} characters of "
                "lowercase letters, digits and single hyphens, and must not "
                "start or end with a hyphen",
            )
        if name != skill.path.resolve().name:
            report.add(
                ERROR,
                "E012",
                f"name {name!r} does not match the directory name "
                f"{skill.path.resolve().name!r}",
            )
        for word in RESERVED_NAME_WORDS:
            if word in name:
                report.add(
                    WARNING,
                    "W013",
                    f"name contains {word!r}, which some hosts reserve and "
                    "reject on upload",
                )

    description = fm.get("description")
    if not isinstance(description, str) or not description.strip():
        report.add(
            ERROR, "E020", "frontmatter is missing a non-empty 'description'"
        )
    else:
        check_description(description, report)

    compatibility = fm.get("compatibility")
    if compatibility is not None:
        if not isinstance(compatibility, str) or not compatibility.strip():
            report.add(ERROR, "E030", "'compatibility' must be a non-empty string")
        elif len(compatibility) > meta.COMPATIBILITY_MAX:
            report.add(
                ERROR,
                "E030",
                f"'compatibility' is {len(compatibility)} characters; the "
                f"limit is {meta.COMPATIBILITY_MAX}",
            )

    metadata = fm.get("metadata")
    if metadata is not None:
        if not isinstance(metadata, dict):
            report.add(ERROR, "E031", "'metadata' must be a mapping")
        else:
            for key, value in metadata.items():
                if not isinstance(value, str):
                    report.add(
                        ERROR,
                        "E031",
                        f"metadata.{key} must be a string; nested values "
                        "are not portable",
                    )

    allowed = fm.get("allowed-tools")
    if allowed is not None and not isinstance(allowed, str):
        report.add(
            WARNING,
            "W002",
            "'allowed-tools' is a YAML list; the specification defines it as "
            "one space-separated string",
        )

    for key in fm:
        if key in meta.SPEC_FIELDS:
            continue
        if key in meta.CLAUDE_CODE_FIELDS:
            report.add(
                INFO,
                "I001",
                f"'{key}' is a Claude Code extension; other agents ignore it "
                "and strict packagers reject it",
            )
        else:
            report.add(
                WARNING,
                "W001",
                f"'{key}' is not a field in the Agent Skills specification",
            )


def check_description(description: str, report: Report) -> None:
    length = len(description)
    if length > meta.DESCRIPTION_MAX:
        report.add(
            ERROR,
            "E021",
            f"description is {length} characters; the limit is "
            f"{meta.DESCRIPTION_MAX}",
        )
    if re.search(r"<[A-Za-z/][^>]*>", description):
        report.add(
            WARNING,
            "W012",
            "description contains an XML-style tag, which some hosts reject",
        )
    if length < 40:
        report.add(
            WARNING,
            "W010",
            f"description is only {length} characters; say what the skill "
            "does and when to use it, with the words a user would type",
        )
    elif not TRIGGER_CUE_RE.search(description):
        report.add(
            WARNING,
            "W010",
            "description never says when to use the skill; add a clause "
            "such as 'Use when ...'",
        )
    match = FIRST_SECOND_PERSON_RE.search(description)
    if match:
        report.add(
            WARNING,
            "W011",
            f"description uses first or second person ({match.group(0)!r}); "
            "write it in the third person, as a statement about the skill",
        )


def check_body(skill, report: Report) -> None:
    body = skill.body
    lines = body.split("\n")
    words = len(body.split())
    tokens = meta.estimate_tokens(body)
    if words < 20:
        report.add(
            WARNING,
            "W022",
            f"body has only {words} words; a skill with no instructions "
            "gives the agent nothing to follow",
        )
    if len(lines) > meta.BODY_MAX_LINES:
        report.add(
            WARNING,
            "W020",
            f"body is {len(lines)} lines; keep SKILL.md under "
            f"{meta.BODY_MAX_LINES} and move detail into reference files",
        )
    if tokens > meta.BODY_MAX_TOKENS:
        report.add(
            WARNING,
            "W021",
            f"body is about {tokens} tokens; the recommended ceiling is "
            f"{meta.BODY_MAX_TOKENS}",
        )
    prose = meta.strip_fenced_code(body).split("\n")
    for offset, line in enumerate(prose):
        number = skill.body_line + offset
        match = MACHINE_PATH_RE.search(line)
        if match:
            report.add(
                WARNING,
                "W050",
                f"machine-specific path {match.group(0)!r}; use a path "
                "relative to the skill directory",
                line=number,
            )
        match = PLACEHOLDER_RE.search(line)
        if match:
            report.add(
                WARNING,
                "W060",
                f"leftover placeholder {match.group(0)!r}",
                line=number,
            )


def _resolve_inside(skill_dir: Path, target: str):
    """Return (path, inside) for a link target relative to the skill."""
    path = (skill_dir / target).resolve()
    root = skill_dir.resolve()
    return path, path == root or root in path.parents


def check_references(skill, report: Report) -> None:
    skill_dir = skill.path
    prose = meta.strip_fenced_code(skill.body).split("\n")
    seen = set()
    for offset, line in enumerate(prose):
        number = skill.body_line + offset
        for match in LINK_RE.finditer(line):
            target = match.group(1).split("#")[0].split("?")[0]
            if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):
                continue
            if target.startswith("/"):
                report.add(
                    WARNING,
                    "W050",
                    f"link target {target!r} is an absolute path",
                    line=number,
                )
                continue
            seen.add(target)
            path, inside = _resolve_inside(skill_dir, target)
            if not path.exists():
                report.add(
                    ERROR,
                    "E040",
                    f"link target {target!r} does not exist",
                    line=number,
                )
            elif not inside:
                report.add(
                    WARNING,
                    "W042",
                    f"link target {target!r} is outside the skill directory "
                    "and will be missing once the skill is installed",
                    line=number,
                )
    # Commands in shell blocks are real references; paths inside sample
    # documents (markdown, yaml, json ...) are illustrations.
    fence, sample = None, False
    for offset, line in enumerate(skill.body.split("\n")):
        number = skill.body_line + offset
        stripped = line.strip()
        marker = re.match(r"(`{3,}|~{3,})\s*([\w+-]*)", stripped)
        if marker and fence is None:
            fence = marker.group(1)[0] * 3
            sample = marker.group(2).lower() in SAMPLE_LANGUAGES
            continue
        if fence is not None and stripped.startswith(fence):
            fence, sample = None, False
            continue
        if fence is not None and sample:
            continue
        for match in BARE_PATH_RE.finditer(line):
            target = match.group(1)
            if target in seen:
                continue
            seen.add(target)
            if not (skill_dir / target).exists():
                report.add(
                    WARNING,
                    "W041",
                    f"mentions {target!r}, which does not exist in the skill",
                    line=number,
                )


def check_files(skill, report: Report) -> None:
    skill_dir = skill.path
    files = meta.iter_files(skill_dir)
    texts = {}
    for rel in files:
        text = meta.read_text(skill_dir / rel)
        if text is not None:
            texts[rel] = text

    for rel in files:
        if rel.name.lower() == "skill.md" and rel.name != meta.SKILL_FILE:
            report.add(
                ERROR,
                "E001",
                f"{rel} must be named exactly SKILL.md",
                file=str(rel),
            )
        if len(rel.parts) == 1 or rel.name in IGNORED_FILES:
            continue
        if rel.name.startswith("."):
            continue
        others = [t for other, t in texts.items() if other != rel]
        needles = {rel.as_posix(), rel.name}
        if rel.suffix == ".py":
            needles.add(rel.stem)
        if not any(needle in text for text in others for needle in needles):
            report.add(
                WARNING,
                "W030",
                "file is never mentioned by SKILL.md or any other file in "
                "the skill, so the agent will not find it",
                file=rel.as_posix(),
            )
        if rel.suffix in SCRIPT_SUFFIXES and rel in texts:
            if not texts[rel].startswith("#!"):
                report.add(
                    WARNING,
                    "W040",
                    "shell script has no shebang line",
                    file=rel.as_posix(),
                )

    for rel, text in texts.items():
        if rel.suffix.lower() != ".md" or rel.name == meta.SKILL_FILE:
            continue
        if len(rel.parts) < 2 or rel.parts[0] != "references":
            continue
        for match in LINK_RE.finditer(meta.strip_fenced_code(text)):
            target = match.group(1).split("#")[0]
            if target.lower().endswith(".md") and ":" not in target:
                report.add(
                    INFO,
                    "I002",
                    f"links on to {target!r}; keep references one level "
                    "deep from SKILL.md so the agent can find everything",
                    file=rel.as_posix(),
                )
                break

    resources = sum(
        meta.estimate_tokens(text)
        for rel, text in texts.items()
        if rel.name != meta.SKILL_FILE
    )
    listing = f"{skill.name}: {skill.description}"
    report.budget = {
        "listing_tokens": meta.estimate_tokens(listing),
        "body_tokens": meta.estimate_tokens(skill.body),
        "body_lines": len(skill.body.split("\n")),
        "resource_tokens": resources,
        "files": len(files),
    }


def lint_skill(skill_dir) -> Report:
    skill_dir = Path(skill_dir)
    report = Report(skill_dir)
    skill = meta.load_skill(skill_dir)
    if not skill.skill_md.is_file():
        wrong = [p.name for p in skill_dir.iterdir() if p.name.lower() == "skill.md"]
        hint = f" (found {wrong[0]}; rename it)" if wrong else ""
        report.add(ERROR, "E001", f"no SKILL.md in {skill_dir}{hint}")
        return report
    if not skill.has_frontmatter:
        report.add(
            ERROR,
            "E002",
            "SKILL.md must start with YAML frontmatter between two '---' "
            "lines",
            line=1,
        )
    else:
        check_frontmatter(skill, report)
    check_body(skill, report)
    check_references(skill, report)
    check_files(skill, report)
    order = {ERROR: 0, WARNING: 1, INFO: 2}
    report.findings.sort(
        key=lambda f: (order[f["level"]], f["file"], f["line"] or 0, f["code"])
    )
    return report


def format_report(report: Report) -> str:
    lines = [str(report.skill_dir)]
    if not report.findings:
        lines.append("  ok")
    for finding in report.findings:
        where = finding["file"]
        if finding["line"]:
            where += f":{finding['line']}"
        lines.append(
            f"  {finding['level']:<7} {finding['code']}  {where}  "
            f"{finding['message']}"
        )
    if report.budget:
        budget = report.budget
        lines.append(
            "  budget  listing ~{listing_tokens} tok (always loaded) | "
            "body ~{body_tokens} tok, {body_lines} lines (on activation) | "
            "resources ~{resource_tokens} tok in {files} files "
            "(on demand)".format(**budget)
        )
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Lint Agent Skills against the agentskills.io specification."
    )
    parser.add_argument("paths", nargs="+", help="skill directory, or a directory of skills")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    parser.add_argument("--json", action="store_true", help="print machine-readable output")
    args = parser.parse_args(argv)

    skill_dirs = []
    for raw in args.paths:
        path = Path(raw)
        if not path.exists():
            print(f"error: {raw} does not exist", file=sys.stderr)
            return 2
        found = meta.find_skills(path)
        if not found and path.is_dir():
            found = [path]  # report the missing SKILL.md rather than nothing
        skill_dirs.extend(found)

    reports = [lint_skill(skill_dir) for skill_dir in skill_dirs]
    errors = sum(r.count(ERROR) for r in reports)
    warnings = sum(r.count(WARNING) for r in reports)

    if args.json:
        print(
            json.dumps(
                {
                    "skills": [
                        {
                            "path": str(r.skill_dir),
                            "findings": r.findings,
                            "budget": r.budget,
                        }
                        for r in reports
                    ],
                    "errors": errors,
                    "warnings": warnings,
                },
                indent=2,
            )
        )
    else:
        print("\n\n".join(format_report(r) for r in reports))
        print(
            f"\n{len(reports)} skill(s): {errors} error(s), "
            f"{warnings} warning(s)"
        )
    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
