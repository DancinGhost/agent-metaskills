"""Shared helpers for the agent-metaskills scripts. Standard library only.

Canonical copy: shared/skillmeta.py. It is vendored into each skill as
scripts/_skillmeta.py by tools/sync_shared.py so that every skill stays
self-contained. Edit the canonical copy, then run the sync tool.
"""

from __future__ import annotations

import hashlib
import os
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

SKILL_FILE = "SKILL.md"

# Fields defined by the Agent Skills specification (agentskills.io).
SPEC_FIELDS = (
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
)

# Extra frontmatter fields that Claude Code understands. Other harnesses
# ignore them, and strict packagers reject them.
CLAUDE_CODE_FIELDS = (
    "when_to_use",
    "argument-hint",
    "arguments",
    "disable-model-invocation",
    "user-invocable",
    "disallowed-tools",
    "model",
    "effort",
    "context",
    "agent",
    "background",
    "hooks",
    "paths",
    "shell",
)

NAME_MAX = 64
DESCRIPTION_MAX = 1024
COMPATIBILITY_MAX = 500
BODY_MAX_LINES = 500
BODY_MAX_TOKENS = 5000

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tox", ".trash"}

_KEY_RE = re.compile(r"^([A-Za-z0-9_.-]+)\s*:(?:[ \t]+(.*))?$")
_RESERVED_START = "@`%*&!"


@dataclass
class Skill:
    """A skill directory and the parsed contents of its SKILL.md."""

    path: Path
    skill_md: Path
    text: str = ""
    frontmatter: dict = field(default_factory=dict)
    has_frontmatter: bool = False
    problems: list = field(default_factory=list)  # (line, message)
    body: str = ""
    body_line: int = 1  # 1-based line in SKILL.md where the body starts

    @property
    def name(self) -> str:
        value = self.frontmatter.get("name")
        return value if isinstance(value, str) else ""

    @property
    def description(self) -> str:
        value = self.frontmatter.get("description")
        return value if isinstance(value, str) else ""


def estimate_tokens(text: str) -> int:
    """Rough token estimate (about four characters per token)."""
    return (len(text) + 3) // 4


def split_frontmatter(text: str):
    """Return (frontmatter_text or None, body, body_start_line)."""
    text = text.lstrip("\ufeff").replace("\r\n", "\n")
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, text, 1
    for index in range(1, len(lines)):
        if lines[index].strip() in ("---", "..."):
            front = "\n".join(lines[1:index])
            body = "\n".join(lines[index + 1:])
            return front, body, index + 2
    return None, text, 1


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] == '"':
        inner = value[1:-1]
        escapes = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "/": "/"}
        return re.sub(
            r"\\(.)", lambda m: escapes.get(m.group(1), m.group(0)), inner
        )
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def _scalar(raw: str, line: int, problems: list, key: str = "") -> str:
    """Parse one scalar and record the YAML traps that bite skill authors."""
    value = raw.strip()
    if not value:
        return ""
    label = f"'{key}'" if key else "value"
    if value[0] in "\"'":
        quote = value[0]
        end = _closing_quote(value, quote)
        if end == -1:
            problems.append((line, f"{label}: quoted string is never closed"))
            return value[1:]
        rest = value[end + 1:].strip()
        if rest and not rest.startswith("#"):
            problems.append(
                (line, f"{label}: unexpected text after the closing quote")
            )
        return _unquote(value[: end + 1])
    comment = re.search(r"\s#", value)
    if comment:
        problems.append(
            (
                line,
                f"{label}: unquoted ' #' starts a YAML comment, so the rest "
                "of the value is dropped; quote the value",
            )
        )
        value = value[: comment.start()].rstrip()
    if re.search(r":(\s|$)", value):
        problems.append(
            (
                line,
                f"{label}: unquoted ': ' is invalid YAML in strict parsers; "
                "quote the value or use a block scalar (>-)",
            )
        )
    if value and value[0] in _RESERVED_START:
        problems.append(
            (
                line,
                f"{label}: unquoted value starts with '{value[0]}', which "
                "YAML reserves; quote the value",
            )
        )
    return value


def _closing_quote(value: str, quote: str) -> int:
    index = 1
    while index < len(value):
        char = value[index]
        if quote == '"' and char == "\\":
            index += 2
            continue
        if char == quote:
            if quote == "'" and value[index + 1: index + 2] == "'":
                index += 2
                continue
            return index
        index += 1
    return -1


def _dedent(block: list) -> list:
    indents = [len(l) - len(l.lstrip(" ")) for l in block if l.strip()]
    cut = min(indents) if indents else 0
    return [l[cut:] if l.strip() else "" for l in block]


def _block_scalar(style: str, block: list) -> str:
    lines = _dedent(block)
    while lines and not lines[-1]:
        lines.pop()
    if style == "|":
        return "\n".join(lines)
    out, paragraph = [], []
    for item in lines:
        if item:
            paragraph.append(item.strip())
        elif paragraph:
            out.append(" ".join(paragraph))
            paragraph = []
    if paragraph:
        out.append(" ".join(paragraph))
    return "\n".join(out)


def _inline_list(value: str, line: int, problems: list) -> list:
    inner = value[1:-1].strip()
    if not inner:
        return []
    return [_scalar(part, line, problems) for part in inner.split(",")]


def _nested(block: list, line: int, problems: list, key: str):
    lines = _dedent(block)
    first = next((l for l in lines if l.strip()), "")
    if not (first.startswith("- ") or first == "-"):
        return _parse_map(lines, line + 1, problems)
    items = []
    for offset, item in enumerate(lines):
        if not item.strip() or item.lstrip().startswith("#"):
            continue
        if item.startswith("- ") or item == "-":
            # A list of mappings (for example hook definitions) is kept as
            # text; only plain string items are checked for YAML traps.
            sink = [] if _KEY_RE.match(item[1:].strip()) else problems
            items.append(_scalar(item[1:], line + offset + 1, sink))
        elif items and item.startswith(" "):
            items[-1] = (items[-1] + " " + item.strip()).strip()
        else:
            problems.append(
                (line + offset + 1, f"'{key}': expected a list item")
            )
    return items


def _parse_map(lines: list, first_line: int, problems: list) -> dict:
    data: dict = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        number = first_line + index
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        if "\t" in line[: len(line) - len(line.lstrip())]:
            problems.append((number, "tab used for indentation"))
        match = _KEY_RE.match(line)
        if line[0] in " \t" or not match:
            problems.append((number, f"cannot parse line: {line.strip()!r}"))
            index += 1
            continue
        key, rest = match.group(1), (match.group(2) or "").strip()
        end = index + 1
        while end < len(lines):
            nxt = lines[end]
            if not nxt.strip() or nxt[0] in " \t":
                end += 1
            elif not rest and (nxt.startswith("- ") or nxt == "-"):
                end += 1
            else:
                break
        block = lines[index + 1:end]
        while block and not block[-1].strip():
            block.pop()
        if key in data:
            problems.append((number, f"duplicate key '{key}'"))
        indicator = rest.split("#")[0].strip()
        if re.fullmatch(r"[|>][+-]?\d?[+-]?", indicator):
            data[key] = _block_scalar(rest[0], block)
        elif not rest:
            data[key] = _nested(block, number, problems, key) if block else ""
        elif rest.startswith("[") and rest.endswith("]"):
            data[key] = _inline_list(rest, number, problems)
        else:
            folded = " ".join([rest] + [b.strip() for b in block if b.strip()])
            data[key] = _scalar(folded, number, problems, key)
        index = end
    return data


def parse_frontmatter(text: str, first_line: int = 2):
    """Parse the YAML subset used in SKILL.md frontmatter.

    Returns (data, problems). Values are strings, lists of strings, or
    nested dicts. Problems are (line, message) tuples for syntax that a
    strict YAML parser would reject or silently misread.
    """
    problems: list = []
    data = _parse_map(text.replace("\r\n", "\n").split("\n"), first_line, problems)
    return data, problems


def load_skill(path) -> Skill:
    """Load a skill directory (or a path to its SKILL.md)."""
    path = Path(path)
    if path.is_file():
        path = path.parent
    skill = Skill(path=path, skill_md=path / SKILL_FILE)
    if not skill.skill_md.is_file():
        return skill
    skill.text = skill.skill_md.read_text(encoding="utf-8", errors="replace")
    front, body, body_line = split_frontmatter(skill.text)
    skill.body, skill.body_line = body, body_line
    if front is not None:
        skill.has_frontmatter = True
        skill.frontmatter, skill.problems = parse_frontmatter(front)
    return skill


def find_skills(root, max_depth: int = 6, include_hidden: bool = True) -> list:
    """Return skill directories at or below root, sorted by path.

    With include_hidden=False, dot-directories below root are skipped.
    """
    root = Path(root)
    if root.is_file():
        return [root.parent] if root.name == SKILL_FILE else []
    if (root / SKILL_FILE).is_file():
        return [root]
    found, seen = [], set()
    base_depth = len(root.parts)
    for current, dirs, files in os.walk(root, followlinks=True):
        real = os.path.realpath(current)
        if real in seen:
            dirs[:] = []
            continue
        seen.add(real)
        here = Path(current)
        dirs[:] = sorted(
            d for d in dirs
            if d not in SKIP_DIRS and (include_hidden or not d.startswith("."))
        )
        if SKILL_FILE in files:
            found.append(here)
            dirs[:] = []
        elif len(here.parts) - base_depth >= max_depth:
            dirs[:] = []
    return sorted(found)


def iter_files(skill_dir) -> list:
    """All regular files in a skill directory, as sorted relative paths."""
    skill_dir = Path(skill_dir)
    out = []
    for current, dirs, files in os.walk(skill_dir):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            out.append((Path(current) / name).relative_to(skill_dir))
    return out


def read_text(path):
    """Return file text, or None when the file is not UTF-8 text."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def strip_fenced_code(text: str) -> str:
    """Blank out fenced code blocks, keeping line numbers intact."""
    out, fence = [], None
    for line in text.replace("\r\n", "\n").split("\n"):
        stripped = line.lstrip()
        marker = re.match(r"(`{3,}|~{3,})", stripped)
        if fence is None and marker:
            fence = marker.group(1)[0] * 3
            out.append("")
        elif fence is not None:
            if stripped.startswith(fence) and not stripped.strip(fence[0]).strip():
                fence = None
            out.append("")
        else:
            out.append(line)
    return "\n".join(out)


STOPWORDS = set(
    """a an and any are as at be been before by can do does for from has have
    how if in into is it its may more must new not of on or other should so
    such than that the their them then these this those to up use used user
    users using when whenever where which while will with without you your
    skill skills agent agents task tasks ask asks asked want wants need needs
    mention mentions about also all each every etc e g i""".split()
)


def keywords(text: str) -> set:
    """Extract stemmed content keywords from a skill name, description or query."""
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
    """Jaccard similarity between two keyword sets."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def heading_slug(title: str) -> str:
    """GitHub-style anchor slug for a Markdown heading title."""
    cleaned = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", title)
    cleaned = re.sub(r"[`*_~]", "", cleaned).strip().lower()
    cleaned = re.sub(r"[^a-z0-9\s_-]", "", cleaned)
    return re.sub(r"\s+", "-", cleaned)


def extract_headings(text: str, start_line: int = 1) -> list:
    """Return Markdown headings outside fenced code as dicts with level, title, slug, line."""
    headings = []
    counts: dict = {}
    for offset, line in enumerate(strip_fenced_code(text).split("\n")):
        match = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        level = len(match.group(1))
        title = match.group(2).strip()
        base = heading_slug(title)
        seen = counts.get(base, 0)
        counts[base] = seen + 1
        slug = base if seen == 0 else f"{base}-{seen}"
        headings.append(
            {
                "level": level,
                "title": title,
                "slug": slug,
                "line": start_line + offset,
            }
        )
    return headings


def skill_digest(skill_dir) -> str:
    """Deterministic SHA-256 hex digest (16 chars) of a skill directory's contents."""
    skill_dir = Path(skill_dir)
    hasher = hashlib.sha256()
    for rel in iter_files(skill_dir):
        hasher.update(rel.as_posix().encode("utf-8") + b"\x00")
        try:
            raw = (skill_dir / rel).read_bytes()
        except OSError:
            continue
        if b"\x00" not in raw[:8192]:
            raw = raw.replace(b"\r\n", b"\n")
        hasher.update(raw + b"\x00")
    return hasher.hexdigest()[:16]


def _needs_quoting(value: str) -> bool:
    if not value:
        return True
    if value[0] in _RESERVED_START or value[0] in "\"'[{>|":
        return True
    if re.search(r":(\s|$)|\s#", value):
        return True
    if re.fullmatch(r"[0-9._+-]+|true|false|null|yes|no|on|off", value, re.I):
        return True
    return False


def _quote_scalar(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def format_frontmatter(data: dict) -> str:
    """Format a frontmatter mapping into clean, portable YAML without traps."""
    ordered = [k for k in SPEC_FIELDS if k in data]
    ordered += [k for k in data if k not in SPEC_FIELDS]
    lines = []
    for key in ordered:
        value = data[key]
        if value is None:
            continue
        if isinstance(value, dict):
            lines.append(f"{key}:")
            for sub_key, sub_val in value.items():
                text = str(sub_val)
                rendered = _quote_scalar(text) if _needs_quoting(text) else text
                lines.append(f"  {sub_key}: {rendered}")
        elif isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                text = str(item)
                rendered = _quote_scalar(text) if _needs_quoting(text) else text
                lines.append(f"  - {rendered}")
        else:
            text = str(value).strip()
            if key == "description" and (
                len(text) > 60 or "\n" in text or _needs_quoting(text)
            ):
                lines.append(f"{key}: >-")
                paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
                for idx, para in enumerate(paragraphs):
                    if idx > 0:
                        lines.append("")
                    wrapped = textwrap.fill(
                        " ".join(para.split()),
                        width=78,
                        initial_indent="  ",
                        subsequent_indent="  ",
                        break_long_words=False,
                        break_on_hyphens=False,
                    )
                    lines.append(wrapped)
            elif "\n" in text:
                lines.append(f"{key}: |")
                for sub_line in text.split("\n"):
                    lines.append(f"  {sub_line}" if sub_line else "")
            elif _needs_quoting(text):
                lines.append(f"{key}: {_quote_scalar(text)}")
            else:
                lines.append(f"{key}: {text}")
    return "\n".join(lines)
