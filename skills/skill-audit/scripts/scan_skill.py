#!/usr/bin/env python3
"""Static triage of an Agent Skill before it is installed or trusted.

    python3 scan_skill.py PATH [PATH ...] [--json] [--min-severity LEVEL]

The scanner only reads files. It never executes, imports or sources
anything from the skill under review. It is a triage aid: a clean result
means "nothing matched", not "safe". Exit status is 2 when any high
finding exists, 1 for medium, 0 otherwise, and 3 on usage errors.
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # keep the skill directory free of __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _skillmeta as meta  # noqa: E402

HIGH, MEDIUM, LOW, INFO = "high", "medium", "low", "info"
RANK = {HIGH: 0, MEDIUM: 1, LOW: 2, INFO: 3}

MAX_TEXT_BYTES = 2_000_000
EXCERPT = 160

BIDI = set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A))
ZERO_WIDTH = {0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0x2061,
              0x2062, 0x2063, 0x2064, 0xFEFF, 0x00AD, 0x180E}
TAG_BLOCK = range(0xE0000, 0xE0080)
VARIATION_SELECTORS = set(range(0xFE00, 0xFE10)) | set(range(0xE0100, 0xE01F0))
MIXED_SCRIPT_RE = re.compile(
    r"\b(?=\w*[A-Za-z])(?=\w*[\u0370-\u03FF\u0400-\u04FF])\w+\b"
)

EXECUTABLE_MAGIC = (
    (b"\x7fELF", "ELF executable"),
    (b"MZ", "Windows PE executable"),
    (b"\xcf\xfa\xed\xfe", "Mach-O executable"),
    (b"\xce\xfa\xed\xfe", "Mach-O executable"),
    (b"\xca\xfe\xba\xbe", "Mach-O universal binary or Java class"),
)
ARCHIVE_SUFFIXES = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z",
                    ".rar", ".whl", ".jar", ".pyc", ".so", ".dll", ".dylib"}

# (severity, category, description, compiled pattern)
def _rules(*rules):
    return [(s, c, d, re.compile(p, re.IGNORECASE)) for s, c, d, p in rules]


LINE_RULES = _rules(
    # Instructions aimed at the agent rather than the task.
    (HIGH, "injection", "tells the agent to discard its existing instructions",
     r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all|any|system|safety)\b[^.\n]{0,30}\b(instructions?|rules?|prompts?|guidelines?|policies)\b"),
    (HIGH, "injection", "tells the agent to hide something from the user",
     r"\b(do not|don't|never|without)\b[^.\n]{0,25}\b(tell|inform|mention|reveal|show|notify|alert|disclos\w*|telling|informing|mentioning|notifying)\b[^.\n]{0,25}\b(the )?(user|human|operator|developer)\b"),
    (MEDIUM, "injection", "asks for covert behaviour",
     r"\b(secretly|covertly|stealthily|surreptitiously)\b|\b(silently|quietly)\s+(run|execute|send|upload|post|install|download|delete|remove|add|modify|write|copy|push|commit|transmit|exfiltrate|collect|read)\b|\b(run|execute|send|upload|post|install|download|delete|remove|add|modify|write|copy|push|commit|transmit|exfiltrate|collect|read)\b[^.\n]{0,40}\b(silently|quietly|in the background without)\b"),
    (MEDIUM, "injection", "tells the agent to skip confirmation or permission checks",
     r"\b(without (asking|confirmation|confirming|permission|approval|prompting)|skip (the )?(confirmation|permission|approval)|do not ask (for )?(permission|confirmation)|don't ask (for )?(permission|confirmation)|auto-?approve)\b"),
    (HIGH, "injection", "turns off the harness's permission or sandbox controls",
     r"(--dangerously-skip-permissions|--yolo\b|--no-sandbox\b|dangerouslyDisableSandbox|bypassPermissions|--trust-all-tools|approval[-_]policy\s*[=:]\s*\"?never)"),
    (MEDIUM, "injection", "tries to redefine the agent's role or authority",
     r"\b(you are now|from now on you|new system prompt|as the system|developer mode|jailbreak)\b"),
    (MEDIUM, "trigger", "description or text claims priority over everything else",
     r"\b(always use this skill|use this skill for (every|all|any)|before (any|every) other (skill|tool|action)|highest priority|must be (used|invoked) (first|for every))\b"),

    # Fetch-and-run.
    (HIGH, "remote-exec", "pipes a download straight into an interpreter",
     r"\b(curl|wget|fetch|iwr|invoke-webrequest|invoke-restmethod)\b[^\n|;]{0,200}\|\s*(sudo\s+)?(sh|bash|zsh|dash|python[0-9.]*|perl|ruby|node|iex|invoke-expression)\b"),
    (HIGH, "remote-exec", "runs code fetched in a subshell",
     r"\b(bash|sh|zsh|source|eval|python[0-9.]*)\b\s+(-c\s+)?[\"']?(<\(|\$\()\s*(curl|wget)\b"),
    (HIGH, "remote-exec", "decodes data and runs it",
     r"base64\s+(-d|--decode|-D)\b[^\n]{0,80}\|\s*(sudo\s+)?(sh|bash|zsh|python[0-9.]*|perl|node)\b"),
    (MEDIUM, "remote-exec", "installs a package at run time (check the name and pin)",
     r"\b(pip3?|pipx|uv(\s+pip)?)\s+install\b|\bnpm\s+(install|i)\s+(-g|--global)\b|\bnpx\s+(-y|--yes)\b|\bgem\s+install\b|\bcargo\s+install\b|\bgo\s+install\b|\bbrew\s+install\b|\bapt(-get)?\s+install\b"),
    (MEDIUM, "remote-exec", "installs from a URL or VCS reference instead of a registry release",
     r"\b(pip3?|uv pip|npm|pnpm|yarn)\s+(install|add|i)\b[^\n]{0,80}(https?://|git\+|github:)"),

    # Obfuscation and dynamic code.
    (MEDIUM, "obfuscation", "evaluates dynamically built code",
     r"(?<![\w.])(eval|exec)\s*\(|\bFunction\s*\(\s*[\"']|\b__import__\s*\(|\bcompile\s*\([^)]*[\"']exec[\"']"),
    (MEDIUM, "obfuscation", "deserialises or decodes opaque data",
     r"\b(marshal\.loads|pickle\.loads?|base64\.b64decode|binascii\.unhexlify|codecs\.decode\([^)]*rot|String\.fromCharCode|atob\s*\()|\bxxd\s+-r\b|\bbase64\s+(-d|--decode|-D)\b"),
    (LOW, "obfuscation", "spawns a shell from code",
     r"\b(os\.system|os\.popen|subprocess\.\w+\([^)]*shell\s*=\s*True|child_process|execSync|spawnSync)\b"),

    # Credentials and sensitive data.
    (HIGH, "credentials", "reads private keys or credential stores",
     r"(~|\$HOME|\$\{HOME\}|/home/[^/\s]+|/Users/[^/\s]+|/root)/\.(ssh|aws|gnupg|kube|docker|azure|netrc|npmrc|pypirc|git-credentials)\b|\bid_(rsa|ed25519|ecdsa|dsa)\b|/etc/shadow\b|\.config/gcloud\b|\bkeychain\b[^\n]{0,40}\b(dump|find|export)|security\s+find-(generic|internet)-password|\bLogin Data\b|\bCookies\.sqlite\b|wallet\.dat"),
    (MEDIUM, "credentials", "reads tokens or secrets from the environment or auth tools",
     r"\b(gh\s+auth\s+token|gcloud\s+auth\s+print-(access|identity)-token|aws\s+configure\s+(get|export-credentials)|printenv|os\.environ(?!\.get\(\s*[\"'](HOME|PATH|PWD|USER|SHELL|TERM|LANG)))\b|\$\{?[A-Z0-9_]*(TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|PRIVATE_KEY)[A-Z0-9_]*\}?|(^|[\s\"'`(])env\s*(\||>)"),
    (MEDIUM, "credentials", "reads dotenv or secrets files",
     r"(?<![\w.-])\.env(?!\.(example|sample|template|dist)\b)(\.[a-z]+)?\b|\bsecrets?\.(json|ya?ml|toml|txt)\b|\bcredentials\.json\b"),

    # Data leaving the machine.
    (HIGH, "exfiltration", "sends data to a paste, tunnel or webhook service",
     r"\b(webhook\.site|requestbin|pipedream\.net|ngrok(-free)?\.(io|app|dev)|pastebin\.com|paste\.ee|hastebin|transfer\.sh|0x0\.st|file\.io|termbin\.com|interact\.sh|oast\.(fun|pro|live|site)|burpcollaborator|discord(app)?\.com/api/webhooks|hooks\.slack\.com|api\.telegram\.org/bot)\b"),
    (HIGH, "exfiltration", "contacts a raw IP address",
     r"\b(https?|ftp|wss?)://\d{1,3}(\.\d{1,3}){3}\b(?!\.)"),
    (HIGH, "exfiltration", "Markdown image URL interpolates variables or secrets to exfiltrate data on render",
     r"!\[[^\]]*\]\(\s*https?://[^)\s]*(\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|\{\{[^}]+\}\}|[?&](?:data|secret|token|key|password|env)=)"),
    (MEDIUM, "exfiltration", "uploads or posts data",
     r"\bcurl\b[^\n]{0,200}\s(-d|--data(-binary|-raw|-urlencode)?|-F|--form|-T|--upload-file|-X\s*(POST|PUT))\b|\bwget\b[^\n]{0,120}--post-(data|file)|\brequests\.(post|put)\s*\(|\burllib\.request\.urlopen\s*\([^)]*data\s*=|\bfetch\s*\([^)]*method\s*:\s*[\"'](POST|PUT)"),
    (MEDIUM, "exfiltration", "opens a raw network channel",
     r"(?<![\w-])(nc|ncat|netcat|socat)\s+(-[a-z]+\s+)*[\w.-]+\s+\d{2,5}\b|/dev/(tcp|udp)/|\bsocket\.socket\s*\(|\bscp\s+[^\n]{0,80}\S+@\S+:|\brsync\s+[^\n]{0,80}\S+@\S+:"),
    (LOW, "network", "makes a network request",
     r"(?<![\w-])(curl|wget)\s+(-|https?://)|\brequests\.get\s*\(|\burllib\.request\b|\bhttp\.client\b|\bInvoke-WebRequest\b"),

    # Persistence and tampering with the agent's own configuration.
    (HIGH, "persistence", "writes to shell start-up, scheduler or SSH trust files",
     r"(>>?|tee(\s+-a)?|cp|mv|install|ln\s+-s\w*)\s+[^\n]{0,80}(\.(bashrc|bash_profile|zshrc|zprofile|profile)\b|authorized_keys\b|/etc/(cron|systemd|sudoers|profile)|LaunchAgents|LaunchDaemons)|\bcrontab\s+(-[^l\s]|[^-\s])|\bsystemctl\s+(--user\s+)?enable\b|\bschtasks\s+/create\b"),
    (HIGH, "persistence", "edits agent settings, hooks or instruction files",
     r"(>>?|tee(\s+-a)?|cp|mv|sed\s+-i|write|append|add|insert|modify|edit|update)\b[^\n]{0,80}((~|\$HOME)?/?\.(claude|gemini|codex|cursor|agents)/[\w./-]*(settings[\w.]*\.json|config\.toml|hooks?[\w./-]*|mcp[\w.]*\.json)|\b(CLAUDE|AGENTS|GEMINI)\.md\b|\.git/hooks/)"),
    (MEDIUM, "persistence", "installs or registers an MCP server, plugin or hook",
     r"\b(claude\s+mcp\s+add|gemini\s+mcp\s+add|codex\s+mcp\s+add|claude\s+plugin\s+(install|marketplace\s+add)|gemini\s+extensions\s+install)\b|\bgit\s+config\s+(--global\s+)?core\.hooksPath\b"),

    # Destructive commands.
    (HIGH, "destructive", "deletes or overwrites broadly",
     r"\brm\s+(-[a-z]*[rf][a-z]*\s+){1,3}(--no-preserve-root\s+)?[\"']?(/|~|\$HOME|\$\{HOME\}|\.\.?|\*)[\"']?(\s|$|;|&)|\bmkfs(\.\w+)?\s|\bdd\s+[^\n]*\bof=/dev/|\bshred\s|:\(\)\s*\{\s*:\|:&\s*\}\s*;|\bchmod\s+-R\s+0?777\b|\bformat\s+[a-z]:"),
    (MEDIUM, "destructive", "rewrites or discards version-control history",
     r"\bgit\s+(push\s+[^\n]*(--force\b|-f\b)|reset\s+--hard|clean\s+-[a-z]*f|checkout\s+--\s+\.|branch\s+-D)\b"),
    (LOW, "privilege", "asks for elevated privileges",
     r"(?<![\w-])sudo\s+\S|\bsu\s+-\s|\bdoas\s+\S|\brunas\s+/"),
)

URL_RE = re.compile(r"\b(?:https?|ftp|wss?)://([A-Za-z0-9.-]+)(?::\d+)?", re.I)
HTML_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.S)
BASE64_BLOB_RE = re.compile(r"[A-Za-z0-9+/]{200,}={0,2}")
HEX_BLOB_RE = re.compile(r"(?:\\x[0-9a-fA-F]{2}){24,}|\b[0-9a-fA-F]{256,}\b")
INJECTION_SHELL_RE = re.compile(r"(?<![`\w])!`([^`\n]+)`")
INJECTION_BLOCK_RE = re.compile(r"^(`{3,}|~{3,})!\s*$")
BROAD_TOOLS_RE = re.compile(r"(^|[\s,])(\*|Bash|Bash\(\*\)|Bash\(\*:\*\)|shell|run_shell_command)(?=$|[\s,])")
SHORTENER_HOSTS = {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "is.gd",
                   "cutt.ly", "rb.gy", "shorturl.at", "ow.ly"}


class Scan:
    def __init__(self, skill_dir: Path):
        self.skill_dir = skill_dir
        self.findings: list = []
        self.hosts: dict = {}
        self.files: list = []

    def add(self, severity, category, message, file, line=None, excerpt=""):
        excerpt = " ".join(excerpt.split())
        if len(excerpt) > EXCERPT:
            excerpt = excerpt[: EXCERPT - 1] + "…"
        self.findings.append(
            {
                "severity": severity,
                "category": category,
                "message": message,
                "file": file,
                "line": line,
                "excerpt": excerpt,
            }
        )

    def worst(self):
        return min((RANK[f["severity"]] for f in self.findings), default=None)


def visible(text: str) -> str:
    """Replace invisible and control characters with <U+XXXX> markers."""
    out = []
    for char in text:
        code = ord(char)
        if (
            code in BIDI
            or code in ZERO_WIDTH
            or code in TAG_BLOCK
            or code in VARIATION_SELECTORS
            or (code < 0x20 and char not in "\t")
        ):
            out.append(f"<U+{code:04X}>")
        else:
            out.append(char)
    return "".join(out)


def check_unicode(scan: Scan, rel: str, text: str) -> None:
    hidden = "".join(
        chr(ord(c) - 0xE0000) for c in text if ord(c) in TAG_BLOCK and 0x20 <= ord(c) - 0xE0000 < 0x7F
    )
    if hidden:
        scan.add(
            HIGH, "hidden-text",
            "Unicode tag characters encode text that is invisible in editors "
            "but readable by a model; decoded content follows",
            rel, excerpt=hidden,
        )
    for number, line in enumerate(text.split("\n"), 1):
        codes = {ord(c) for c in line}
        start = line[:1] == "\ufeff" and number == 1
        if codes & BIDI:
            scan.add(
                HIGH, "hidden-text",
                "bidirectional control characters can make text display in "
                "a different order from what is executed",
                rel, number, visible(line),
            )
        zero = codes & ZERO_WIDTH
        if zero and not (start and zero == {0xFEFF} and line.count("\ufeff") == 1):
            scan.add(
                MEDIUM, "hidden-text",
                "zero-width or invisible characters",
                rel, number, visible(line),
            )
        vs_count = sum(1 for c in line if ord(c) in VARIATION_SELECTORS)
        if vs_count >= 2 or any(0xE0100 <= ord(c) < 0xE01F0 for c in line):
            scan.add(
                HIGH, "hidden-text",
                "Unicode variation selectors can smuggle hidden byte sequences",
                rel, number, visible(line),
            )
        match = MIXED_SCRIPT_RE.search(line)
        if match:
            word = match.group(0)
            annotated = "".join(
                c if ord(c) < 128 else f"{c}<U+{ord(c):04X}>" for c in word
            )
            scan.add(
                HIGH, "hidden-text",
                f"mixed-script identifier {annotated!r} combines Latin with "
                "Cyrillic or Greek characters (homograph risk)",
                rel, number, line,
            )


def check_markdown(scan: Scan, rel: str, text: str) -> None:
    for match in HTML_COMMENT_RE.finditer(text):
        content = match.group(1).strip()
        if not content:
            continue
        line = text.count("\n", 0, match.start()) + 1
        scan.add(
            MEDIUM, "hidden-text",
            "HTML comment: hidden when rendered, still read by the agent",
            rel, line, content,
        )
    lines = text.split("\n")
    for number, line in enumerate(lines, 1):
        for match in INJECTION_SHELL_RE.finditer(line):
            scan.add(
                MEDIUM, "auto-exec",
                "dynamic context injection: this command runs when the skill "
                "loads, before the model reads anything",
                rel, number, match.group(1),
            )
        if INJECTION_BLOCK_RE.match(line.strip()):
            block = []
            for follow in lines[number:]:
                if follow.strip().startswith(("```", "~~~")):
                    break
                block.append(follow.strip())
            scan.add(
                MEDIUM, "auto-exec",
                "dynamic context injection block: these commands run when "
                "the skill loads",
                rel, number, "; ".join(block),
            )


def check_lines(scan: Scan, rel: str, text: str) -> None:
    raw_lines = text.split("\n")
    hits_by_line: dict = {}
    for number, line in enumerate(raw_lines, 1):
        sample = line[:4000] if len(line) > 4000 else line
        hits = hits_by_line.setdefault(number, set())
        for severity, category, message, pattern in LINE_RULES:
            match = pattern.search(sample)
            if match and (category, message) not in hits:
                hits.add((category, message))
                start = max(0, match.start() - 40)
                scan.add(
                    severity, category, message, rel, number,
                    visible(sample[start: match.end() + 80]),
                )
        if BASE64_BLOB_RE.search(line):
            scan.add(
                MEDIUM, "obfuscation",
                "long base64-like blob; decode it before trusting it",
                rel, number, line,
            )
        elif HEX_BLOB_RE.search(line):
            scan.add(
                MEDIUM, "obfuscation",
                "long hex-encoded blob; decode it before trusting it",
                rel, number, line,
            )
        for match in URL_RE.finditer(line):
            host = match.group(1).lower().rstrip(".")
            scan.hosts.setdefault(host, f"{rel}:{number}")
            if host in SHORTENER_HOSTS:
                scan.add(
                    MEDIUM, "exfiltration",
                    "URL shortener hides the real destination",
                    rel, number, match.group(0),
                )

    # Join backslash-continued lines so split commands cannot evade LINE_RULES.
    index = 0
    while index < len(raw_lines):
        if not raw_lines[index].rstrip().endswith("\\"):
            index += 1
            continue
        start_num = index + 1
        parts = [raw_lines[index].rstrip()[:-1]]
        end = index + 1
        while end < len(raw_lines):
            stripped = raw_lines[end].rstrip()
            if stripped.endswith("\\"):
                parts.append(stripped[:-1].lstrip())
                end += 1
            else:
                parts.append(stripped.lstrip())
                end += 1
                break
        joined = " ".join(parts)[:4000]
        existing = set()
        for num in range(start_num, end + 1):
            existing |= hits_by_line.get(num, set())
        for severity, category, message, pattern in LINE_RULES:
            match = pattern.search(joined)
            if match and (category, message) not in existing:
                existing.add((category, message))
                start = max(0, match.start() - 40)
                scan.add(
                    severity, category, message, rel, start_num,
                    visible(joined[start: match.end() + 80]),
                )
        index = end


def check_frontmatter(scan: Scan, skill) -> None:
    fm = skill.frontmatter
    allowed = fm.get("allowed-tools")
    if allowed:
        text = " ".join(allowed) if isinstance(allowed, list) else str(allowed)
        if BROAD_TOOLS_RE.search(text):
            scan.add(
                MEDIUM, "permissions",
                "allowed-tools pre-approves unrestricted shell or all tools, "
                "so commands run without a permission prompt",
                "SKILL.md", excerpt=text,
            )
        else:
            scan.add(
                LOW, "permissions",
                "allowed-tools pre-approves these tools; confirm each is needed",
                "SKILL.md", excerpt=text,
            )
    if "hooks" in fm:
        scan.add(
            MEDIUM, "auto-exec",
            "frontmatter defines hooks, which run commands automatically "
            "while the skill is active",
            "SKILL.md", excerpt=json.dumps(fm["hooks"], default=str),
        )
    for line, message in skill.problems:
        scan.add(
            LOW, "malformed",
            f"frontmatter does not parse cleanly ({message}); a harness may "
            "read it differently from how it looks",
            "SKILL.md", line,
        )


def check_file(scan: Scan, skill_dir: Path, rel: Path) -> None:
    path = skill_dir / rel
    name = rel.as_posix()
    if path.is_symlink():
        target = os.path.realpath(path)
        root = os.path.realpath(skill_dir)
        if not (target == root or target.startswith(root + os.sep)):
            scan.add(
                HIGH, "filesystem",
                "symlink points outside the skill directory",
                name, excerpt=f"-> {os.readlink(path)}",
            )
            return
    if path.is_dir():
        return  # a directory symlink that stays inside the skill
    try:
        size = path.stat().st_size
        with open(path, "rb") as handle:
            head = handle.read(8192)
    except OSError as error:
        scan.add(LOW, "filesystem", f"cannot read file: {error}", name)
        return
    scan.files.append({"path": name, "bytes": size})

    for magic, label in EXECUTABLE_MAGIC:
        if head.startswith(magic):
            scan.add(
                HIGH, "binary",
                f"{label}: compiled code cannot be reviewed by reading it",
                name,
            )
            return
    if rel.suffix.lower() in ARCHIVE_SUFFIXES:
        scan.add(
            MEDIUM, "binary",
            "archive or compiled artefact; unpack and review the contents "
            "separately",
            name,
        )
        return
    if size > MAX_TEXT_BYTES:
        scan.add(
            LOW, "filesystem",
            f"file is {size} bytes; too large to scan, review it by hand",
            name,
        )
        return
    text = meta.read_text(path)
    if text is None:
        scan.add(
            MEDIUM, "binary",
            "not UTF-8 text; the scanner cannot read it",
            name,
        )
        return
    if rel.name.startswith(".") and rel.name not in (".gitignore", ".gitattributes"):
        scan.add(LOW, "filesystem", "hidden file", name)
    if os.access(path, os.X_OK) and not text.startswith("#!") and len(rel.parts) > 1:
        scan.add(LOW, "filesystem", "executable bit set on a file with no shebang", name)

    check_unicode(scan, name, text)
    if rel.suffix.lower() in (".md", ".markdown", ".mdx", ".txt", ""):
        check_markdown(scan, name, text)
    check_lines(scan, name, text)


def scan_skill(skill_dir) -> Scan:
    skill_dir = Path(skill_dir)
    scan = Scan(skill_dir)
    skill = meta.load_skill(skill_dir)
    if not skill.skill_md.is_file():
        scan.add(INFO, "malformed", "no SKILL.md; not a skill directory", ".")
    elif not skill.has_frontmatter:
        scan.add(LOW, "malformed", "SKILL.md has no frontmatter", "SKILL.md")
    else:
        check_frontmatter(scan, skill)

    entries = []
    for current, dirs, files in os.walk(skill_dir, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d != ".git")
        for directory in list(dirs):
            full = Path(current) / directory
            if full.is_symlink():
                entries.append(full.relative_to(skill_dir))
        for name in sorted(files):
            entries.append((Path(current) / name).relative_to(skill_dir))
    for rel in sorted(entries):
        check_file(scan, skill_dir, rel)

    upgrade_combined(scan)
    scan.findings.sort(
        key=lambda f: (RANK[f["severity"]], f["file"], f["line"] or 0)
    )
    return scan


def upgrade_combined(scan: Scan) -> None:
    """A file that both reads secrets and talks to the network is the
    classic exfiltration shape; call it out even if each half is medium."""
    by_file: dict = {}
    for finding in scan.findings:
        by_file.setdefault(finding["file"], set()).add(finding["category"])
    for file, categories in sorted(by_file.items()):
        if "credentials" in categories and categories & {"exfiltration", "network"}:
            scan.add(
                HIGH, "exfiltration",
                "this file both reads credentials and makes network "
                "requests; trace where the data goes",
                file,
            )


def verdict(scan: Scan) -> str:
    worst = scan.worst()
    if worst == RANK[HIGH]:
        return "BLOCK until every high finding is explained"
    if worst == RANK[MEDIUM]:
        return "REVIEW each medium finding before installing"
    return "No pattern matched; a manual read is still required"


def format_scan(scan: Scan, minimum: str) -> str:
    lines = [f"{scan.skill_dir}", f"  verdict: {verdict(scan)}"]
    shown = [f for f in scan.findings if RANK[f["severity"]] <= RANK[minimum]]
    for finding in shown:
        where = finding["file"]
        if finding["line"]:
            where += f":{finding['line']}"
        lines.append(
            f"  {finding['severity'].upper():<6} [{finding['category']}] "
            f"{where}  {finding['message']}"
        )
        if finding["excerpt"]:
            lines.append(f"         > {finding['excerpt']}")
    hidden = len(scan.findings) - len(shown)
    if hidden:
        lines.append(f"  ({hidden} lower-severity finding(s) not shown)")
    if scan.hosts:
        lines.append("  external hosts referenced:")
        for host, where in sorted(scan.hosts.items()):
            lines.append(f"    {host}  ({where})")
    lines.append(f"  files scanned: {len(scan.files)}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Static triage of an Agent Skill before installing it."
    )
    parser.add_argument("paths", nargs="+", help="skill directory, or a directory of skills")
    parser.add_argument("--json", action="store_true", help="print machine-readable output")
    parser.add_argument(
        "--min-severity", choices=[HIGH, MEDIUM, LOW, INFO], default=LOW,
        help="lowest severity to print (default: low)",
    )
    args = parser.parse_args(argv)

    skill_dirs = []
    for raw in args.paths:
        path = Path(raw)
        if not path.is_dir():
            print(f"error: {raw} is not a directory", file=sys.stderr)
            return 3
        skill_dirs.extend(meta.find_skills(path) or [path])

    scans = [scan_skill(skill_dir) for skill_dir in skill_dirs]
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "path": str(s.skill_dir),
                        "verdict": verdict(s),
                        "findings": s.findings,
                        "hosts": s.hosts,
                        "files": s.files,
                    }
                    for s in scans
                ],
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print("\n\n".join(format_scan(s, args.min_severity) for s in scans))
        print(
            "\nThis is pattern matching, not proof. Read every file before "
            "you install a skill."
        )
    worst = min((s.worst() for s in scans if s.worst() is not None), default=None)
    if worst == RANK[HIGH]:
        return 2
    if worst == RANK[MEDIUM]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
