import json
import unittest

from helpers import GOOD_BODY, GOOD_FRONTMATTER, SkillCase, load_script, run_main

tune = load_script("skills/skill-tune/scripts/eval_triggers.py")


class TuneCase(SkillCase):
    def write_evals(self, payload, name="evals.json"):
        path = self.tmp / name
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def valid_evals(self):
        cases = []
        for idx in range(8):
            cases.append(
                {
                    "query": f"convert csv export {idx} into a markdown table",
                    "should_trigger": True,
                    "holdout": idx >= 6,
                }
            )
        for idx in range(8):
            cases.append(
                {
                    "query": f"sort json rows {idx} by timestamp",
                    "should_trigger": False,
                    "holdout": idx >= 6,
                }
            )
        return {"skill": "csv-table", "method": "blind-judge", "cases": cases, "runs": []}


class ValidationAndCoverage(TuneCase):
    def test_valid_evals_and_coverage(self):
        skill = self.make_skill("csv-table")
        evals = self.write_evals(self.valid_evals())
        status, out, _ = run_main(tune, [str(skill), "--evals", str(evals), "--json"])
        self.assertEqual(status, 0, out)
        data = json.loads(out)
        self.assertEqual(data["errors"], [])
        self.assertEqual(data["warnings"], [])
        self.assertEqual(data["blind_spots"], [])
        self.assertEqual(data["stats"]["total_cases"], 16)

    def test_template_placeholders_fail_validation(self):
        skill = self.make_skill("csv-table")
        template = (
            tune.Path(__file__).resolve().parent.parent
            / "skills"
            / "skill-tune"
            / "assets"
            / "trigger-evals.template.json"
        )
        status, out, _ = run_main(tune, [str(skill), "--evals", str(template)])
        self.assertEqual(status, 1)
        self.assertIn("placeholder", out)

    def test_blind_spots_collision_risks_and_competitors(self):
        skill = self.make_skill("csv-table")
        comp_root = self.tmp / "other"
        self.make_skill(
            "tsv-converter",
            skill_md=(
                "---\nname: tsv-converter\n"
                "description: Converts TSV and tab-delimited dumps into Markdown tables. Use when converting TSV dumps.\n---\n"
                + GOOD_BODY
            ),
            parent=comp_root,
        )
        payload = {
            "skill": "csv-table",
            "cases": [
                {"query": "turn this tsv dump into a table", "should_trigger": True, "holdout": False},
                {"query": "reformat legacy ledger", "should_trigger": True, "holdout": False},
                {"query": "validate csv spreadsheet export columns", "should_trigger": False, "holdout": True},
            ],
        }
        evals = self.write_evals(payload)
        status, out, _ = run_main(
            tune, [str(skill), "--evals", str(evals), "--root", str(comp_root), "--json"]
        )
        self.assertEqual(status, 0)
        data = json.loads(out)
        self.assertEqual([b["query"] for b in data["blind_spots"]], ["reformat legacy ledger"])
        self.assertEqual(len(data["collision_risks"]), 1)
        self.assertEqual(data["competing_matches"][0]["competitor"], "tsv-converter")

    def test_candidate_description_override_and_runs_scoring(self):
        skill = self.make_skill("csv-table")
        payload = self.valid_evals()
        payload["runs"] = [
            {
                "description": "v1",
                "should_trigger_passed": 5,
                "should_trigger_total": 8,
                "should_not_trigger_passed": 8,
                "should_not_trigger_total": 8,
                "holdout_passed": True,
            },
            {
                "description": "v2",
                "should_trigger_passed": 7,
                "should_trigger_total": 8,
                "should_not_trigger_passed": 6,
                "should_not_trigger_total": 8,
                "holdout_passed": False,
            },
        ]
        evals = self.write_evals(payload)
        status, out, _ = run_main(
            tune,
            [
                str(skill),
                "--evals",
                str(evals),
                "--description",
                "Converts CSV exports into tables. Use when converting CSV files. Not for sorting JSON.",
                "--json",
            ],
        )
        self.assertEqual(status, 0)
        data = json.loads(out)
        self.assertTrue(data["has_boundary_clause"])
        self.assertEqual(len(data["runs"]), 2)
        self.assertTrue(data["runs"][1]["regressed_from_previous"])


if __name__ == "__main__":
    unittest.main()
