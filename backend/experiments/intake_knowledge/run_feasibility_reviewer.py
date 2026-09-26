"""EXP-002c: a dedicated feasibility reviewer call after the unchanged Task B.

    python -m backend.experiments.intake_knowledge.run_feasibility_reviewer [--runs 3]
"""

import argparse
import json
import re
from typing import Any, Dict, List

from openai import OpenAI

from backend.config import get_openai_api_key
from backend.experiments.intake_knowledge.run import OUT, decide
from backend.experiments.intake_knowledge.run_feasibility import EXPECTED_REFS
from backend.experiments.intake_knowledge.scenarios import SCENARIOS
from backend.experiments.intake_knowledge.feasibility_reviewer import review_feasibility
from backend.services.intake_reasoning import IntakeReasoner, apply_posted_title, parse_role_understanding


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    key = get_openai_api_key()
    if not key:
        raise SystemExit("OPENAI_API_KEY is not configured.")
    client = OpenAI(api_key=key)
    reasoner = IntakeReasoner(client=client)

    rows: List[Dict[str, Any]] = []
    for scenario in SCENARIOS:
        understanding = parse_role_understanding(json.loads((OUT / f"{scenario.id}_task_a.json").read_text(encoding="utf-8")))
        apply_posted_title(understanding, scenario.jd, scenario.posted_title or None)
        result = decide(reasoner, client, scenario, understanding, None)  # production Task B, unchanged
        fi = result.decision.final_search_intent
        print(f"\n{scenario.id} {scenario.label} ({len(fi.hard_requirements)} core)")
        for run in range(1, args.runs + 1):
            issues = review_feasibility(reasoner, understanding, fi.hard_requirements, fi.strong_signals, fi.preferred_differentiators)
            expected = EXPECTED_REFS.get(scenario.id)
            caught = bool(expected and any(re.search(expected, " ".join(i.references), re.I) for i in issues))
            rows.append({"scenario": scenario.id, "run": run, "findings": [{"issue": i.issue, "references": i.references, "text": i.insight_text} for i in issues], "caught": caught})
            print(f"  run{run}: findings={len(issues)} caught={caught}")
            for i in issues:
                print(f"      - {i.issue} | refs={[r[:45] for r in i.references]} | {(i.insight_text or '')[:150]}")
    (OUT / "runs_feasibility_reviewer.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
