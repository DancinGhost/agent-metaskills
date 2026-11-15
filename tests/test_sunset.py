import json
import unittest

from helpers import GOOD_BODY, SkillCase, load_script, run_main

sunset = load_script("skills/skill-sunset/scripts/usage_report.py")


def md(name, description):
    return f"---\nname: {name}\ndescription: >-\n  {description}\n---\n{GOOD_BODY}"


class SunsetCase(SkillCase):
    def test_identifies_active_and_dormant_skills_without_system_prompt_false_positives(self):
        project = self.tmp / "project"
        skills_dir = project / ".agents" / "skills"
        self.make_skill("used-by-read", md("used-by-read", "Used by reading SKILL.md. Use when asked."), parent=skills_dir)
        self.make_skill("used-by-script", md("used-by-script", "Used by running its script. Use when asked."), parent=skills_dir)
        self.make_skill("used-by-slash", md("used-by-slash", "Used by slash command. Use when asked."), parent=skills_dir)
        self.make_skill("never-used", md("never-used", "Never activated anywhere. Use when asked."), parent=skills_dir)

        logs_dir = self.tmp / "logs"
        logs_dir.mkdir()
        # Session 1: passive system-prompt listing mentions never-used, plus real activations
        (logs_dir / "session1.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "SYSTEM",
                            "content": "Available skills:\n- never-used (/path/to/never-used/SKILL.md): Never activated.",
                        }
                    ),
                    json.dumps(
                        {
                            "type": "PLANNER_RESPONSE",
                            "tool_calls": [{"name": "read_file", "args": {"Path": "/x/used-by-read/SKILL.md"}}],
                        }
                    ),
                    json.dumps(
                        {
                            "type": "PLANNER_RESPONSE",
                            "tool_calls": [{"name": "run_command", "args": {"CommandLine": "python3 skills/used-by-script/scripts/run.py"}}],
                        }
                    ),
                ]
            ),
            encoding="utf-8",
        )
        # Session 2: slash command
        (logs_dir / "session2.jsonl").write_text(
            json.dumps({"type": "USER_INPUT", "content": "please run /used-by-slash on this repo"}),
            encoding="utf-8",
        )

        status, out, _ = run_main(
            sunset,
            ["--project", str(project), "--logs", str(logs_dir), "--no-user", "--days", "0", "--json"],
        )
        self.assertEqual(status, 0, out)
        data = json.loads(out)
        self.assertEqual(data["sessions_scanned"], 2)
        active_names = sorted(s["name"] for s in data["active"])
        dormant_names = [s["name"] for s in data["dormant"]]
        self.assertEqual(active_names, ["used-by-read", "used-by-script", "used-by-slash"])
        self.assertEqual(dormant_names, ["never-used"])
        self.assertGreater(data["dormant_listing_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
