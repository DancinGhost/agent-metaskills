import json
import zipfile
import unittest

from helpers import GOOD_BODY, SkillCase, load_script, run_main

pack = load_script("skills/skill-pack/scripts/pack_skill.py")
lint = load_script("skills/skill-lint/scripts/lint_skill.py")


class PackCase(SkillCase):
    def make_claude_skill(self, name="csv-table"):
        md = (
            "---\r\n"
            f"name: {name}\r\n"
            "description: Converts CSV exports: into Markdown tables.\r\n"
            "when_to_use: Use when the user asks to convert a CSV file.\r\n"
            "context: fork\r\n"
            "allowed-tools:\r\n  - Read\r\n  - Bash\r\n"
            "---\r\n"
            + GOOD_BODY
        )
        return self.make_skill(
            name,
            skill_md=md,
            files={".DS_Store": b"junk", "scripts/cache.pyc": b"123"},
        )

    def test_pack_spec_dir_strips_extensions_and_passes_strict_lint(self):
        src = self.make_claude_skill()
        out_dir = self.tmp / "dist"
        status, out, _ = run_main(
            pack, [str(src), "--output", str(out_dir), "--format", "spec-dir", "--json"]
        )
        self.assertEqual(status, 0, out)
        packed = out_dir / "csv-table"
        self.assertTrue((packed / "SKILL.md").is_file())
        self.assertFalse((packed / ".DS_Store").exists())
        self.assertFalse((packed / "scripts" / "cache.pyc").exists())
        report = lint.lint_skill(packed)
        self.assertEqual(report.findings, [])
        loaded = pack.meta.load_skill(packed)
        self.assertIn("Use when the user asks to convert a CSV file.", loaded.description)
        text = (packed / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("context:", text)
        self.assertNotIn("when_to_use:", text)

    def test_pack_zip_is_reproducible_and_clean(self):
        src = self.make_claude_skill()
        zip_path = self.tmp / "csv-table.zip"
        status, _, _ = run_main(
            pack, [str(src), "--output", str(zip_path), "--format", "zip"]
        )
        self.assertEqual(status, 0)
        with zipfile.ZipFile(zip_path) as zf:
            self.assertEqual(zf.namelist(), ["csv-table/SKILL.md"])

    def test_pack_plugin_writes_manifests(self):
        src = self.make_claude_skill()
        plugin_dir = self.tmp / "my-plugin"
        status, _, _ = run_main(
            pack,
            [str(src), "--output", str(plugin_dir), "--format", "plugin", "--plugin-name", "csv-suite"],
        )
        self.assertEqual(status, 0)
        manifest = json.loads((plugin_dir / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(manifest["name"], "csv-suite")
        self.assertTrue((plugin_dir / "skills" / "csv-table" / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
