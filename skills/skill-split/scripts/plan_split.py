#!/usr/bin/env python3
"""Analyse a large Agent Skill and propose how to split it into references and scripts.

    python3 plan_split.py SKILL_DIR [--target-lines 300] [--target-tokens 3000] [--json]

Measures the line and token weight of each section in SKILL.md, identifies
sections dominated by executable scripts or reference material, and estimates
the entry-point size after extracting them. Standard library only.
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

EXEC_LANGS = {
    "py": ".py", "python": ".py", "python3": ".py",
    "sh": ".sh", "bash": ".sh", "zsh": ".zsh", "shell": ".sh",
    "js": ".js", "javascript": ".js", "node": ".js",
    "ts": ".ts", "typescript": ".ts",
    "rb": ".rb", "ruby": ".rb", "pl": ".pl", "perl": ".pl",
}
REFERENCE_TITLE_RE = re.compile(
    r"\b(references?|rules?|patterns?|examples?|templates?|schemas?|tables?|"
    r"catalog(?:ue)?|troubleshooting|errors?|appendix|details?|matrix|"
    r"glossary|api|formats?|specifications?|options|flags)\b",
    re.IGNORECASE,
)
CORE_TITLE_RE = re.compile(
    r"\b(when to use|overview|quick start|before starting|preconditions?|"
    r"steps?|procedure|workflow|verify|verification|hand over|limits?)\b",
    re.IGNORECASE,
)


def _analyse_blocks(text: str) -> tuple[int, int, str, int]:
    """Return (code_blocks, code_lines, dominant_ext, table_lines)."""
    fence = None
    lang = ""
    code_blocks = 0
    code_lines = 0
    table_lines = 0
    lang_counts: dict = {}
    for line in text.split("\n"):
        stripped = line.strip()
        marker = re.match(r"(`{3,}|~{3,})\s*([\w+-]*)", stripped)
        if fence is None and marker:
            fence = marker.group(1)[0] * 3
            lang = marker.group(2).lower()
            code_blocks += 1
        elif fence is not None:
            if stripped.startswith(fence) and not stripped.strip(fence[0]).strip():
                fence = None
                lang = ""
            else:
                code_lines += 1
                if lang in EXEC_LANGS:
                    ext = EXEC_LANGS[lang]
                    lang_counts[ext] = lang_counts.get(ext, 0) + 1
        else:
            if stripped.startswith("|") and stripped.endswith("|"):
                table_lines += 1
    dominant_ext = max(lang_counts, key=lang_counts.get) if lang_counts else ""
    return code_blocks, code_lines, dominant_ext, table_lines


def _split_sections(body: str, body_line: int) -> list:
    lines = body.split("\n")
    headings = meta.extract_headings(body, body_line)
    # Prefer splitting at H2 (##); fall back to all headings if no H2 exists.
    split_points = [h for h in headings if h["level"] == 2] or headings
    if not split_points:
        return [
            {
                "title": "(body)",
                "slug": "body",
                "level": 1,
                "start_line": body_line,
                "end_line": body_line + len(lines) - 1,
                "text": body,
            }
        ]
    sections = []
    first_idx = split_points[0]["line"] - body_line
    if first_idx > 0:
        intro = "\n".join(lines[:first_idx])
        if intro.strip():
            sections.append(
                {
                    "title": "(introduction)",
                    "slug": "introduction",
                    "level": 1,
                    "start_line": body_line,
                    "end_line": split_points[0]["line"] - 1,
                    "text": intro,
                }
            )
    for idx, heading in enumerate(split_points):
        start_idx = heading["line"] - body_line
        if idx + 1 < len(split_points):
            end_idx = split_points[idx + 1]["line"] - body_line
        else:
            end_idx = len(lines)
        chunk = "\n".join(lines[start_idx:end_idx]).rstrip("\n")
        sections.append(
            {
                "title": heading["title"],
                "slug": heading["slug"],
                "level": heading["level"],
                "start_line": heading["line"],
                "end_line": body_line + end_idx - 1,
                "text": chunk,
            }
        )
    return sections


def _classify_section(sec: dict) -> dict:
    text = sec["text"]
    line_count = len(text.split("\n"))
    tokens = meta.estimate_tokens(text)
    code_blocks, code_lines, dominant_ext, table_lines = _analyse_blocks(text)
    slug = re.sub(r"^\d+-", "", sec["slug"]) or "section"
    title = sec["title"]

    action = "keep-inline"
    target = None
    reason = "core workflow or already concise"

    if dominant_ext and code_lines >= 15 and code_lines / max(line_count, 1) >= 0.35:
        action = "extract-script"
        stem = slug.replace("-", "_") if dominant_ext == ".py" else slug
        target = f"scripts/{stem}{dominant_ext}"
        reason = f"{code_lines} lines of executable code ({dominant_ext}); run as a script instead of inline code"
    elif sec["slug"] != "introduction" and (
        (REFERENCE_TITLE_RE.search(title) and (line_count >= 15 or tokens >= 120))
        or (table_lines >= 8 and line_count >= 12)
        or (not CORE_TITLE_RE.search(title) and (line_count >= 45 or tokens >= 400))
        or line_count >= 80
    ):
        action = "extract-reference"
        target = f"references/{slug}.md"
        if table_lines >= 8:
            reason = f"{table_lines} table rows ({line_count} lines); move lookup table to a reference file"
        elif REFERENCE_TITLE_RE.search(title):
            reason = f"reference material ({line_count} lines, ~{tokens} tok); load on demand"
        else:
            reason = f"large section ({line_count} lines, ~{tokens} tok); summarize inline and link to detail"

    return {
        "title": title,
        "slug": sec["slug"],
        "start_line": sec["start_line"],
        "end_line": sec["end_line"],
        "lines": line_count,
        "tokens": tokens,
        "code_blocks": code_blocks,
        "code_lines": code_lines,
        "table_lines": table_lines,
        "action": action,
        "target": target,
        "reason": reason,
    }


def plan_split(
    skill_dir: Path, target_lines: int = 300, target_tokens: int = 3000
) -> dict:
    skill = meta.load_skill(skill_dir)
    body_lines = len(skill.body.split("\n")) if skill.body else 0
    body_tokens = meta.estimate_tokens(skill.body)

    raw_sections = _split_sections(skill.body, skill.body_line)
    analysed = [_classify_section(sec) for sec in raw_sections]

    saved_lines = 0
    saved_tokens = 0
    extractions = []
    for item in analysed:
        if item["action"] != "keep-inline":
            # Replacing a section with a short link line takes ~2 lines / ~20 tokens
            saved_lines += max(0, item["lines"] - 3)
            saved_tokens += max(0, item["tokens"] - 25)
            extractions.append(
                {
                    "title": item["title"],
                    "lines": f"{item['start_line']}-{item['end_line']}",
                    "action": item["action"],
                    "target": item["target"],
                    "estimated_savings_lines": max(0, item["lines"] - 3),
                    "estimated_savings_tokens": max(0, item["tokens"] - 25),
                    "reason": item["reason"],
                }
            )

    projected_lines = max(1, body_lines - saved_lines)
    projected_tokens = max(1, body_tokens - saved_tokens)

    return {
        "skill": skill.name or skill_dir.name,
        "path": str(skill_dir),
        "current": {
            "body_lines": body_lines,
            "body_tokens": body_tokens,
            "over_spec_lines": body_lines > meta.BODY_MAX_LINES,
            "over_spec_tokens": body_tokens > meta.BODY_MAX_TOKENS,
        },
        "target": {
            "body_lines": target_lines,
            "body_tokens": target_tokens,
        },
        "projected": {
            "body_lines": projected_lines,
            "body_tokens": projected_tokens,
            "meets_target": (
                projected_lines <= target_lines and projected_tokens <= target_tokens
            ),
        },
        "sections": analysed,
        "extractions": extractions,
    }


def format_plan(plan: dict) -> str:
    cur = plan["current"]
    proj = plan["projected"]
    tgt = plan["target"]
    lines = [
        f"{plan['skill']}  ({plan['path']})",
        f"  current body:   {cur['body_lines']} lines, ~{cur['body_tokens']} tok "
        f"(ceiling: {meta.BODY_MAX_LINES} lines, ~{meta.BODY_MAX_TOKENS} tok)",
        f"  projected body: {proj['body_lines']} lines, ~{proj['body_tokens']} tok "
        f"(target: <={tgt['body_lines']} lines, <={tgt['body_tokens']} tok)",
        "",
        "  sections:",
    ]
    for sec in plan["sections"]:
        span = f"L{sec['start_line']}-{sec['end_line']}"
        arrow = f" -> {sec['target']}" if sec["target"] else ""
        lines.append(
            f"    {sec['action']:<17} {span:<11} {sec['lines']:>4} lines  "
            f"~{sec['tokens']:>4} tok  {sec['title']}{arrow}"
        )
        if sec["action"] != "keep-inline":
            lines.append(f"      reason: {sec['reason']}")
    if not plan["extractions"]:
        lines.append("\n  no extractions needed; skill is already compact.")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyse an Agent Skill and propose how to split it into references and scripts."
    )
    parser.add_argument("skill_dir", help="path to the skill directory")
    parser.add_argument("--target-lines", type=int, default=300, help="target line count for SKILL.md (default: 300)")
    parser.add_argument("--target-tokens", type=int, default=3000, help="target token count for SKILL.md (default: 3000)")
    parser.add_argument("--json", action="store_true", help="print machine-readable output")
    args = parser.parse_args(argv)

    skill_dir = Path(args.skill_dir)
    if not (skill_dir / meta.SKILL_FILE).is_file():
        print(f"error: no {meta.SKILL_FILE} in {args.skill_dir}", file=sys.stderr)
        return 2

    plan = plan_split(skill_dir, args.target_lines, args.target_tokens)
    if args.json:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    else:
        print(format_plan(plan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
