import json
import unittest

from helpers import GOOD_FRONTMATTER, SkillCase, load_script, run_main

split = load_script("skills/skill-split/scripts/plan_split.py")


class SplitCase(SkillCase):
    def test_compact_skill_needs_no_extractions(self):
        skill = self.make_skill("compact")
        status, out, _ = run_main(split, [str(skill)])
        self.assertEqual(status, 0)
        self.assertIn("already compact", out)

    def test_classifies_script_and_reference_sections(self):
        code_lines = "\n".join(f"print('step {i}')" for i in range(25))
        table_rows = "\n".join(f"| E{i:03d} | Rule {i} | Fix {i} |" for i in range(15))
        body = (
            "\n# Big skill\n\n"
            "## 1. Procedure\n\nRun the steps in order and verify.\n\n"
            f"## 2. Helper script\n\n```python\n{code_lines}\n```\n\n"
            f"## 3. Error reference table\n\n| Code | Rule | Fix |\n|---|---|---|\n{table_rows}\n"
        )
        skill = self.make_skill(
            "big-skill", skill_md=GOOD_FRONTMATTER.format(name="big-skill") + body
        )
        status, out, _ = run_main(split, [str(skill), "--json"])
        self.assertEqual(status, 0)
        data = json.loads(out)
        by_title = {s["title"]: s for s in data["sections"]}
        self.assertEqual(by_title["1. Procedure"]["action"], "keep-inline")
        self.assertEqual(by_title["2. Helper script"]["action"], "extract-script")
        self.assertEqual(by_title["2. Helper script"]["target"], "scripts/helper_script.py")
        self.assertEqual(by_title["3. Error reference table"]["action"], "extract-reference")
        self.assertEqual(
            by_title["3. Error reference table"]["target"],
            "references/error-reference-table.md",
        )
        self.assertLess(data["projected"]["body_lines"], data["current"]["body_lines"])


if __name__ == "__main__":
    unittest.main()
