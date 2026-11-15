#!/usr/bin/env python3
"""Find installed Agent Skills that are never used in session transcripts.

    python3 usage_report.py [--project DIR] [--root PATH ...] [--logs PATH ...]
                            [--days 30] [--no-user] [--json]

Cross-references installed skills with local session transcripts from
Claude Code, Codex, Gemini CLI and Antigravity, counting sessions where each
skill was actually activated and estimating the context tokens spent on
dormant skills. Read-only. Standard library only.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True  # keep the skill directory free of __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _skillmeta as meta  # noqa: E402

USER_SKILL_ROOTS = (
    ("Claude Code (personal)", ".claude/skills"),
    ("Claude Code (plugins)", ".claude/plugins"),
    ("Shared ~/.agents (Codex, Gemini CLI)", ".agents/skills"),
    ("Gemini CLI (user)", ".gemini/skills"),
    ("Antigravity (global)", ".gemini/config/skills"),
    ("Antigravity (plugins)", ".gemini/config/plugins"),
    ("Cursor (user)", ".cursor/skills"),
    ("Windsurf (user)", ".codeium/windsurf/skills"),
    ("OpenCode (user)", ".config/opencode/skills"),
    ("GitHub Copilot (user)", ".copilot/skills"),
)
PROJECT_SKILL_ROOTS = (
    ("Claude Code (project)", ".claude/skills"),
    ("Shared .agents (Codex, Gemini CLI, Antigravity)", ".agents/skills"),
    ("Antigravity (.agent)", ".agent/skills"),
    ("Gemini CLI (workspace)", ".gemini/skills"),
    ("Cursor (project)", ".cursor/skills"),
    ("Windsurf (project)", ".windsurf/skills"),
    ("OpenCode (project)", ".opencode/skills"),
    ("GitHub Copilot (project)", ".github/skills"),
)
USER_LOG_ROOTS = (
    ("Claude Code", ".claude/projects"),
    ("Codex", ".codex/sessions"),
    ("Gemini CLI", ".gemini/tmp"),
    ("Antigravity", ".gemini/antigravity/brain"),
)
MAX_LOG_BYTES = 20_000_000


def collect_skills(roots: list) -> list:
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
            name = skill.name or skill_dir.name
            listing = f"{name}: {skill.description}"
            records.append(
                {
                    "name": name,
                    "location": label,
                    "path": str(skill_dir),
                    "listing_tokens": meta.estimate_tokens(listing),
                }
            )
    return records


def iter_log_files(log_roots: list, cutoff_ts: float | None) -> list:
    found, seen = [], set()
    for _, root in log_roots:
        root = Path(root)
        if not root.exists():
            continue
        if root.is_file():
            if cutoff_ts is None or root.stat().st_mtime >= cutoff_ts:
                found.append(root)
            continue
        base_depth = len(root.parts)
        for current, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in meta.SKIP_DIRS)
            if len(Path(current).parts) - base_depth > 6:
                dirs[:] = []
                continue
            for fname in sorted(files):
                if not fname.endswith((".jsonl", ".json")):
                    continue
                if fname == "transcript_full.jsonl":
                    continue
                full = Path(current) / fname
                real = os.path.realpath(full)
                if real in seen:
                    continue
                seen.add(real)
                try:
                    stat = full.stat()
                except OSError:
                    continue
                if stat.st_size > MAX_LOG_BYTES:
                    continue
                if cutoff_ts is not None and stat.st_mtime < cutoff_ts:
                    continue
                found.append(full)
    return found


def build_activation_matcher(names: list):
    """Compile a regex that matches real activations and ignores system-prompt listings."""
    if not names:
        return None
    alt = "|".join(re.escape(n) for n in sorted(set(names), key=len, reverse=True))
    pattern = (
        # 1. Tool argument reading <name>/SKILL.md
        rf'"(?:file_?path|path|TargetFile|Path)"\s*:\s*"[^"\n]*[/\\](?P<read>{alt})[/\\]SKILL\.md"'
        # 2. Running or reading a bundled resource inside <name>/(scripts|references|assets)/
        rf'|(?:^|[\s"\'=/\\])(?P<res>{alt})[/\\](?:scripts|references|assets|resources)[/\\][\w.-]+'
        # 3. Direct Skill / activate_skill tool invocation
        rf'|"(?:skill|skill_name)"\s*:\s*"(?:[\w-]+:)?(?P<tool>{alt})"'
        # 4. Explicit slash command (not preceded by a path segment)
        rf'|(?<![\w./:\\-])/(?:[\w-]+:)?(?P<slash>{alt})(?=$|[\s"\',.!?;:)])'
    )
    return re.compile(pattern)


def scan_logs(skills: list, log_files: list) -> dict:
    names = [s["name"] for s in skills]
    matcher = build_activation_matcher(names)
    usage = {n: {"sessions": 0, "last_used_ts": None} for n in names}
    if matcher is None:
        return usage

    for log_path in log_files:
        text = meta.read_text(log_path)
        if not text:
            continue
        try:
            mtime = log_path.stat().st_mtime
        except OSError:
            mtime = None
        hit_in_session = set()
        for match in matcher.finditer(text):
            name = (
                match.group("read")
                or match.group("res")
                or match.group("tool")
                or match.group("slash")
            )
            if name in usage:
                hit_in_session.add(name)
        for name in hit_in_session:
            usage[name]["sessions"] += 1
            if mtime is not None:
                prev = usage[name]["last_used_ts"]
                if prev is None or mtime > prev:
                    usage[name]["last_used_ts"] = mtime
    return usage


def generate_report(
    skills: list, log_files: list, days: int
) -> dict:
    usage = scan_logs(skills, log_files)
    active, dormant = [], []
    for item in skills:
        info = usage.get(item["name"], {"sessions": 0, "last_used_ts": None})
        ts = info["last_used_ts"]
        last_used = (
            datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%Y-%m-%d")
            if ts is not None
            else None
        )
        entry = {
            **item,
            "sessions": info["sessions"],
            "last_used": last_used,
        }
        if info["sessions"] > 0:
            active.append(entry)
        else:
            dormant.append(entry)

    active.sort(key=lambda r: (-r["sessions"], r["name"]))
    dormant.sort(key=lambda r: (-r["listing_tokens"], r["name"]))

    return {
        "days": days,
        "sessions_scanned": len(log_files),
        "total_skills": len(skills),
        "total_listing_tokens": sum(s["listing_tokens"] for s in skills),
        "dormant_listing_tokens": sum(s["listing_tokens"] for s in dormant),
        "active": active,
        "dormant": dormant,
    }


def format_report(report: dict) -> str:
    window = f"last {report['days']} day(s)" if report["days"] > 0 else "all time"
    lines = [
        f"Sessions scanned: {report['sessions_scanned']} ({window})",
        f"Installed skills: {report['total_skills']} "
        f"(~{report['total_listing_tokens']} listing tok/session)",
    ]
    if report["sessions_scanned"] == 0:
        lines.append(
            "\nNo session transcripts found in the scanned locations. "
            "Pass --logs <dir> if your harness stores transcripts elsewhere."
        )
    if report["active"]:
        lines.append("\nActive skills:")
        for item in report["active"]:
            lines.append(
                f"  {item['name']:<28} {item['sessions']:>4} session(s)  "
                f"last {item['last_used']}  ~{item['listing_tokens']:>4} tok  "
                f"({item['location']})"
            )
    if report["dormant"]:
        lines.append(
            f"\nDormant skills (0 activations; ~{report['dormant_listing_tokens']} "
            "tok/session always loaded):"
        )
        for item in report["dormant"]:
            lines.append(
                f"  {item['name']:<28} ~{item['listing_tokens']:>4} tok  "
                f"{item['path']}  ({item['location']})"
            )
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Find installed Agent Skills that are never used in session transcripts."
    )
    parser.add_argument("--project", default=".", help="project directory (default: current directory)")
    parser.add_argument("--root", action="append", default=[], help="extra skill directory to scan; repeatable")
    parser.add_argument("--logs", action="append", default=[], help="extra session transcript directory or file; repeatable")
    parser.add_argument("--days", type=int, default=30, help="only scan transcripts modified within N days (0 = all time)")
    parser.add_argument("--no-user", action="store_true", help="skip user-level skill and transcript locations")
    parser.add_argument("--json", action="store_true", help="print machine-readable output")
    args = parser.parse_args(argv)

    project = Path(args.project).resolve()
    home = Path.home()

    skill_roots = [(label, project / rel) for label, rel in PROJECT_SKILL_ROOTS]
    log_roots = []
    if not args.no_user:
        skill_roots += [(label, home / rel) for label, rel in USER_SKILL_ROOTS]
        log_roots += [(label, home / rel) for label, rel in USER_LOG_ROOTS]
    skill_roots += [(f"custom ({raw})", Path(raw).resolve()) for raw in args.root]
    log_roots += [(f"custom ({raw})", Path(raw).resolve()) for raw in args.logs]

    cutoff = (
        time.time() - (args.days * 86400) if args.days and args.days > 0 else None
    )
    skills = collect_skills(skill_roots)
    log_files = iter_log_files(log_roots, cutoff)
    report = generate_report(skills, log_files, args.days)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
