#!/usr/bin/env python3
"""Compare two versions of an Agent Skill in terms of behaviour and budget.

    python3 diff_skill.py OLD_SKILL NEW_SKILL [--json]
    python3 diff_skill.py SKILL_DIR --git-ref REF [--json]

Reports changes in frontmatter, trigger keywords, context budget, headings,
bundled files, external hosts and specification compliance. Exit status is 1
when the new version introduces specification errors, 2 on usage errors, and
0 otherwise. Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # keep the skill directory free of __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _skillmeta as meta  # noqa: E402

URL_RE = re.compile(r"\b(?:https?|ftp|wss?)://([A-Za-z0-9.-]+)(?::\d+)?", re.I)


def _file_hash(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if b"\x00" not in data[:8192]:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()[:16]


def _budget(skill: meta.Skill) -> dict:
    files = meta.iter_files(skill.path)
    resources = 0
    for rel in files:
        if rel.name == meta.SKILL_FILE:
            continue
        text = meta.read_text(skill.path / rel)
        if text is not None:
            resources += meta.estimate_tokens(text)
    listing = f"{skill.name}: {skill.description}"
    return {
        "listing_tokens": meta.estimate_tokens(listing),
        "body_tokens": meta.estimate_tokens(skill.body),
        "body_lines": len(skill.body.split("\n")) if skill.body else 0,
        "resource_tokens": resources,
        "files": len(files),
    }


def _hosts(skill_dir: Path) -> set:
    found = set()
    for rel in meta.iter_files(skill_dir):
        text = meta.read_text(skill_dir / rel)
        if text is None:
            continue
        for match in URL_RE.finditer(text):
            found.add(match.group(1).lower().rstrip("."))
    return found


def diff_skills(old_dir: Path, new_dir: Path) -> dict:
    old = meta.load_skill(old_dir)
    new = meta.load_skill(new_dir)

    old_fm, new_fm = old.frontmatter, new.frontmatter
    fm_added = sorted(k for k in new_fm if k not in old_fm)
    fm_removed = sorted(k for k in old_fm if k not in new_fm)
    fm_changed = {
        k: {"old": old_fm[k], "new": new_fm[k]}
        for k in sorted(set(old_fm) & set(new_fm))
        if old_fm[k] != new_fm[k]
    }

    old_kw = meta.keywords(old.name.replace("-", " ") + " " + old.description)
    new_kw = meta.keywords(new.name.replace("-", " ") + " " + new.description)

    old_budget = _budget(old)
    new_budget = _budget(new)
    budget_delta = {
        key: {
            "old": old_budget[key],
            "new": new_budget[key],
            "delta": new_budget[key] - old_budget[key],
        }
        for key in ("listing_tokens", "body_tokens", "body_lines", "resource_tokens", "files")
    }

    old_headings = [h["title"] for h in meta.extract_headings(old.body, old.body_line)]
    new_headings = [h["title"] for h in meta.extract_headings(new.body, new.body_line)]
    old_h_set, new_h_set = set(old_headings), set(new_headings)

    old_files = {rel.as_posix(): _file_hash(old_dir / rel) for rel in meta.iter_files(old_dir)}
    new_files = {rel.as_posix(): _file_hash(new_dir / rel) for rel in meta.iter_files(new_dir)}
    files_added = sorted(f for f in new_files if f not in old_files)
    files_removed = sorted(f for f in old_files if f not in new_files)
    files_modified = sorted(
        f for f in (set(old_files) & set(new_files)) if old_files[f] != new_files[f]
    )

    old_hosts = _hosts(old_dir)
    new_hosts = _hosts(new_dir)

    new_problems = []
    if not new.skill_md.is_file():
        new_problems.append("new version is missing SKILL.md")
    elif not new.has_frontmatter:
        new_problems.append("new version is missing YAML frontmatter")
    else:
        for line, msg in new.problems:
            if (line, msg) not in old.problems:
                new_problems.append(f"frontmatter line {line}: {msg}")
        if not new.name:
            new_problems.append("new version is missing 'name'")
        if not new.description.strip():
            new_problems.append("new version is missing 'description'")
        elif len(new.description) > meta.DESCRIPTION_MAX:
            new_problems.append(
                f"description is {len(new.description)} chars (limit {meta.DESCRIPTION_MAX})"
            )

    return {
        "skill": new.name or old.name or new_dir.name,
        "old_path": str(old_dir),
        "new_path": str(new_dir),
        "identical": (
            not files_added and not files_removed and not files_modified
        ),
        "frontmatter": {
            "added": fm_added,
            "removed": fm_removed,
            "changed": fm_changed,
        },
        "trigger": {
            "description_changed": old.description != new.description,
            "old_description": old.description,
            "new_description": new.description,
            "keywords_added": sorted(new_kw - old_kw),
            "keywords_removed": sorted(old_kw - new_kw),
        },
        "budget": budget_delta,
        "headings": {
            "added": [h for h in new_headings if h not in old_h_set],
            "removed": [h for h in old_headings if h not in new_h_set],
        },
        "files": {
            "added": files_added,
            "removed": files_removed,
            "modified": files_modified,
        },
        "hosts": {
            "added": sorted(new_hosts - old_hosts),
            "removed": sorted(old_hosts - new_hosts),
        },
        "new_problems": new_problems,
    }


def _signed(value: int) -> str:
    return f"+{value}" if value > 0 else str(value)


def format_diff(diff: dict) -> str:
    lines = [f"{diff['skill']}  ({diff['old_path']} -> {diff['new_path']})"]
    if diff["identical"]:
        lines.append("  no changes")
        return "\n".join(lines)

    trig = diff["trigger"]
    if trig["description_changed"]:
        lines.append("  trigger description changed:")
        if trig["keywords_added"]:
            lines.append(f"    + trigger words: {', '.join(trig['keywords_added'])}")
        if trig["keywords_removed"]:
            lines.append(f"    - trigger words: {', '.join(trig['keywords_removed'])}")
        if not trig["keywords_added"] and not trig["keywords_removed"]:
            lines.append("    (wording changed; keyword set is unchanged)")

    fm = diff["frontmatter"]
    for key in fm["added"]:
        lines.append(f"  frontmatter + {key}")
    for key in fm["removed"]:
        lines.append(f"  frontmatter - {key}")
    for key in fm["changed"]:
        if key != "description":
            lines.append(f"  frontmatter ~ {key}: {fm['changed'][key]['old']!r} -> {fm['changed'][key]['new']!r}")

    b = diff["budget"]
    lines.append(
        "  budget  "
        f"listing {b['listing_tokens']['old']}->{b['listing_tokens']['new']} tok ({_signed(b['listing_tokens']['delta'])}) | "
        f"body {b['body_tokens']['old']}->{b['body_tokens']['new']} tok ({_signed(b['body_tokens']['delta'])}), "
        f"{b['body_lines']['old']}->{b['body_lines']['new']} lines ({_signed(b['body_lines']['delta'])}) | "
        f"resources {b['resource_tokens']['old']}->{b['resource_tokens']['new']} tok ({_signed(b['resource_tokens']['delta'])})"
    )

    h = diff["headings"]
    for title in h["added"]:
        lines.append(f"  section + {title}")
    for title in h["removed"]:
        lines.append(f"  section - {title}")

    f = diff["files"]
    for path in f["added"]:
        lines.append(f"  file    + {path}")
    for path in f["removed"]:
        lines.append(f"  file    - {path}")
    for path in f["modified"]:
        lines.append(f"  file    ~ {path}")

    for host in diff["hosts"]["added"]:
        lines.append(f"  host    + {host} (new external host)")
    for host in diff["hosts"]["removed"]:
        lines.append(f"  host    - {host}")

    for problem in diff["new_problems"]:
        lines.append(f"  error   {problem}")

    return "\n".join(lines)


def _export_git_ref(skill_dir: Path, ref: str, dest: Path) -> bool:
    skill_dir = skill_dir.resolve()
    top = subprocess.run(
        ["git", "-C", str(skill_dir), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    if top.returncode != 0:
        return False
    repo_root = Path(top.stdout.strip()).resolve()
    rel_skill = skill_dir.relative_to(repo_root).as_posix()
    listed = subprocess.run(
        ["git", "-C", str(repo_root), "ls-tree", "-r", "--name-only", ref, rel_skill],
        capture_output=True, text=True,
    )
    if listed.returncode != 0 or not listed.stdout.strip():
        return False
    for line in listed.stdout.splitlines():
        rel_inside = Path(line).relative_to(rel_skill)
        shown = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"{ref}:{line}"],
            capture_output=True,
        )
        if shown.returncode == 0:
            target = dest / rel_inside
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(shown.stdout)
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare two versions of an Agent Skill."
    )
    parser.add_argument("old_path", help="old skill directory (or current skill directory with --git-ref)")
    parser.add_argument("new_path", nargs="?", help="new skill directory")
    parser.add_argument("--git-ref", help="compare old_path on disk against its version at this git ref")
    parser.add_argument("--json", action="store_true", help="print machine-readable output")
    args = parser.parse_args(argv)

    first = Path(args.old_path)
    if not first.is_dir():
        print(f"error: {args.old_path} is not a directory", file=sys.stderr)
        return 2

    if args.git_ref:
        if args.new_path:
            print("error: pass either NEW_SKILL or --git-ref, not both", file=sys.stderr)
            return 2
        with tempfile.TemporaryDirectory() as tmp:
            old_copy = Path(tmp) / first.name
            old_copy.mkdir()
            if not _export_git_ref(first, args.git_ref, old_copy):
                print(
                    f"error: could not read {args.old_path} at git ref {args.git_ref!r}",
                    file=sys.stderr,
                )
                return 2
            result = diff_skills(old_copy, first)
            result["old_path"] = f"{args.old_path}@{args.git_ref}"
    else:
        if not args.new_path:
            print("error: provide NEW_SKILL or --git-ref REF", file=sys.stderr)
            return 2
        second = Path(args.new_path)
        if not second.is_dir():
            print(f"error: {args.new_path} is not a directory", file=sys.stderr)
            return 2
        result = diff_skills(first, second)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_diff(result))
    return 1 if result["new_problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
