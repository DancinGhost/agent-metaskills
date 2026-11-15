#!/usr/bin/env python3
"""Validate trigger evaluation sets and score descriptions for an Agent Skill.

    python3 eval_triggers.py SKILL_DIR [--evals FILE] [--description TEXT]
                             [--root DIR ...] [--json]

Checks a trigger-evals JSON file for balance, holdout coverage and leftover
template text, then tests each query's lexical overlap against the skill's
description (and optional competing skills) and scores recorded runs.
Exit status is 1 when validation errors are found, 2 on usage errors, and
0 otherwise. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # keep the skill directory free of __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _skillmeta as meta  # noqa: E402

MIN_RECOMMENDED_CASES = 16
BOUNDARY_RE = re.compile(
    r"\b(not for|do not use|don't use|never use for|"
    r"use [a-z0-9-]+ (?:for|when|if|instead)|instead use)\b",
    re.IGNORECASE,
)


def _is_placeholder(text: str) -> bool:
    return bool(re.search(r"\bREPLACE\b", str(text)))


def validate_evals(data: dict) -> tuple[list, list, dict]:
    """Return (errors, warnings, stats) for a parsed trigger-evals dict."""
    errors, warnings = [], []
    if not isinstance(data, dict):
        return ["root of evals file must be a JSON object"], [], {}

    skill_name = data.get("skill", "")
    if not isinstance(skill_name, str) or not skill_name.strip():
        errors.append("missing 'skill' name")
    elif _is_placeholder(skill_name):
        errors.append(f"'skill' still has template placeholder {skill_name!r}")

    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append("'cases' must be a non-empty list")
        return errors, warnings, {}

    positives = negatives = holdouts = pos_holdouts = neg_holdouts = 0
    for idx, case in enumerate(cases, 1):
        if not isinstance(case, dict):
            errors.append(f"case {idx}: must be an object")
            continue
        query = case.get("query")
        if not isinstance(query, str) or not query.strip():
            errors.append(f"case {idx}: missing non-empty 'query'")
        elif _is_placeholder(query):
            errors.append(f"case {idx}: 'query' still has template placeholder")
        should = case.get("should_trigger")
        if not isinstance(should, bool):
            errors.append(f"case {idx}: 'should_trigger' must be true or false")
            continue
        holdout = bool(case.get("holdout", False))
        if should:
            positives += 1
            if holdout:
                pos_holdouts += 1
        else:
            negatives += 1
            if holdout:
                neg_holdouts += 1
        if holdout:
            holdouts += 1

    total = positives + negatives
    if total < MIN_RECOMMENDED_CASES:
        warnings.append(
            f"only {total} case(s); {MIN_RECOMMENDED_CASES}-20 is recommended "
            "so both halves and the holdout have enough coverage"
        )
    if positives == 0 or negatives == 0:
        warnings.append(
            "both should_trigger=true and should_trigger=false cases are needed"
        )
    if holdouts == 0:
        warnings.append(
            "no cases have holdout=true; set aside about a quarter of each "
            "half to detect descriptions over-fitted to the working set"
        )
    elif pos_holdouts == 0 or neg_holdouts == 0:
        warnings.append(
            "holdout only covers one half; include both positive and negative "
            "holdout cases"
        )

    stats = {
        "total_cases": total,
        "should_trigger": positives,
        "should_not_trigger": negatives,
        "holdout_cases": holdouts,
    }
    return errors, warnings, stats


def score_runs(runs: list) -> list:
    """Summarize recorded runs with recall, specificity and regression flags."""
    scored = []
    if not isinstance(runs, list):
        return scored
    for idx, run in enumerate(runs):
        if not isinstance(run, dict):
            continue
        desc = str(run.get("description", ""))
        if _is_placeholder(desc) and run.get("should_trigger_total", 0) == 0:
            continue
        pos_pass = int(run.get("should_trigger_passed", 0) or 0)
        pos_total = int(run.get("should_trigger_total", 0) or 0)
        neg_pass = int(run.get("should_not_trigger_passed", 0) or 0)
        neg_total = int(run.get("should_not_trigger_total", 0) or 0)
        recall = round(pos_pass / pos_total, 3) if pos_total else None
        specificity = round(neg_pass / neg_total, 3) if neg_total else None
        entry = {
            "round": idx + 1,
            "description": desc,
            "should_trigger": f"{pos_pass}/{pos_total}",
            "should_not_trigger": f"{neg_pass}/{neg_total}",
            "recall": recall,
            "specificity": specificity,
            "holdout_passed": run.get("holdout_passed"),
            "failures": run.get("failures", []),
        }
        if scored:
            prev = scored[-1]
            regressed = (
                (recall is not None and prev["recall"] is not None and recall < prev["recall"])
                or (
                    specificity is not None
                    and prev["specificity"] is not None
                    and specificity < prev["specificity"]
                )
            )
            entry["regressed_from_previous"] = regressed
        scored.append(entry)
    return scored


def evaluate_skill(
    skill_dir: Path,
    evals_data: dict | None = None,
    description_override: str | None = None,
    extra_roots: list | None = None,
) -> dict:
    skill = meta.load_skill(skill_dir)
    errors, warnings = [], []
    if not skill.skill_md.is_file():
        errors.append(f"no SKILL.md in {skill_dir}")
    name = skill.name or skill_dir.name
    description = (
        description_override if description_override is not None else skill.description
    )
    if not description.strip():
        errors.append("skill has no description")

    target_words = meta.keywords(name.replace("-", " ") + " " + description)
    has_boundary = bool(BOUNDARY_RE.search(description))

    competitors = []
    for root in extra_roots or []:
        for other_dir in meta.find_skills(root, include_hidden=False):
            if other_dir.resolve() == Path(skill_dir).resolve():
                continue
            other = meta.load_skill(other_dir)
            other_name = other.name or other_dir.name
            if other_name == name:
                continue
            words = meta.keywords(other_name.replace("-", " ") + " " + other.description)
            competitors.append((other_name, words))

    blind_spots = []
    collision_risks = []
    competing_matches = []
    stats = {}
    runs = []

    if evals_data is not None:
        ev_errors, ev_warnings, stats = validate_evals(evals_data)
        errors.extend(ev_errors)
        warnings.extend(ev_warnings)
        if (
            isinstance(evals_data.get("skill"), str)
            and evals_data["skill"]
            and not _is_placeholder(evals_data["skill"])
            and evals_data["skill"] != name
        ):
            warnings.append(
                f"evals file is for {evals_data['skill']!r}, not {name!r}"
            )
        for case in evals_data.get("cases", []) if isinstance(evals_data.get("cases"), list) else []:
            if not isinstance(case, dict):
                continue
            query = str(case.get("query", "")).strip()
            should = case.get("should_trigger")
            if not query or _is_placeholder(query) or not isinstance(should, bool):
                continue
            q_words = meta.keywords(query)
            shared = sorted(q_words & target_words)
            if should:
                if not shared:
                    blind_spots.append(
                        {
                            "query": query,
                            "holdout": bool(case.get("holdout", False)),
                            "missing_keywords": sorted(q_words),
                        }
                    )
                for comp_name, comp_words in competitors:
                    comp_shared = sorted(q_words & comp_words)
                    if len(comp_shared) > len(shared) and comp_shared:
                        competing_matches.append(
                            {
                                "query": query,
                                "competitor": comp_name,
                                "target_shared": shared,
                                "competitor_shared": comp_shared,
                            }
                        )
            else:
                if len(shared) >= 2 or meta.similarity(q_words, target_words) >= 0.25:
                    collision_risks.append(
                        {
                            "query": query,
                            "holdout": bool(case.get("holdout", False)),
                            "shared_keywords": shared,
                        }
                    )
        runs = score_runs(evals_data.get("runs", []))

    if collision_risks and not has_boundary:
        warnings.append(
            "negative queries share vocabulary with the description, which has "
            "no boundary clause (for example, 'Not for X; use Y for that')"
        )

    return {
        "skill": name,
        "path": str(skill_dir),
        "description": description,
        "description_chars": len(description),
        "listing_tokens": meta.estimate_tokens(f"{name}: {description}"),
        "keywords": sorted(target_words),
        "has_boundary_clause": has_boundary,
        "stats": stats,
        "blind_spots": blind_spots,
        "collision_risks": collision_risks,
        "competing_matches": competing_matches,
        "runs": runs,
        "errors": errors,
        "warnings": warnings,
    }


def format_report(result: dict) -> str:
    lines = [
        f"{result['skill']}  ({result['path']})",
        f"  description: {result['description_chars']} chars, "
        f"~{result['listing_tokens']} listing tok, "
        f"{len(result['keywords'])} keywords, "
        f"boundary clause: {'yes' if result['has_boundary_clause'] else 'no'}",
    ]
    if result["stats"]:
        s = result["stats"]
        lines.append(
            f"  cases: {s['total_cases']} total "
            f"({s['should_trigger']} should-trigger, "
            f"{s['should_not_trigger']} should-not, "
            f"{s['holdout_cases']} holdout)"
        )
    for err in result["errors"]:
        lines.append(f"  error    {err}")
    for warn in result["warnings"]:
        lines.append(f"  warning  {warn}")
    if result["blind_spots"]:
        lines.append("  blind spots (should-trigger queries sharing no keywords with description):")
        for item in result["blind_spots"]:
            tag = " [holdout]" if item["holdout"] else ""
            missing = ", ".join(item["missing_keywords"][:6]) or "none"
            lines.append(f"    - {item['query']!r}{tag}  (query words: {missing})")
    if result["collision_risks"]:
        lines.append("  false-trigger risks (should-not queries overlapping description keywords):")
        for item in result["collision_risks"]:
            tag = " [holdout]" if item["holdout"] else ""
            shared = ", ".join(item["shared_keywords"])
            lines.append(f"    - {item['query']!r}{tag}  (shared: {shared})")
    if result["competing_matches"]:
        lines.append("  competing skills with stronger keyword overlap on positive queries:")
        for item in result["competing_matches"]:
            lines.append(
                f"    - {item['query']!r}: {item['competitor']} matches "
                f"{item['competitor_shared']} vs {item['target_shared']}"
            )
    if result["runs"]:
        lines.append("  recorded runs:")
        for run in result["runs"]:
            reg = " [REGRESSED]" if run.get("regressed_from_previous") else ""
            hold = (
                f", holdout {run['holdout_passed']}"
                if run.get("holdout_passed") is not None
                else ""
            )
            lines.append(
                f"    round {run['round']}: trigger {run['should_trigger']}, "
                f"quiet {run['should_not_trigger']}{hold}{reg}"
            )
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate trigger evaluation sets and score skill descriptions."
    )
    parser.add_argument("skill_dir", help="path to the skill directory")
    parser.add_argument("--evals", help="path to a trigger-evals JSON file")
    parser.add_argument("--description", help="candidate description text to test before editing SKILL.md")
    parser.add_argument("--root", action="append", default=[], help="directory of competing skills to compare against; repeatable")
    parser.add_argument("--json", action="store_true", help="print machine-readable output")
    args = parser.parse_args(argv)

    skill_dir = Path(args.skill_dir)
    if not skill_dir.exists():
        print(f"error: {args.skill_dir} does not exist", file=sys.stderr)
        return 2

    evals_data = None
    if args.evals:
        evals_path = Path(args.evals)
        if not evals_path.is_file():
            print(f"error: {args.evals} does not exist", file=sys.stderr)
            return 2
        try:
            evals_data = json.loads(evals_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"error: invalid JSON in {args.evals}: {exc}", file=sys.stderr)
            return 2

    result = evaluate_skill(
        skill_dir,
        evals_data=evals_data,
        description_override=args.description,
        extra_roots=args.root,
    )
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_report(result))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
