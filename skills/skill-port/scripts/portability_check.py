#!/usr/bin/env python3
"""Find the parts of an Agent Skill that only work in one harness.

    python3 portability_check.py PATH [PATH ...] [--json]

Reports frontmatter outside the Agent Skills specification, harness-only
substitutions and tool names, hard-coded harness paths, and undeclared
runtime requirements. Exit status is 1 when something will break in
another harness ("breaks"), 0 otherwise. Standard library only.
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

BREAKS, ADAPT, NOTE = "breaks", "adapt", "note"
RANK = {BREAKS: 0, ADAPT: 1, NOTE: 2}

CLAUDE_FIELD_EFFECT = {
    "when_to_use": "merge this text into 'description'; other harnesses never read it",
    "argument-hint": "arguments are a Claude Code slash-command feature",
    "arguments": "arguments are a Claude Code slash-command feature",
    "disable-model-invocation": "elsewhere the skill stays model-invocable",
    "user-invocable": "has no effect elsewhere",
    "disallowed-tools": "tool restrictions are not enforced elsewhere",
    "model": "model selection is ignored elsewhere",
    "effort": "effort selection is ignored elsewhere",
    "context": "'context: fork' subagent isolation does not happen elsewhere; the skill runs inline",
    "agent": "subagent selection is ignored elsewhere",
    "background": "background execution is ignored elsewhere",
    "hooks": "hooks do not run elsewhere; anything they enforce is lost",
    "paths": "path-scoped activation is ignored elsewhere",
    "shell": "shell selection is ignored elsewhere",
}

SUBSTITUTION_RE = re.compile(
    r"\$ARGUMENTS(\[\d+\])?|\$\{CLAUDE_[A-Z_]+\}|\$\{user_config\.[\w.]+\}"
)
# "$1" is also ordinary shell and ordinary money, so positional arguments
# are only reported when the skill visibly uses Claude Code arguments.
POSITIONAL_RE = re.compile(r"(?<![\w$\\])\$[0-9](?!\w|[.,]\d)")
INJECT_INLINE_RE = re.compile(r"(?<![`\w])!`[^`\n]+`")
INJECT_BLOCK_RE = re.compile(r"^(`{3,}|~{3,})!\s*$")
MCP_TOOL_RE = re.compile(r"\bmcp__[A-Za-z0-9_-]+__[A-Za-z0-9_-]+\b")

# Tool names are only flagged when the text clearly refers to a tool.
TOOL_NAMES = {
    "Claude Code": (
        "Bash", "Read", "Edit", "Write", "Grep", "Glob", "WebFetch",
        "WebSearch", "AskUserQuestion", "TodoWrite", "NotebookEdit",
        "Task", "Agent", "Skill", "ToolSearch", "ExitPlanMode",
    ),
    "Gemini CLI": (
        "run_shell_command", "read_file", "write_file", "read_many_files",
        "search_file_content", "google_web_search", "web_fetch",
        "save_memory", "activate_skill", "list_directory",
    ),
    "Codex": ("apply_patch", "shell_command", "update_plan"),
}
NEUTRAL = {
    "Bash": "run a shell command", "run_shell_command": "run a shell command",
    "shell_command": "run a shell command",
    "Read": "read the file", "read_file": "read the file",
    "read_many_files": "read the files",
    "Edit": "edit the file", "Write": "write the file",
    "write_file": "write the file", "apply_patch": "edit the file",
    "Grep": "search file contents", "search_file_content": "search file contents",
    "Glob": "find files by name pattern", "list_directory": "list the directory",
    "WebFetch": "fetch the URL", "web_fetch": "fetch the URL",
    "WebSearch": "search the web", "google_web_search": "search the web",
    "AskUserQuestion": "ask the user", "TodoWrite": "keep a task list",
    "update_plan": "keep a task list",
    "Task": "delegate to a subagent if one is available",
    "Agent": "delegate to a subagent if one is available",
    "Skill": "load the other skill", "activate_skill": "load the other skill",
    "save_memory": "save a note to memory if the harness has one",
}
SNAKE_OR_CAMEL = re.compile(r"_|[a-z][A-Z]")

HARNESS_PATH_RE = re.compile(
    r"(~|\$HOME)?/?\.(claude|gemini|codex|cursor|agents)/[\w./-]*|\b(CLAUDE|GEMINI|AGENTS)\.md\b"
)
SLASH_COMMAND_RE = re.compile(
    r"(?<![\w/.:-])/(compact|clear|plugin|hooks|permissions|agents|mcp|memory|model|skills|init|resume|rewind)\b(?!/)"
)
# suffix -> (what to tell the reader, word to look for in 'compatibility')
INTERPRETERS = {
    ".py": ("python3", "python"), ".sh": ("a POSIX shell", "shell"),
    ".bash": ("bash", "bash"), ".zsh": ("zsh", "zsh"),
    ".js": ("node", "node"), ".mjs": ("node", "node"),
    ".ts": ("node with a TypeScript runner", "node"),
    ".rb": ("ruby", "ruby"), ".pl": ("perl", "perl"),
    ".ps1": ("PowerShell", "powershell"),
}
SHELL_SUFFIXES = {".sh", ".bash", ".zsh"}
CLI_RE = re.compile(
    r"^(?:\$\s+)?(?:sudo\s+)?(jq|gh|git|docker|kubectl|ffmpeg|pandoc|rg|fd|uv|"
    r"npx|npm|pnpm|yarn|make|aws|gcloud|az|terraform|sqlite3|psql|curl|wget)"
    r"(?:\s|$)"
)
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")


def code_segments(body: str) -> list:
    """Commands as written: fenced code lines and inline code spans."""
    segments, fence = [], None
    for line in body.split("\n"):
        stripped = line.strip()
        marker = re.match(r"(`{3,}|~{3,})", stripped)
        if fence is None and marker:
            fence = marker.group(1)[0] * 3
        elif fence is not None:
            if stripped.startswith(fence):
                fence = None
            else:
                segments.append(stripped)
        else:
            segments.extend(m.group(1).strip() for m in INLINE_CODE_RE.finditer(line))
    return segments


def tool_patterns() -> list:
    patterns = []
    for harness, names in TOOL_NAMES.items():
        for name in names:
            escaped = re.escape(name)
            if SNAKE_OR_CAMEL.search(name):
                regex = rf"(?<![\w`])`?{escaped}`?(?![\w(])"
            else:
                regex = (
                    rf"`{escaped}`(?: tool)?|\b{escaped} tool\b|"
                    rf"\b(?:use|using|call|invoke|with|via) (?:the )?{escaped}\b(?! (?:the|a|an|to|of)\b)"
                )
            patterns.append((harness, name, re.compile(regex)))
    return patterns


TOOL_PATTERNS = tool_patterns()


class Check:
    def __init__(self, skill_dir: Path):
        self.skill_dir = skill_dir
        self.findings: list = []

    def add(self, level, message, fix, file="SKILL.md", line=None):
        self.findings.append(
            {"level": level, "message": message, "fix": fix, "file": file, "line": line}
        )

    def worst(self):
        return min((RANK[f["level"]] for f in self.findings), default=None)


def check_frontmatter(check: Check, skill) -> None:
    fm = skill.frontmatter
    for key in fm:
        if key in meta.SPEC_FIELDS:
            continue
        if key in CLAUDE_FIELD_EFFECT:
            level = BREAKS if key in ("hooks", "context", "when_to_use") else ADAPT
            check.add(
                level,
                f"frontmatter '{key}' is a Claude Code extension",
                CLAUDE_FIELD_EFFECT[key],
            )
        else:
            check.add(
                ADAPT,
                f"frontmatter '{key}' is not in the Agent Skills specification",
                "move it under 'metadata' or drop it; strict packagers reject unknown fields",
            )
    if "allowed-tools" in fm:
        check.add(
            ADAPT,
            "'allowed-tools' is experimental and its tool names are harness-specific",
            "expect permission prompts elsewhere; do not rely on it for safety",
        )
    if (skill.path / "agents" / "openai.yaml").is_file():
        check.add(
            NOTE,
            "agents/openai.yaml is a Codex sidecar",
            "other harnesses ignore it; keep invocation policy in the description too",
            file="agents/openai.yaml",
        )


def check_body(check: Check, skill) -> None:
    lines = skill.body.split("\n")
    seen_tools, seen_paths = set(), set()
    uses_arguments = "$ARGUMENTS" in skill.body or any(
        key in skill.frontmatter for key in ("arguments", "argument-hint")
    )
    for offset, line in enumerate(lines):
        number = skill.body_line + offset
        tokens = {m.group(0) for m in SUBSTITUTION_RE.finditer(line)}
        if uses_arguments:
            tokens |= {m.group(0) for m in POSITIONAL_RE.finditer(line)}
        for token in sorted(tokens):
            check.add(
                BREAKS,
                f"{token} is substituted only by Claude Code; elsewhere "
                "the agent sees the literal text",
                "describe the input in words ('the file the user named') or "
                "use a path relative to the skill directory",
                line=number,
            )
        if INJECT_INLINE_RE.search(line) or INJECT_BLOCK_RE.match(line.strip()):
            check.add(
                BREAKS,
                "dynamic context injection (!`command`) runs only in Claude Code",
                "turn it into an explicit first step: 'Run <command> and read the output'",
                line=number,
            )
        for match in MCP_TOOL_RE.finditer(line):
            check.add(
                ADAPT,
                f"{match.group(0)} needs that MCP server configured in the target harness",
                "name the server as a prerequisite and say what to do when it is absent",
                line=number,
            )
        for harness, name, pattern in TOOL_PATTERNS:
            if name in seen_tools or not pattern.search(line):
                continue
            seen_tools.add(name)
            check.add(
                ADAPT,
                f"refers to the {harness} tool '{name}'",
                f"describe the action instead: \"{NEUTRAL.get(name, 'describe what to do')}\"",
                line=number,
            )
        for match in HARNESS_PATH_RE.finditer(line):
            text = match.group(0).rstrip(".,;:")
            if text in seen_paths:
                continue
            seen_paths.add(text)
            check.add(
                ADAPT,
                f"hard-codes the harness path or file '{text}'",
                "say 'the harness's skills directory' or 'the project instruction "
                "file', or list the equivalent for each target",
                line=number,
            )
        match = SLASH_COMMAND_RE.search(line)
        if match:
            check.add(
                NOTE,
                f"mentions the slash command {match.group(0)}",
                "slash commands differ between harnesses; describe the outcome wanted",
                line=number,
            )


def check_runtime(check: Check, skill) -> None:
    compatibility = str(skill.frontmatter.get("compatibility", "")).lower()
    needs = {}  # display name -> keyword expected in 'compatibility'
    suffixes = set()
    for rel in meta.iter_files(skill.path):
        if len(rel.parts) < 2:
            continue
        suffix = rel.suffix.lower()
        if suffix in INTERPRETERS:
            suffixes.add(suffix)
            display, keyword = INTERPRETERS[suffix]
            needs.setdefault(display, keyword)
    for segment in code_segments(skill.body):
        match = CLI_RE.match(segment)
        if match:
            needs.setdefault(match.group(1), match.group(1))
    missing = sorted(
        display for display, keyword in needs.items()
        if keyword not in compatibility
    )
    if missing:
        check.add(
            NOTE,
            "needs " + ", ".join(missing) + " but 'compatibility' does not say so",
            "add a 'compatibility' line listing what must be installed",
        )
    if suffixes & SHELL_SUFFIXES and ".ps1" not in suffixes:
        check.add(
            NOTE,
            "ships shell scripts with no Windows equivalent",
            "they will not run on Windows without WSL or Git Bash; say so, or "
            "provide a Python version",
        )


def check_skill(skill_dir) -> Check:
    check = Check(Path(skill_dir))
    skill = meta.load_skill(skill_dir)
    if not skill.skill_md.is_file() or not skill.has_frontmatter:
        check.add(BREAKS, "no SKILL.md with frontmatter", "run skill-lint first")
        return check
    check_frontmatter(check, skill)
    check_body(check, skill)
    check_runtime(check, skill)
    check.findings.sort(key=lambda f: (RANK[f["level"]], f["line"] or 0))
    return check


def format_check(check: Check) -> str:
    lines = [str(check.skill_dir)]
    if not check.findings:
        lines.append("  portable: nothing harness-specific found")
    for finding in check.findings:
        where = finding["file"] + (f":{finding['line']}" if finding["line"] else "")
        lines.append(f"  {finding['level']:<6} {where}  {finding['message']}")
        lines.append(f"         fix: {finding['fix']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Find the harness-specific parts of an Agent Skill."
    )
    parser.add_argument("paths", nargs="+", help="skill directory, or a directory of skills")
    parser.add_argument("--json", action="store_true", help="print machine-readable output")
    args = parser.parse_args(argv)

    skill_dirs = []
    for raw in args.paths:
        path = Path(raw)
        if not path.exists():
            print(f"error: {raw} does not exist", file=sys.stderr)
            return 2
        skill_dirs.extend(meta.find_skills(path) or [path])

    checks = [check_skill(skill_dir) for skill_dir in skill_dirs]
    if args.json:
        print(
            json.dumps(
                [{"path": str(c.skill_dir), "findings": c.findings} for c in checks],
                indent=2,
            )
        )
    else:
        print("\n\n".join(format_check(c) for c in checks))
        print(
            "\nbreaks = fails or misleads in another harness | adapt = works "
            "with changes | note = worth declaring"
        )
    return 1 if any(c.worst() == RANK[BREAKS] for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
