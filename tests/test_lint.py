import json
import unittest

from helpers import GOOD_BODY, GOOD_FRONTMATTER, SkillCase, load_script, run_main

lint = load_script("skills/skill-lint/scripts/lint_skill.py")


def skill_md(frontmatter: str, body: str = GOOD_BODY) -> str:
    return "---\n" + frontmatter.strip("\n") + "\n---\n" + body


GOOD_DESCRIPTION = (
    "description: Converts CSV exports into Markdown tables. Use when the "
    "user asks to turn a CSV file into a table.\n"
)


class LintCase(SkillCase):
    def codes(self, directory):
        return [f["code"] for f in lint.lint_skill(directory).findings]


class ValidSkill(LintCase):
    def test_clean_skill_has_no_findings(self):
        report = lint.lint_skill(self.make_skill())
        self.assertEqual(report.findings, [])
        self.assertGreater(report.budget["listing_tokens"], 0)
        self.assertGreater(report.budget["body_tokens"], 0)

    def test_linked_and_mentioned_files_are_not_orphans(self):
        body = GOOD_BODY + "\nSee [the rules](references/rules.md). Run `scripts/convert.py`.\n"
        directory = self.make_skill(
            skill_md=GOOD_FRONTMATTER.format(name="csv-table") + body,
            files={
                "references/rules.md": "# Rules\n",
                "scripts/convert.py": "import _shared\n",
                "scripts/_shared.py": "X = 1\n",
                "LICENSE.txt": "MIT\n",
            },
        )
        self.assertEqual(self.codes(directory), [])


class FrontmatterErrors(LintCase):
    def test_missing_skill_md(self):
        directory = self.tmp / "empty"
        directory.mkdir()
        self.assertEqual(self.codes(directory), ["E001"])

    def test_wrongly_cased_file_name(self):
        directory = self.tmp / "lower"
        directory.mkdir()
        (directory / "skill.md").write_text("x")
        report = lint.lint_skill(directory)
        self.assertEqual([f["code"] for f in report.findings], ["E001"])
        self.assertIn("rename", report.findings[0]["message"])

    def test_no_frontmatter(self):
        directory = self.make_skill(skill_md="# Title\n" + GOOD_BODY)
        self.assertIn("E002", self.codes(directory))

    def test_yaml_traps(self):
        directory = self.make_skill(
            skill_md=skill_md(
                "name: csv-table\n"
                "description: Converts CSV files. Use when: the user asks for a table of #data\n"
            )
        )
        report = lint.lint_skill(directory)
        yaml = [f for f in report.findings if f["code"] == "E003"]
        self.assertEqual(len(yaml), 2)
        self.assertEqual({f["line"] for f in yaml}, {3})

    def test_name_rules(self):
        cases = {
            "Bad_Name": "E011",
            "-lead": "E011",
            "double--hyphen": "E011",
            "x" * 65: "E011",
        }
        for name, code in cases.items():
            with self.subTest(name=name):
                directory = self.make_skill(
                    name=name, skill_md=skill_md(f"name: {name}\n" + GOOD_DESCRIPTION)
                )
                self.assertIn(code, self.codes(directory))

    def test_name_must_match_directory(self):
        directory = self.make_skill(
            name="actual-dir", skill_md=skill_md("name: other-name\n" + GOOD_DESCRIPTION)
        )
        self.assertEqual(self.codes(directory), ["E012"])

    def test_missing_name_and_description(self):
        directory = self.make_skill(skill_md=skill_md("license: MIT\n"))
        self.assertEqual(self.codes(directory), ["E010", "E020"])

    def test_length_limits(self):
        directory = self.make_skill(
            skill_md=skill_md(
                "name: csv-table\n"
                "description: Use when converting. " + "x" * 1024 + "\n"
                "compatibility: " + "y" * 501 + "\n"
            )
        )
        codes = self.codes(directory)
        self.assertIn("E021", codes)
        self.assertIn("E030", codes)

    def test_metadata_must_be_flat_strings(self):
        directory = self.make_skill(
            skill_md=skill_md(
                "name: csv-table\n" + GOOD_DESCRIPTION + "metadata:\n  nested:\n    deep: x\n"
            )
        )
        self.assertEqual(self.codes(directory), ["E031"])


class Warnings(LintCase):
    def test_unknown_and_extension_fields(self):
        directory = self.make_skill(
            skill_md=skill_md(
                "name: csv-table\n" + GOOD_DESCRIPTION + "version: 2\ncontext: fork\n"
            )
        )
        self.assertEqual(sorted(self.codes(directory)), ["I001", "W001"])

    def test_description_quality(self):
        cases = {
            "description: Helps with PDFs.\n": "W010",
            "description: Converts CSV exports into tidy Markdown tables with aligned columns.\n": "W010",
            "description: I can convert CSV files. Use when the user asks for a table.\n": "W011",
            "description: Converts <b>CSV</b> files. Use when the user asks for a table.\n": "W012",
        }
        for description, code in cases.items():
            with self.subTest(description=description):
                directory = self.make_skill(skill_md=skill_md("name: csv-table\n" + description))
                self.assertEqual(self.codes(directory), [code])

    def test_reserved_word_in_name(self):
        directory = self.make_skill(
            name="claude-helper", skill_md=skill_md("name: claude-helper\n" + GOOD_DESCRIPTION)
        )
        self.assertEqual(self.codes(directory), ["W013"])

    def test_body_size(self):
        long_body = "\n".join(f"Step {n}: do the next thing carefully." for n in range(600))
        directory = self.make_skill(skill_md=skill_md("name: csv-table\n" + GOOD_DESCRIPTION, long_body))
        codes = self.codes(directory)
        self.assertIn("W020", codes)
        self.assertIn("W021", codes)
        directory = self.make_skill(
            name="tiny", skill_md=skill_md("name: tiny\n" + GOOD_DESCRIPTION, "\nDo it.\n")
        )
        self.assertEqual(self.codes(directory), ["W022"])

    def test_references(self):
        body = GOOD_BODY + (
            "\nRead [the guide](references/missing.md) and [docs](https://example.com/x.md)."
            "\nThen run scripts/nope.py and see [outside](../other/file.md)."
            "\nA placeholder such as references/<topic>.md is fine.\n"
        )
        (self.tmp / "other").mkdir()
        (self.tmp / "other" / "file.md").write_text("x")
        directory = self.make_skill(
            skill_md=GOOD_FRONTMATTER.format(name="csv-table") + body,
            files={"references/orphan.md": "never mentioned\n"},
        )
        report = lint.lint_skill(directory)
        by_code = {f["code"]: f for f in report.findings}
        self.assertEqual(sorted(by_code), ["E040", "W030", "W041", "W042"])
        self.assertEqual(by_code["W030"]["file"], "references/orphan.md")
        self.assertIn("missing.md", by_code["E040"]["message"])

    def test_links_inside_code_fences_are_ignored(self):
        body = GOOD_BODY + "\n```markdown\nSee [x](references/example.md)\n```\n"
        directory = self.make_skill(skill_md=GOOD_FRONTMATTER.format(name="csv-table") + body)
        self.assertEqual(self.codes(directory), [])

    def test_machine_paths_placeholders_and_shebang(self):
        body = GOOD_BODY + "\nTODO finish this. Output goes to /home/alex/out/ and uses scripts/run.sh.\n"
        directory = self.make_skill(
            skill_md=GOOD_FRONTMATTER.format(name="csv-table") + body,
            files={"scripts/run.sh": "echo hi\n"},
        )
        self.assertEqual(sorted(self.codes(directory)), ["W040", "W050", "W060"])

    def test_anchor_and_reference_file_links(self):
        body = GOOD_BODY + (
            "\nSee [good](#csv-to-table), [bad](#missing-section), "
            "[ref](references/guide.md#details) and [bad ref](references/guide.md#nope).\n"
            "\n[def-link]: references/missing-def.md\n"
        )
        directory = self.make_skill(
            skill_md=GOOD_FRONTMATTER.format(name="csv-table") + body,
            files={"references/guide.md": "# Guide\n\n## Details\n\nSee [broken](nowhere.md).\n"},
        )
        report = lint.lint_skill(directory)
        e040 = [f for f in report.findings if f["code"] == "E040"]
        self.assertEqual(len(e040), 4)

    def test_crlf_in_script_raises_w043(self):
        body = GOOD_BODY + "\nRun `scripts/run.sh`.\n"
        directory = self.make_skill(
            skill_md=GOOD_FRONTMATTER.format(name="csv-table") + body,
            files={"scripts/run.sh": b"#!/bin/sh\r\necho hi\r\n"},
        )
        self.assertEqual(self.codes(directory), ["W043"])

    def test_fix_repairs_mechanical_errors(self):
        directory = self.tmp / "fix-me"
        directory.mkdir()
        (directory / "skill.md").write_bytes(
            (
                "---\r\n"
                "name: wrong-name\r\n"
                "description: Converts CSV: exports into tables. Use when the user asks for a table.\r\n"
                "allowed-tools:\r\n  - Read\r\n  - Bash\r\n"
                "---\r\n"
                + GOOD_BODY
                + "\nRun `scripts/run.sh`.\n"
            ).encode("utf-8")
        )
        (directory / "scripts").mkdir()
        (directory / "scripts" / "run.sh").write_bytes(b"echo ok\r\n")
        status, out, _ = run_main(lint, [str(directory), "--fix", "--strict"])
        self.assertEqual(status, 0, out)
        self.assertIn("fixed", out)


class CommandLine(LintCase):
    def test_exit_status_and_strict(self):
        good = self.make_skill("good")
        warn = self.make_skill(
            "warn", skill_md=skill_md("name: warn\ndescription: Helps with PDFs.\n")
        )
        bad = self.make_skill("bad", skill_md="no frontmatter\n" + GOOD_BODY)
        self.assertEqual(run_main(lint, [str(good), "--strict"])[0], 0)
        self.assertEqual(run_main(lint, [str(warn)])[0], 0)
        self.assertEqual(run_main(lint, [str(warn), "--strict"])[0], 1)
        self.assertEqual(run_main(lint, [str(bad)])[0], 1)
        self.assertEqual(run_main(lint, [str(self.tmp / "nowhere")])[0], 2)

    def test_scans_a_directory_of_skills_and_emits_json(self):
        self.make_skill("one")
        self.make_skill("two", skill_md="no frontmatter\n" + GOOD_BODY)
        status, out, _ = run_main(lint, [str(self.tmp), "--json"])
        data = json.loads(out)
        self.assertEqual(status, 1)
        self.assertEqual(len(data["skills"]), 2)
        self.assertEqual(data["errors"], 1)

    def test_directory_without_skills_reports_missing_file(self):
        (self.tmp / "empty").mkdir()
        status, out, _ = run_main(lint, [str(self.tmp / "empty")])
        self.assertEqual(status, 1)
        self.assertIn("E001", out)


if __name__ == "__main__":
    unittest.main()
