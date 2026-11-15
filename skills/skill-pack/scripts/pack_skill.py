#!/usr/bin/env python3
"""Package Agent Skills into specification-clean directories, zip archives or plugins.

    python3 pack_skill.py PATH [PATH ...] --output DEST
                          [--format zip|spec-dir|plugin]
                          [--plugin-name NAME] [--keep-extensions] [--json]

Strips harness-only frontmatter extensions (merging 'when_to_use' into
'description' first), normalises YAML and line endings, omits junk files,
and writes either a reproducible zip archive, a clean directory or a plugin
bundle. Exit status is 1 when a skill fails validation, 2 on usage errors,
and 0 otherwise. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True  # keep the skill directory free of __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _skillmeta as meta  # noqa: E402

JUNK_NAMES = {".DS_Store", "Thumbs.db", ".gitignore"}
JUNK_SUFFIXES = {".pyc", ".pyo", ".swp", ".bak"}
ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)


def prepare_skill(skill_dir: Path, strip_extensions: bool = True) -> dict:
    """Validate and prepare one skill's files in memory before writing."""
    skill_dir = Path(skill_dir)
    skill = meta.load_skill(skill_dir)
    errors = []
    notes = []

    if not skill.skill_md.is_file():
        errors.append(f"no {meta.SKILL_FILE} in {skill_dir}")
        return {"name": skill_dir.name, "path": str(skill_dir), "errors": errors, "notes": notes, "files": {}}
    if not skill.has_frontmatter:
        errors.append(f"{meta.SKILL_FILE} has no YAML frontmatter")
        return {"name": skill_dir.name, "path": str(skill_dir), "errors": errors, "notes": notes, "files": {}}

    fm = dict(skill.frontmatter)
    name = fm.get("name")
    if not isinstance(name, str) or not meta.NAME_RE.match(name) or len(name) > meta.NAME_MAX:
        errors.append(f"invalid or missing skill name {name!r}")
        name = skill_dir.name

    description = str(fm.get("description", "")).strip()
    when_to_use = str(fm.get("when_to_use", "")).strip()
    if strip_extensions and when_to_use:
        if when_to_use.lower() not in description.lower():
            sep = " " if description.endswith(".") else ". "
            merged = f"{description}{sep}{when_to_use}".strip(". ") + "."
            if len(merged) <= meta.DESCRIPTION_MAX:
                description = merged
                fm["description"] = description
                notes.append("merged 'when_to_use' into 'description'")

    if not description:
        errors.append("missing non-empty 'description'")
    elif len(description) > meta.DESCRIPTION_MAX:
        errors.append(
            f"description is {len(description)} characters (limit {meta.DESCRIPTION_MAX})"
        )

    if isinstance(fm.get("allowed-tools"), list):
        fm["allowed-tools"] = " ".join(str(x) for x in fm["allowed-tools"])
        notes.append("converted 'allowed-tools' list to a space-separated string")

    stripped_fields = []
    if strip_extensions:
        for key in list(fm):
            if key not in meta.SPEC_FIELDS:
                stripped_fields.append(key)
                del fm[key]
        if stripped_fields:
            notes.append("stripped non-spec frontmatter: " + ", ".join(stripped_fields))

    rendered_skill_md = (
        "---\n" + meta.format_frontmatter(fm) + "\n---\n" + skill.body.replace("\r\n", "\n")
    ).encode("utf-8")

    files_map: dict[str, bytes] = {meta.SKILL_FILE: rendered_skill_md}
    root_real = os.path.realpath(skill_dir)

    for rel in meta.iter_files(skill_dir):
        if rel.name == meta.SKILL_FILE:
            continue
        if rel.name in JUNK_NAMES or rel.suffix.lower() in JUNK_SUFFIXES:
            continue
        full = skill_dir / rel
        target_real = os.path.realpath(full)
        if not (target_real == root_real or target_real.startswith(root_real + os.sep)):
            errors.append(f"symlink {rel.as_posix()!r} points outside the skill directory")
            continue
        text = meta.read_text(full)
        if text is not None:
            files_map[rel.as_posix()] = text.replace("\r\n", "\n").encode("utf-8")
        else:
            files_map[rel.as_posix()] = full.read_bytes()

    return {
        "name": name,
        "description": description,
        "path": str(skill_dir),
        "errors": errors,
        "notes": notes,
        "stripped_fields": stripped_fields,
        "files": files_map,
    }


def _write_zip(zip_path: Path, prepared_list: list) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in prepared_list:
            prefix = item["name"]
            for rel_posix, content in sorted(item["files"].items()):
                info = zipfile.ZipInfo(f"{prefix}/{rel_posix}", date_time=ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                is_exec = rel_posix.startswith("scripts/") and not rel_posix.endswith(".py")
                mode = 0o755 if is_exec else 0o644
                info.external_attr = (mode & 0xFFFF) << 16
                zf.writestr(info, content)


def _write_tree(base_dir: Path, files_map: dict) -> None:
    for rel_posix, content in sorted(files_map.items()):
        dest = base_dir / rel_posix
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)


def pack_skills(
    skill_dirs: list,
    output: Path,
    fmt: str = "zip",
    plugin_name: str | None = None,
    strip_extensions: bool = True,
) -> dict:
    prepared = [prepare_skill(d, strip_extensions=strip_extensions) for d in skill_dirs]
    all_errors = [
        f"{item['name']}: {err}" for item in prepared for err in item["errors"]
    ]
    if all_errors:
        return {
            "format": fmt,
            "outputs": [],
            "skills": [
                {
                    "name": p["name"],
                    "path": p["path"],
                    "files": len(p["files"]),
                    "notes": p["notes"],
                    "errors": p["errors"],
                }
                for p in prepared
            ],
            "errors": all_errors,
        }

    outputs = []
    if fmt == "zip":
        if str(output).lower().endswith(".zip"):
            _write_zip(output, prepared)
            outputs.append(str(output))
        else:
            output.mkdir(parents=True, exist_ok=True)
            for item in prepared:
                dest_zip = output / f"{item['name']}.zip"
                _write_zip(dest_zip, [item])
                outputs.append(str(dest_zip))
    elif fmt == "spec-dir":
        if len(prepared) == 1 and output.name == prepared[0]["name"]:
            _write_tree(output, prepared[0]["files"])
            outputs.append(str(output))
        else:
            for item in prepared:
                dest_dir = output / item["name"]
                _write_tree(dest_dir, item["files"])
                outputs.append(str(dest_dir))
    elif fmt == "plugin":
        name = plugin_name or (
            prepared[0]["name"] if len(prepared) == 1 else output.resolve().name
        )
        summary = (
            prepared[0]["description"]
            if len(prepared) == 1
            else "Bundled Agent Skills: " + ", ".join(p["name"] for p in prepared) + "."
        )
        for item in prepared:
            _write_tree(output / "skills" / item["name"], item["files"])
        manifest = {
            "name": name,
            "version": "1.0.0",
            "description": summary[:300],
            "license": "MIT",
        }
        claude_dir = output / ".claude-plugin"
        claude_dir.mkdir(parents=True, exist_ok=True)
        (claude_dir / "plugin.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        (output / "plugin.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        outputs.append(str(output))

    return {
        "format": fmt,
        "outputs": outputs,
        "skills": [
            {
                "name": p["name"],
                "path": p["path"],
                "files": len(p["files"]),
                "bytes": sum(len(b) for b in p["files"].values()),
                "notes": p["notes"],
                "errors": p["errors"],
            }
            for p in prepared
        ],
        "errors": [],
    }


def format_result(result: dict) -> str:
    lines = [f"format: {result['format']}"]
    for skill in result["skills"]:
        lines.append(
            f"  skill   {skill['name']} ({skill['files']} files"
            + (f", {skill.get('bytes', 0)} bytes)" if "bytes" in skill else ")")
        )
        for note in skill["notes"]:
            lines.append(f"          note: {note}")
        for err in skill["errors"]:
            lines.append(f"          error: {err}")
    for out in result["outputs"]:
        lines.append(f"  wrote   {out}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Package Agent Skills into spec-clean directories, zips or plugins."
    )
    parser.add_argument("paths", nargs="+", help="skill directory, or a directory of skills")
    parser.add_argument("--output", required=True, help="destination file (.zip) or directory")
    parser.add_argument(
        "--format", choices=["zip", "spec-dir", "plugin"], default="zip",
        help="distributable format to build (default: zip)",
    )
    parser.add_argument("--plugin-name", help="plugin name when --format=plugin")
    parser.add_argument(
        "--keep-extensions", action="store_true",
        help="keep non-specification frontmatter fields instead of stripping them",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable output")
    args = parser.parse_args(argv)

    skill_dirs = []
    for raw in args.paths:
        path = Path(raw)
        if not path.exists():
            print(f"error: {raw} does not exist", file=sys.stderr)
            return 2
        skill_dirs.extend(meta.find_skills(path) or [path])

    result = pack_skills(
        skill_dirs,
        Path(args.output),
        fmt=args.format,
        plugin_name=args.plugin_name,
        strip_extensions=not args.keep_extensions,
    )
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_result(result))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
