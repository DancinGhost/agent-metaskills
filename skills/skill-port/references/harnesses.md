# Where harnesses look for skills

Checked against each vendor's documentation in November 2026. These details
change between releases; when something here disagrees with the harness's own
documentation, the documentation wins.

## Locations

| Harness | User level | Project level | Other |
|---|---|---|---|
| Claude Code | `~/.claude/skills/<name>/` | `.claude/skills/<name>/`, also in nested subdirectories | Plugins: `<plugin>/skills/<name>/`, invoked as `/<plugin>:<name>`. Enterprise: managed settings directory. |
| Codex | `~/.agents/skills/<name>/` | `.agents/skills/<name>/` in the working directory and each parent up to the repository root | Admin: `/etc/codex/skills/`. |
| Gemini CLI | `~/.gemini/skills/<name>/` or `~/.agents/skills/<name>/` | `.gemini/skills/<name>/` or `.agents/skills/<name>/` | Extensions bundle their own skills. |
| Antigravity | `~/.gemini/config/skills/<name>/` | `.agents/skills/<name>/` or `.agent/skills/<name>/` | Plugins: `~/.gemini/config/plugins/<plugin>/skills/<name>/`. Built-in skills ship with the product. |
| Cursor | `~/.cursor/skills/<name>/` | `.cursor/skills/<name>/` or `.agents/skills/<name>/` | Also reads project rules under `.cursor/rules/`. |
| Windsurf | `~/.codeium/windsurf/skills/<name>/` | `.windsurf/skills/<name>/` or `.agents/skills/<name>/` | Also reads `.windsurf/rules/`. |
| GitHub Copilot | `~/.copilot/skills/<name>/` | `.github/skills/<name>/` | Also reads `.github/copilot-instructions.md`. |
| OpenCode | `~/.config/opencode/skills/<name>/` | `.opencode/skills/<name>/` or `.agents/skills/<name>/` | Also reads `.claude/skills/<name>/` for compatibility. |

`.agents/skills/` (project) and `~/.agents/skills/` (user) are read by Codex
and Gemini CLI, and the project form by Antigravity. Claude Code does not read
them; for Claude Code, copy or symlink the skill into `.claude/skills/`.

## Precedence when two skills share a name

| Harness | Rule |
|---|---|
| Gemini CLI | Workspace over user over extension over built-in. Within one tier, `.agents/skills/` over `.gemini/skills/`. |
| Codex | Same-named skills are not merged; both can appear in the selector. |
| Claude Code | Plugin skills are namespaced by plugin, so they never collide with personal or project skills. For personal versus project versus enterprise, check the current documentation. |

## Frontmatter

Every harness reads `name` and `description`. Beyond that:

| Field | Specification | Claude Code | Others |
|---|---|---|---|
| `license`, `compatibility`, `metadata` | Yes | Accepted | Accepted or ignored |
| `allowed-tools` | Experimental | Honoured | Varies; do not rely on it |
| `when_to_use`, `argument-hint`, `arguments`, `disable-model-invocation`, `user-invocable`, `disallowed-tools`, `model`, `effort`, `context`, `agent`, `background`, `hooks`, `paths`, `shell` | No | Yes | Ignored. Strict packagers, including claude.ai skill upload, reject fields outside the specification. |

Codex keeps its extras out of SKILL.md, in an optional `agents/openai.yaml`
beside it (interface metadata, whether implicit invocation is allowed, tool
dependencies).

## Body features that exist only in Claude Code

| Feature | Looks like | Portable replacement |
|---|---|---|
| Argument substitution | `$ARGUMENTS`, `$0`, `$1`, named arguments | Describe the input in words; tell the agent to ask if it is missing. |
| Path variables | `${CLAUDE_SKILL_DIR}`, `${CLAUDE_PROJECT_DIR}`, `${CLAUDE_PLUGIN_ROOT}` | Paths relative to the skill directory. |
| Load-time command injection | An exclamation mark followed by a backticked command, or a fenced block whose opening fence ends in an exclamation mark | An explicit first step that runs the command. |
| Forked context | `context: fork` | "Delegate to a subagent if one is available." |

## Confirming a skill was picked up

| Harness | How |
|---|---|
| Claude Code | Start a new session and type `/` followed by the skill name, or ask which skills are available. |
| Gemini CLI | `gemini skills list --all`, or `/skills list` in a session. `/skills reload` rescans without restarting. |
| Codex | Open the skill selector in a session; restart Codex if a new skill is missing. |
| Antigravity | Start a new conversation in the workspace and ask which skills are available. |

Listing shows discovery only. Finish with a real request that should trigger
the skill.

## Installing from a repository

| Harness | Command |
|---|---|
| Claude Code | `claude plugin marketplace add <owner>/<repo>` then `claude plugin install <plugin>@<marketplace>`, for repositories that publish a plugin marketplace. |
| Gemini CLI | `gemini skills install <git-url>`, with `--path <subdir>` for one skill in a larger repository and `--scope workspace` for a project install. |
| Any | Copy or symlink the skill directory into the location in the first table. |
