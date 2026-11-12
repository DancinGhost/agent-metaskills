import json
import unittest

from helpers import GOOD_BODY, SkillCase, load_script, run_main

inventory = load_script("skills/skill-inventory/scripts/inventory.py")


def md(name, description):
    return f"---\nname: {name}\ndescription: >-\n  {description}\n---\n{GOOD_BODY}"


class Analysis(SkillCase):
    def setUp(self):
        super().setUp()
        self.project = self.tmp / "project"
        claude = self.project / ".claude" / "skills"
        agents = self.project / ".agents" / "skills"
        self.make_skill("pdf-forms", md("pdf-forms", "Fills PDF forms and extracts fields from PDF documents. Use when the user asks to fill a PDF form."), parent=claude)
        self.make_skill("pdf-extract", md("pdf-extract", "Extracts form fields and text from PDF documents. Use when the user asks to extract fields from a PDF form."), parent=claude)
        self.make_skill("release-notes", md("release-notes", "Drafts release notes from merged pull requests. Use when cutting a release."), parent=claude)
        self.make_skill("release-notes", md("release-notes", "Writes a changelog. Use when tagging a version."), parent=agents)
        self.make_skill("broken", "# no frontmatter\n", parent=agents)
        self.make_skill("old", md("old", "Trashed skill. Use when never."), parent=claude / ".trash")

    def run_json(self, *extra):
        status, out, _ = run_main(
            inventory, ["--project", str(self.project), "--no-user", "--json", *extra]
        )
        self.assertEqual(status, 0)
        return json.loads(out)

    def test_lists_project_skills_and_skips_trash(self):
        data = self.run_json()
        names = sorted(s["name"] for s in data["skills"])
        self.assertEqual(names, ["broken", "pdf-extract", "pdf-forms", "release-notes", "release-notes"])
        self.assertTrue(all(s["listing_tokens"] > 0 for s in data["skills"]))

    def test_duplicates(self):
        duplicates = self.run_json()["duplicates"]
        self.assertEqual([d["name"] for d in duplicates], ["release-notes"])
        self.assertEqual(len(duplicates[0]["paths"]), 2)

    def test_broken_skills(self):
        broken = self.run_json()["broken"]
        self.assertEqual([b["name"] for b in broken], ["broken"])
        self.assertEqual(broken[0]["problems"], ["no frontmatter"])

    def test_overlap_respects_threshold(self):
        overlaps = self.run_json()["overlaps"]
        self.assertEqual([{o["a"], o["b"]} for o in overlaps], [{"pdf-forms", "pdf-extract"}])
        self.assertIn("pdf", overlaps[0]["shared"])
        self.assertEqual(self.run_json("--threshold", "0.95")["overlaps"], [])

    def test_cost_totals(self):
        data = self.run_json()
        self.assertEqual(
            data["total_listing_tokens"], sum(s["listing_tokens"] for s in data["skills"])
        )
        self.assertEqual(sum(v["skills"] for v in data["by_location"].values()), 5)

    def test_extra_root_and_text_output(self):
        extra = self.tmp / "elsewhere"
        self.make_skill("lonely", md("lonely", "Counts words in a text file. Use when asked for a word count."), parent=extra)
        status, out, _ = run_main(
            inventory, ["--project", str(self.project), "--no-user", "--root", str(extra)]
        )
        self.assertEqual(status, 0)
        self.assertIn("lonely", out)
        self.assertIn("Same name in more than one place", out)
        self.assertIn("Searched:", out)

    def test_empty_project(self):
        status, out, _ = run_main(inventory, ["--project", str(self.tmp / "none"), "--no-user"])
        self.assertEqual(status, 0)
        self.assertIn("No skills found.", out)


class Keywords(unittest.TestCase):
    def test_stopwords_and_stemming(self):
        words = inventory.keywords("Use when the user asks for extracting tables from PDFs")
        self.assertEqual(words, {"extract", "table", "pdf"})

    def test_similarity(self):
        self.assertEqual(inventory.similarity(set(), {"a"}), 0.0)
        self.assertEqual(inventory.similarity({"a", "b"}, {"a", "b"}), 1.0)
        self.assertAlmostEqual(inventory.similarity({"a", "b"}, {"b", "c"}), 1 / 3)


if __name__ == "__main__":
    unittest.main()
