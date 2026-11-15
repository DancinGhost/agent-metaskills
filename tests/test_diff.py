import json
import unittest

from helpers import GOOD_BODY, GOOD_FRONTMATTER, SkillCase, load_script, run_main

diff = load_script("skills/skill-diff/scripts/diff_skill.py")


class DiffCase(SkillCase):
    def test_identical_skills_report_no_changes(self):
        one = self.make_skill("demo", parent=self.tmp / "v1")
        two = self.make_skill("demo", parent=self.tmp / "v2")
        status, out, _ = run_main(diff, [str(one), str(two)])
        self.assertEqual(status, 0)
        self.assertIn("no changes", out)

    def test_detects_trigger_section_file_and_host_changes(self):
        old = self.make_skill(
            "demo",
            skill_md=(
                GOOD_FRONTMATTER.format(name="demo")
                + GOOD_BODY
                + "\n## Old section\n\nSee https://old.example.com.\n"
            ),
            files={"references/old.md": "old\n", "scripts/keep.py": "x = 1\n"},
            parent=self.tmp / "v1",
        )
        new = self.make_skill(
            "demo",
            skill_md=(
                "---\nname: demo\nlicense: MIT\n"
                "description: >-\n  Converts CSV and TSV exports into Markdown tables and charts. "
                "Use when the user asks to turn a CSV or TSV file into a table.\n---\n"
                + GOOD_BODY
                + "\n## New section\n\nSee https://new.example.com/api.\n"
            ),
            files={"references/new.md": "new\n", "scripts/keep.py": "x = 2\n"},
            parent=self.tmp / "v2",
        )
        status, out, _ = run_main(diff, [str(old), str(new), "--json"])
        self.assertEqual(status, 0)
        data = json.loads(out)
        self.assertFalse(data["identical"])
        self.assertEqual(data["frontmatter"]["added"], ["license"])
        self.assertIn("tsv", data["trigger"]["keywords_added"])
        self.assertEqual(data["headings"]["added"], ["New section"])
        self.assertEqual(data["headings"]["removed"], ["Old section"])
        self.assertEqual(data["files"]["added"], ["references/new.md"])
        self.assertEqual(data["files"]["removed"], ["references/old.md"])
        self.assertIn("scripts/keep.py", data["files"]["modified"])
        self.assertEqual(data["hosts"]["added"], ["new.example.com"])
        self.assertEqual(data["hosts"]["removed"], ["old.example.com"])

    def test_new_spec_errors_exit_non_zero(self):
        old = self.make_skill("demo", parent=self.tmp / "v1")
        new = self.make_skill("demo", skill_md="# Missing frontmatter\n", parent=self.tmp / "v2")
        status, out, _ = run_main(diff, [str(old), str(new)])
        self.assertEqual(status, 1)
        self.assertIn("missing YAML frontmatter", out)


if __name__ == "__main__":
    unittest.main()
