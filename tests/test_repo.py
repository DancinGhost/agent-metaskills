"""Checks on this repository itself: the skills must pass their own tools."""

import json
import subprocess
import sys
import unittest

from helpers import ROOT, load_script, run_main

lint = load_script("skills/skill-lint/scripts/lint_skill.py")
port = load_script("skills/skill-port/scripts/portability_check.py")
meta = load_script("shared/skillmeta.py")

SKILLS = sorted(p.parent for p in (ROOT / "skills").glob("*/SKILL.md"))
SCRIPTS = sorted(
    p for p in (ROOT / "skills").glob("*/scripts/*.py") if not p.name.startswith("_")
)


class Repository(unittest.TestCase):
    def test_there_are_skills(self):
        self.assertGreaterEqual(len(SKILLS), 7)

    def test_vendored_helpers_match_the_canonical_copy(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "sync_shared.py"), "--check"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_every_skill_passes_strict_lint(self):
        for skill in SKILLS:
            with self.subTest(skill=skill.name):
                report = lint.lint_skill(skill)
                problems = [f for f in report.findings if f["level"] != "info"]
                self.assertEqual(problems, [])

    def test_no_skill_depends_on_one_harness(self):
        for skill in SKILLS:
            with self.subTest(skill=skill.name):
                breaks = [f for f in port.check_skill(skill).findings if f["level"] == "breaks"]
                self.assertEqual(breaks, [])

    def test_skills_use_only_specification_fields(self):
        for skill in SKILLS:
            with self.subTest(skill=skill.name):
                fields = set(meta.load_skill(skill).frontmatter)
                self.assertLessEqual(fields, set(meta.SPEC_FIELDS))

    def test_scripts_run_standalone_and_leave_no_bytecode(self):
        for script in SCRIPTS:
            with self.subTest(script=script.name):
                result = subprocess.run(
                    [sys.executable, str(script), "--help"], capture_output=True, text=True
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout)
                self.assertFalse((script.parent / "__pycache__").exists())

    def test_plugin_manifests(self):
        plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
        market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
        self.assertEqual(plugin["name"], "agent-metaskills")
        self.assertEqual([p["name"] for p in market["plugins"]], [plugin["name"]])
        self.assertEqual(market["plugins"][0]["source"], "./")

    def test_readme_lists_every_skill(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for skill in SKILLS:
            with self.subTest(skill=skill.name):
                self.assertIn(f"skills/{skill.name}/", readme)

    def test_command_line_lint_of_the_repository_is_clean(self):
        status, out, _ = run_main(lint, [str(ROOT / "skills"), "--strict"])
        self.assertEqual(status, 0, out)


if __name__ == "__main__":
    unittest.main()
