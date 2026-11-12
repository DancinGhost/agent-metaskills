import json
import unittest

from helpers import GOOD_BODY, GOOD_FRONTMATTER, SkillCase, load_script, run_main

port = load_script("skills/skill-port/scripts/portability_check.py")

HEADER = GOOD_FRONTMATTER.format(name="csv-table")


class PortCase(SkillCase):
    def check(self, extra="", header=HEADER, files=None):
        directory = self.make_skill(skill_md=header + GOOD_BODY + "\n" + extra + "\n", files=files)
        return port.check_skill(directory)

    def messages(self, check, level):
        return [f["message"] for f in check.findings if f["level"] == level]


class Portable(PortCase):
    def test_plain_skill_is_portable(self):
        check = self.check()
        self.assertEqual(check.findings, [])
        status, out, _ = run_main(port, [str(check.skill_dir)])
        self.assertEqual(status, 0)
        self.assertIn("portable", out)

    def test_ordinary_words_are_not_tool_references(self):
        check = self.check(
            "Read the file, then edit the table. Write the result and search for gaps.\n"
            "Make the change only if the task needs it, and use the shell when it helps.\n"
            "It costs $5 per run.\n"
        )
        self.assertEqual(check.findings, [])


class ClaudeCodeFeatures(PortCase):
    def test_frontmatter_extensions(self):
        header = (
            "---\nname: csv-table\ndescription: Converts CSV. Use when asked.\n"
            "when_to_use: on csv requests\ncontext: fork\nargument-hint: \"[file]\"\n"
            "allowed-tools: Read\nowner: me\n---\n"
        )
        check = self.check(header=header)
        breaks = " ".join(self.messages(check, port.BREAKS))
        adapt = " ".join(self.messages(check, port.ADAPT))
        self.assertIn("'when_to_use'", breaks)
        self.assertIn("'context'", breaks)
        self.assertIn("'argument-hint'", adapt)
        self.assertIn("'allowed-tools'", adapt)
        self.assertIn("'owner' is not in the Agent Skills specification", adapt)

    def test_substitutions(self):
        check = self.check("Convert $ARGUMENTS with ${CLAUDE_SKILL_DIR}/scripts/x.py, sheet $1.")
        breaks = self.messages(check, port.BREAKS)
        self.assertEqual(len(breaks), 3)
        for token in ("$ARGUMENTS", "${CLAUDE_SKILL_DIR}", "$1"):
            self.assertTrue(any(m.startswith(token + " ") for m in breaks), token)

    def test_load_time_injection(self):
        inline = self.check("- Status: !`git status --short`")
        self.assertEqual(len(self.messages(inline, port.BREAKS)), 1)
        block = self.check("```!\nnode --version\n```")
        self.assertEqual(len(self.messages(block, port.BREAKS)), 1)

    def test_tool_names_paths_and_mcp(self):
        check = self.check(
            "Use the Bash tool, then call `AskUserQuestion`. On Gemini use run_shell_command.\n"
            "Call mcp__github__create_issue and record it in CLAUDE.md under ~/.claude/skills/x.\n"
            "Finish with /compact.\n"
        )
        adapt = " ".join(self.messages(check, port.ADAPT))
        for expected in ("'Bash'", "'AskUserQuestion'", "'run_shell_command'", "mcp__github__create_issue", "'CLAUDE.md'", "'~/.claude/skills/x'"):
            self.assertIn(expected, adapt)
        self.assertIn("/compact", " ".join(self.messages(check, port.NOTE)))
        self.assertEqual(self.messages(check, port.BREAKS), [])

    def test_each_tool_is_reported_once(self):
        check = self.check("Use the Bash tool.\nUse the Bash tool again.\n")
        self.assertEqual(len(self.messages(check, port.ADAPT)), 1)


class Runtime(PortCase):
    def test_undeclared_requirements(self):
        check = self.check(
            "Make the edits by hand.\n\n```bash\njq '.items' data.json\npython3 scripts/run.py\n```\n",
            files={"scripts/run.py": "print(1)\n", "scripts/go.sh": "#!/bin/sh\n"},
        )
        notes = self.messages(check, port.NOTE)
        self.assertEqual(len(notes), 2)
        self.assertIn("needs a POSIX shell, jq, python3", notes[0])
        self.assertNotIn("make", notes[0])
        self.assertIn("Windows", notes[1])

    def test_declared_requirements_are_quiet(self):
        header = HEADER.replace("---\n", "---\ncompatibility: Requires python3 and jq.\n", 1)
        check = self.check(
            "```bash\njq . x.json\n```\n", header=header, files={"scripts/run.py": "print(1)\n"}
        )
        self.assertEqual(check.findings, [])


class CommandLine(PortCase):
    def test_exit_status_and_json(self):
        breaking = self.make_skill("breaking", skill_md=GOOD_FRONTMATTER.format(name="breaking") + GOOD_BODY + "\nUse $ARGUMENTS.\n")
        status, out, _ = run_main(port, [str(breaking), "--json"])
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(out)[0]["findings"][0]["level"], "breaks")
        self.assertEqual(run_main(port, [str(self.tmp / "nowhere")])[0], 2)

    def test_missing_skill_md(self):
        (self.tmp / "empty").mkdir()
        status, out, _ = run_main(port, [str(self.tmp / "empty")])
        self.assertEqual(status, 1)
        self.assertIn("no SKILL.md", out)


if __name__ == "__main__":
    unittest.main()
