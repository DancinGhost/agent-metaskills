import unittest

from helpers import SkillCase, load_script

meta = load_script("shared/skillmeta.py")


class SplitFrontmatter(unittest.TestCase):
    def test_splits_and_reports_body_line(self):
        front, body, line = meta.split_frontmatter("---\nname: a\n---\nBody\n")
        self.assertEqual(front, "name: a")
        self.assertEqual(body, "Body\n")
        self.assertEqual(line, 4)

    def test_missing_or_unterminated(self):
        self.assertIsNone(meta.split_frontmatter("# Title\n")[0])
        self.assertIsNone(meta.split_frontmatter("---\nname: a\nBody\n")[0])

    def test_crlf_line_endings_are_normalised(self):
        front, body, line = meta.split_frontmatter(
            "---\r\nname: demo\r\ndescription: >-\r\n  line one\r\n  line two\r\n---\r\nBody\r\n"
        )
        self.assertEqual(line, 7)
        self.assertNotIn("\r", front)
        self.assertNotIn("\r", body)
        data, problems = meta.parse_frontmatter(front)
        self.assertEqual(problems, [])
        self.assertEqual(data["name"], "demo")
        self.assertEqual(data["description"], "line one line two")

    def test_byte_order_mark_is_ignored(self):
        front, _, _ = meta.split_frontmatter("﻿---\nname: a\n---\n")
        self.assertEqual(front, "name: a")


class ParseFrontmatter(unittest.TestCase):
    def parse(self, text):
        return meta.parse_frontmatter(text)

    def test_plain_quoted_and_block_scalars(self):
        data, problems = self.parse(
            'name: demo\n'
            'a: "has: colon # and hash"\n'
            "b: 'it''s'\n"
            "folded: >-\n  one\n  two\n\n  three\n"
            "literal: |\n  x\n  y\n"
        )
        self.assertEqual(problems, [])
        self.assertEqual(data["name"], "demo")
        self.assertEqual(data["a"], "has: colon # and hash")
        self.assertEqual(data["b"], "it's")
        self.assertEqual(data["folded"], "one two\nthree")
        self.assertEqual(data["literal"], "x\ny")

    def test_maps_and_lists(self):
        data, problems = self.parse(
            'metadata:\n  author: me\n  version: "1.0"\n'
            "inline: [a, \"b\", c]\n"
            "indented:\n  - one\n  - two\n"
            "flush:\n- three\n- four\n"
            "allowed-tools: Bash(git:*) Read\n"
        )
        self.assertEqual(problems, [])
        self.assertEqual(data["metadata"], {"author": "me", "version": "1.0"})
        self.assertEqual(data["inline"], ["a", "b", "c"])
        self.assertEqual(data["indented"], ["one", "two"])
        self.assertEqual(data["flush"], ["three", "four"])
        self.assertEqual(data["allowed-tools"], "Bash(git:*) Read")

    def test_nested_structures_do_not_raise_problems(self):
        data, problems = self.parse(
            "hooks:\n  PreToolUse:\n    - matcher: Bash\n      hooks:\n"
            "        - type: command\n"
        )
        self.assertEqual(problems, [])
        self.assertIsInstance(data["hooks"], dict)

    def test_unquoted_colon_is_a_problem(self):
        data, problems = self.parse("description: Use when: something\n")
        self.assertEqual(data["description"], "Use when: something")
        self.assertEqual(len(problems), 1)
        self.assertIn("': '", problems[0][1])
        self.assertEqual(problems[0][0], 2)  # first frontmatter line

    def test_unquoted_hash_truncates_like_yaml(self):
        data, problems = self.parse("description: Triage issues tagged #bug today\n")
        self.assertEqual(data["description"], "Triage issues tagged")
        self.assertIn("comment", problems[0][1])

    def test_hash_without_leading_space_is_fine(self):
        data, problems = self.parse("description: Handles C# and issue#12\n")
        self.assertEqual(problems, [])
        self.assertEqual(data["description"], "Handles C# and issue#12")

    def test_other_problems(self):
        _, problems = self.parse("name: a\nname: b\n")
        self.assertIn("duplicate", problems[0][1])
        _, problems = self.parse("description: @mention first\n")
        self.assertIn("reserves", problems[0][1])
        _, problems = self.parse('description: "never closed\n')
        self.assertIn("never closed", problems[0][1])
        _, problems = self.parse("just some words\n")
        self.assertIn("cannot parse", problems[0][1])

    def test_multiline_plain_scalar_is_joined(self):
        data, problems = self.parse("description: first line\n  second line\n")
        self.assertEqual(problems, [])
        self.assertEqual(data["description"], "first line second line")


class Discovery(SkillCase):
    def test_find_single_and_nested(self):
        one = self.make_skill("one")
        two = self.make_skill("two", parent=self.tmp / "group")
        self.assertEqual(meta.find_skills(one), [one])
        self.assertEqual(meta.find_skills(self.tmp), sorted([two, one]))

    def test_hidden_and_trash_directories(self):
        self.make_skill("kept")
        hidden = self.make_skill("tucked", parent=self.tmp / ".claude" / "skills")
        self.make_skill("gone", parent=self.tmp / ".trash")
        names = [p.name for p in meta.find_skills(self.tmp)]
        self.assertEqual(sorted(names), ["kept", "tucked"])
        names = [p.name for p in meta.find_skills(self.tmp, include_hidden=False)]
        self.assertEqual(names, ["kept"])
        self.assertEqual(meta.find_skills(hidden), [hidden])

    def test_load_skill(self):
        skill = meta.load_skill(self.make_skill("demo"))
        self.assertTrue(skill.has_frontmatter)
        self.assertEqual(skill.name, "demo")
        self.assertTrue(skill.description.startswith("Converts CSV"))
        self.assertEqual(skill.problems, [])

    def test_strip_fenced_code_keeps_line_numbers(self):
        text = "a\n```bash\nrm -rf x\n```\nb\n~~~\ny\n~~~\nc"
        stripped = meta.strip_fenced_code(text)
        self.assertEqual(len(stripped.split("\n")), len(text.split("\n")))
        self.assertNotIn("rm -rf", stripped)
        self.assertEqual([l for l in stripped.split("\n") if l], ["a", "b", "c"])

    def test_extract_headings_and_slugs(self):
        md = "# Title\n```bash\n# not a heading\n```\n## 1. Check `SKILL.md`\n## 1. Check `SKILL.md`\n"
        headings = meta.extract_headings(md, start_line=10)
        self.assertEqual(
            headings,
            [
                {"level": 1, "title": "Title", "slug": "title", "line": 10},
                {"level": 2, "title": "1. Check `SKILL.md`", "slug": "1-check-skillmd", "line": 14},
                {"level": 2, "title": "1. Check `SKILL.md`", "slug": "1-check-skillmd-1", "line": 15},
            ],
        )

    def test_format_frontmatter_roundtrips_cleanly(self):
        raw = {
            "name": "demo",
            "description": "Converts CSV: tables and #tags. Use when asked.",
            "metadata": {"version": "1.0.0"},
        }
        rendered = meta.format_frontmatter(raw)
        parsed, problems = meta.parse_frontmatter(rendered)
        self.assertEqual(problems, [])
        self.assertEqual(parsed["name"], "demo")
        self.assertEqual(parsed["description"], raw["description"])
        self.assertEqual(parsed["metadata"]["version"], "1.0.0")

    def test_skill_digest_ignores_crlf_difference(self):
        one = self.make_skill("one", skill_md="---\nname: one\n---\nBody\n")
        two = self.make_skill("two", skill_md="---\r\nname: one\r\n---\r\nBody\r\n")
        self.assertEqual(meta.skill_digest(one), meta.skill_digest(two))


if __name__ == "__main__":
    unittest.main()
