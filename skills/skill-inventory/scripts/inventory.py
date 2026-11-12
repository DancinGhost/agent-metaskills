#!/usr/bin/env python3
"""Inventory the Agent Skills installed on this machine and in a project.

    python3 inventory.py [--project DIR] [--root PATH ...] [--no-user]
                         [--threshold 0.4] [--json]

Lists every skill found in the known harness locations, then reports
names defined in more than one place, skills that break the specification,
descriptions similar enough to compete for the same request, and the
context cost of the always-loaded listing. Read-only. Standard library
only.
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

# (label, path relative to the home directory)
USER_ROOTS = (
    ("Claude Code (personal)", ".claude/skills"),
    ("Claude Code (plugins)", ".claude/plugins"),
    ("Shared ~/.agents (Codex, Gemini CLI)", ".agents/skills"),
    ("Gemini CLI (user)", ".gemini/skills"),
    ("Antigravity (global)", ".gemini/config/skills"),
    ("Antigravity (built-in)", ".gemini/antigravity/builtin/skills"),
)
# (label, path relative to the project directory)
PROJECT_ROOTS = (
    ("Claude Code (project)", ".claude/skills"),
    ("Shared .agents (Codex, Gemini CLI, Antigravity)", ".agents/skills"),
    ("Gemini CLI (workspace)", ".gemini/skills"),
)
SYSTEM_ROOTS = (("Codex (admin)", "/etc/codex/skills"),)

STOPWORDS = set(
    """a an and any are as at be been before by can do does for from has have
    how if in into is it its may more must new not of on or other should so
    such than that the their them then these this those to up use used user
    users using when whenever where which while will with without you your
    skill skills agent agents task tasks ask asks asked want wants need needs
    mention mentions about also all each every etc e g i""".split()
)


def keywords(text: str) -> set:
    words = re.findall(r"[a-z][a-z0-9+#.-]*[a-z0-9+#]|[a-z]", text.lower())
    out = set()
    for word in words:
        word = word.strip(".-")
        if len(word) < 3 or word in STOPWORDS:
            continue
        if word.endswith("ies") and len(word) > 5:
            word = word[:-3] + "y"
        elif word.endswith(("ing", "ed")) and len(word) > 5:
            word = word[:-3] if word.endswith("ing") else word[:-2]
        elif word.endswith("s") and not word.endswith("ss") and len(word) > 3:
            word = word[:-1]
        out.add(word)
    return out


def similarity(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def collect(roots: list) -> list:
    """Return one record per skill directory found under the given roots."""
    records, seen = [], set()
    for label, root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        for skill_dir in meta.find_skills(root, include_hidden=False):
            real = skill_dir.resolve()
            if real in seen:
                continue
            seen.add(real)
            skill = meta.load_skill(skill_dir)
            problems = []
            if not skill.has_frontmatter:
                problems.append("no frontmatter")
            else:
                if not skill.name:
                    problems.append("no name")
                elif not meta.NAME_RE.match(skill.name):
                    problems.append("invalid name")
                if not skill.description.strip():
                    problems.append("no description")
                elif len(skill.description) > meta.DESCRIPTION_MAX:
                    problems.append(
                        f"description over {meta.DESCRIPTION_MAX} characters"
                    )
                if skill.problems:
                    problems.append("frontmatter YAML problems")
                if skill.name and skill.name != skill_dir.name:
                    problems.append(
                        f"name differs from directory '{skill_dir.name}'"
                    )
            name = skill.name or skill_dir.name
            listing = f"{name}: {skill.description}"
            records.append(
                {
                    "name": name,
                    "location": label,
                    "root": str(root),
                    "path": str(skill_dir),
                    "symlink": skill_dir.is_symlink(),
                    "description": skill.description,
                    "description_chars": len(skill.description),
                    "listing_tokens": meta.estimate_tokens(listing),
                    "body_tokens": meta.estimate_tokens(skill.body),
                    "body_lines": len(skill.body.split("\n")),
                    "problems": problems,
                }
            )
    return records


def analyse(records: list, threshold: float) -> dict:
    by_name: dict = {}
    for record in records:
        by_name.setdefault(record["name"], []).append(record)
    duplicates = [
        {"name": name, "paths": [r["path"] for r in group]}
        for name, group in sorted(by_name.items())
        if len(group) > 1
    ]

    words = [keywords(r["name"].replace("-", " ") + " " + r["description"]) for r in records]
    overlaps = []
    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            if records[i]["name"] == records[j]["name"]:
                continue
            score = similarity(words[i], words[j])
            if score >= threshold:
                overlaps.append(
                    {
                        "a": records[i]["name"],
                        "b": records[j]["name"],
                        "score": round(score, 2),
                        "shared": sorted(words[i] & words[j]),
                    }
                )
    overlaps.sort(key=lambda o: -o["score"])

    by_location: dict = {}
    for record in records:
        entry = by_location.setdefault(
            record["location"], {"skills": 0, "listing_tokens": 0}
        )
        entry["skills"] += 1
        entry["listing_tokens"] += record["listing_tokens"]

    return {
        "duplicates": duplicates,
        "overlaps": overlaps,
        "broken": [r for r in records if r["problems"]],
        "by_location": by_location,
        "total_listing_tokens": sum(r["listing_tokens"] for r in records),
    }


def shorten(text: str, width: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


def format_text(records: list, analysis: dict, searched: list) -> str:
    out = []
    if not records:
        out.append("No skills found.")
    current = None
    for record in sorted(records, key=lambda r: (r["location"], r["name"])):
        if record["location"] != current:
            current = record["location"]
            out.append(f"\n{current}  [{record['root']}]")
        flag = " !" if record["problems"] else ""
        out.append(
            f"  {record['name']:<28} ~{record['listing_tokens']:>4} tok  "
            f"{shorten(record['description'], 70)}{flag}"
        )

    out.append("\nAlways-loaded listing cost (name + description, estimated):")
    for location, entry in sorted(analysis["by_location"].items()):
        out.append(
            f"  {location:<48} {entry['skills']:>3} skills  "
            f"~{entry['listing_tokens']} tok"
        )
    out.append(f"  {'total':<48} {len(records):>3} skills  ~{analysis['total_listing_tokens']} tok")

    if analysis["duplicates"]:
        out.append("\nSame name in more than one place (one copy shadows the others):")
        for item in analysis["duplicates"]:
            out.append(f"  {item['name']}")
            out.extend(f"    {path}" for path in item["paths"])
    if analysis["broken"]:
        out.append("\nSkills that break the specification (some harnesses will not load them):")
        for record in analysis["broken"]:
            out.append(f"  {record['path']}: {'; '.join(record['problems'])}")
    if analysis["overlaps"]:
        out.append("\nDescriptions that may compete for the same request:")
        for item in analysis["overlaps"]:
            out.append(
                f"  {item['a']} <-> {item['b']}  similarity {item['score']}  "
                f"(shared: {', '.join(item['shared'][:8])})"
            )
    out.append("\nSearched:")
    for label, root in searched:
        state = "found" if Path(root).is_dir() else "absent"
        out.append(f"  {state:<6} {root}  ({label})")
    return "\n".join(out).lstrip("\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Inventory installed Agent Skills across harnesses."
    )
    parser.add_argument("--project", default=".", help="project directory (default: current directory)")
    parser.add_argument("--root", action="append", default=[], help="extra directory to scan; repeatable")
    parser.add_argument("--no-user", action="store_true", help="skip user-level and system locations")
    parser.add_argument("--threshold", type=float, default=0.4, help="description similarity that counts as overlap (0-1)")
    parser.add_argument("--json", action="store_true", help="print machine-readable output")
    args = parser.parse_args(argv)

    project = Path(args.project).resolve()
    home = Path.home()
    roots = [(label, project / rel) for label, rel in PROJECT_ROOTS]
    if not args.no_user:
        roots += [(label, home / rel) for label, rel in USER_ROOTS]
        roots += [(label, Path(path)) for label, path in SYSTEM_ROOTS]
    roots += [(f"custom ({raw})", Path(raw).resolve()) for raw in args.root]

    # A project inside the home directory can reach the same folder twice.
    unique, seen = [], set()
    for label, root in roots:
        key = str(root.resolve()) if root.exists() else str(root)
        if key not in seen:
            seen.add(key)
            unique.append((label, root))

    records = collect(unique)
    analysis = analyse(records, args.threshold)
    if args.json:
        print(json.dumps({"skills": records, **analysis}, indent=2, ensure_ascii=False))
    else:
        print(format_text(records, analysis, [(l, str(r)) for l, r in unique]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
