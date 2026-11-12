#!/usr/bin/env bash
# Install agent-metaskills into an agent harness's skills directory.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_dir="$here/skills"

usage() {
  cat <<'USAGE'
Usage: ./install.sh [options] [skill ...]

Copies skills from this repository into a harness's skills directory.
With no skill names, installs all of them.

Options:
  --target NAME|PATH  Where to install (default: claude)
                        claude       ~/.claude/skills
                        agents       ~/.agents/skills   (Codex, Gemini CLI)
                        gemini       ~/.gemini/skills
                        antigravity  ~/.gemini/config/skills
                        PATH         any directory
  --project DIR       Install into DIR's project-level directory instead
                      (.claude/skills, .agents/skills or .gemini/skills)
  --link              Symlink instead of copying, so 'git pull' updates them
  --force             Replace a skill that is already installed
  --list              List the available skills and exit
  -h, --help          Show this help
USAGE
}

target="claude"
project=""
link=0
force=0
skills=()

while [ $# -gt 0 ]; do
  case "$1" in
    --target) [ $# -ge 2 ] || { echo "error: --target needs a value" >&2; exit 2; }
              target="$2"; shift 2 ;;
    --project) [ $# -ge 2 ] || { echo "error: --project needs a value" >&2; exit 2; }
               project="$2"; shift 2 ;;
    --link) link=1; shift ;;
    --force) force=1; shift ;;
    --list) ls -1 "$source_dir"; exit 0 ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "error: unknown option $1" >&2; usage >&2; exit 2 ;;
    *) skills+=("$1"); shift ;;
  esac
done

if [ -n "$project" ]; then
  case "$target" in
    claude) dest="$project/.claude/skills" ;;
    agents|antigravity) dest="$project/.agents/skills" ;;
    gemini) dest="$project/.gemini/skills" ;;
    *) echo "error: --project needs --target claude, agents, gemini or antigravity" >&2; exit 2 ;;
  esac
else
  case "$target" in
    claude) dest="$HOME/.claude/skills" ;;
    agents) dest="$HOME/.agents/skills" ;;
    gemini) dest="$HOME/.gemini/skills" ;;
    antigravity) dest="$HOME/.gemini/config/skills" ;;
    *) dest="$target" ;;
  esac
fi

if [ ${#skills[@]} -eq 0 ]; then
  for dir in "$source_dir"/*/; do
    skills+=("$(basename "$dir")")
  done
fi

for name in "${skills[@]}"; do
  if [ ! -f "$source_dir/$name/SKILL.md" ]; then
    echo "error: no skill named '$name' (try --list)" >&2
    exit 2
  fi
done

mkdir -p "$dest"
installed=0
skipped=0
for name in "${skills[@]}"; do
  to="$dest/$name"
  if [ -e "$to" ] || [ -L "$to" ]; then
    if [ "$force" -ne 1 ]; then
      echo "skip     $name (already at $to; use --force to replace)"
      skipped=$((skipped + 1))
      continue
    fi
    rm -rf -- "$to"
  fi
  if [ "$link" -eq 1 ]; then
    ln -s "$source_dir/$name" "$to"
    echo "linked   $name -> $to"
  else
    cp -R "$source_dir/$name" "$to"
    find "$to" -name __pycache__ -type d -prune -exec rm -rf {} +
    echo "copied   $name -> $to"
  fi
  installed=$((installed + 1))
done

echo "$installed installed, $skipped skipped. Start a new agent session to pick them up."
