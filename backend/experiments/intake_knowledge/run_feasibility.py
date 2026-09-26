"""EXP-002b: baseline Task B prompt vs the Release 4 prompt (feasibility check + requirement evidence).

    python -m backend.experiments.intake_knowledge.run_feasibility [--runs 3]

Reuses the pinned Task A outputs saved by EXP-002 (run `python -m backend.experiments.intake_knowledge.run` first).
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from openai import OpenAI

from backend.config import get_openai_api_key
from backend.experiments.intake_knowledge.run import BOUNDARY, OUT, analyse_run
from backend.experiments.intake_knowledge.scenarios import SCENARIOS, Scenario
from backend.experiments.intake_knowledge.feasibility_reviewer import validate_feasibility_issues, verify_requirement_evidence
from backend.models.intake import IntakeResult, role_understanding_to_dict
from backend.services.intake_reasoning import (
    IntakeReasoner,
    apply_intake_backstops,
    apply_posted_title,
    apply_search_boundary,
    parse_intake_decision,
    parse_role_understanding,

)

BASELINE = Path(__file__).with_name("baseline_task_b.txt")
CURRENT = Path(__file__).resolve().parents[3] / "prompts" / "intake_task_b_decision.txt"
SYSTEM = "Follow the instructions in the user message exactly and return only the JSON they specify."
# Which requirements a correct feasibility challenge should be about (regex over the referenced texts).
EXPECTED_REFS = {"S4": r"python|java|go|rust|c\+\+|kubernetes|kafka|spark|tensorflow|react|angular|ios|android|terraform|graphql|snowflake", "S5": r"kubernetes|language model|llm|12|8\+", "S6": r"staff|years|experience"}


def decide(reasoner: IntakeReasoner, client: OpenAI, scenario: Scenario, understanding, template: str) -> Dict[str, Any]:
    prompt = template.replace("{role_understanding_json}", json.dumps(role_understanding_to_dict(understanding))).replace("{raw_input}", scenario.jd)
    payload = reasoner._call_json(client, SYSTEM, prompt)
    decision = parse_intake_decision(payload)
    claimed = sum(1 for quote in decision.final_search_intent.evidence.values() if quote)
    raw_feasibility = [i for i in decision.issues if i.kind == "feasibility"]
    verify_requirement_evidence(decision, scenario.jd)
    validate_feasibility_issues(decision, understanding.posted_title)
    kept_feasibility = [i for i in decision.issues if i.kind == "feasibility"]
    decision, contradictions = apply_intake_backstops(scenario.jd, bool(understanding.explicit_constraints.locations), decision)
    result = IntakeResult(raw_input=scenario.jd, role_understanding=understanding, decision=decision, contradictions=contradictions)
    result.status = "needs_clarification" if any(i.decision == "ask" for i in decision.issues) else "ready"
    result = apply_search_boundary(result, BOUNDARY)
    row = analyse_run(scenario, result)
    fi = result.decision.final_search_intent
    total = len(fi.hard_requirements) + len(fi.strong_signals) + len(fi.preferred_differentiators)
    row.update(
        feasibility_raised=len(raw_feasibility),
        feasibility_kept=len(kept_feasibility),
        feasibility=[{"decision": i.decision, "references": i.references, "text": i.insight_text or i.question} for i in kept_feasibility],
        evidence_claimed=claimed,
        evidence_verified=len(fi.evidence),
        requirements_total=total,
        evidence=fi.evidence,
    )
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    key = get_openai_api_key()
    if not key:
        raise SystemExit("OPENAI_API_KEY is not configured.")
    client = OpenAI(api_key=key)
    reasoner = IntakeReasoner(client=client)
    templates = {"baseline": BASELINE.read_text(encoding="utf-8"), "revised": CURRENT.read_text(encoding="utf-8")}

    rows: List[Dict[str, Any]] = []
    for scenario in SCENARIOS:
        understanding = parse_role_understanding(json.loads((OUT / f"{scenario.id}_task_a.json").read_text(encoding="utf-8")))
        apply_posted_title(understanding, scenario.jd, scenario.posted_title or None)
        print(f"\n{scenario.id} {scenario.label}")
        for condition, template in templates.items():
            for run in range(1, args.runs + 1):
                row = decide(reasoner, client, scenario, understanding, template)
                row.update(scenario=scenario.id, condition=condition, run=run)
                rows.append(row)
                print(f"  {condition:8s} run{run}: asks={row['ask_count']} fp={row['false_positive_asks']} feasibility={row['feasibility_kept']}/{row['feasibility_raised']} evidence={row['evidence_verified']}/{row['requirements_total']}")
    (OUT / "runs_feasibility.json").write_text(json.dumps(rows, indent=1, default=str), encoding="utf-8")
    print(f"\nWrote {OUT / 'runs_feasibility.json'}")


if __name__ == "__main__":
    main()
