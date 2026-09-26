"""EXP-002: does a small, selected slice of the Knowledge Library improve the intake decision (Task B)?

    python -m backend.experiments.intake_knowledge.run [--runs 3]

Same Task A output per scenario in both conditions (Task A is run once and pinned), so the only difference is the
knowledge excerpt in Task B. The rest of the production path is applied unchanged: the deterministic backstops and
the recruiter's Search Boundary. Uses the real model (gpt-4o-mini, temperature 0) and costs a few cents.

The decision rule was written down BEFORE the first run (see docs/experiments/intake-knowledge-spike.md):
wire the knowledge into Task B only if it clearly helps and does not add false-positive questions.
"""

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

from backend.config import get_openai_api_key
from backend.experiments.intake_knowledge.scenarios import SCENARIOS, Scenario
from backend.models.intake import IntakeDecision, IntakeResult, SearchBoundary, role_understanding_to_dict
from backend.services.intake_reasoning import (
    IntakeReasoner,
    apply_intake_backstops,
    apply_posted_title,
    apply_search_boundary,
    parse_intake_decision,
    parse_role_understanding,
)
from backend.experiments.intake_knowledge.knowledge_slice import select_knowledge_slice

OUT = Path(__file__).resolve().parents[3] / "output" / "experiments" / "intake_knowledge"
BOUNDARY = SearchBoundary(hiring_company="Acme", country="Canada", work_mode="hybrid", state="Ontario", city="Toronto", radius_miles=25.0)
MATERIAL_FIELDS = re.compile(r"title|query|tier|requirement|experience|years|filter|exclu|hard|preferred|seniority|search|core|supporting", re.IGNORECASE)


def task_b_prompt(reasoner: IntakeReasoner, understanding_dict: Dict[str, Any], raw_input: str, knowledge_text: Optional[str]) -> str:
    template = reasoner._load_prompt("intake_task_b_decision.txt")
    prompt = template.replace("{role_understanding_json}", json.dumps(understanding_dict)).replace("{raw_input}", raw_input)
    if knowledge_text:
        marker = "Role Understanding (from the prior step):"
        prompt = prompt.replace(marker, knowledge_text + "\n\n" + marker, 1)
    return prompt


def decide(reasoner: IntakeReasoner, client: OpenAI, scenario: Scenario, understanding, knowledge_text: Optional[str]) -> IntakeResult:
    raw = task_b_prompt(reasoner, role_understanding_to_dict(understanding), scenario.jd, knowledge_text)
    payload = reasoner._call_json(client, "Follow the instructions in the user message exactly and return only the JSON they specify.", raw)
    decision = parse_intake_decision(payload)
    decision, contradictions = apply_intake_backstops(scenario.jd, bool(understanding.explicit_constraints.locations), decision)
    result = IntakeResult(raw_input=scenario.jd, role_understanding=understanding, decision=decision, contradictions=contradictions)
    result.status = "needs_clarification" if any(i.decision == "ask" for i in decision.issues) else "ready"
    return apply_search_boundary(result, BOUNDARY)


def surfaced_text(decision: IntakeDecision) -> str:
    parts: List[str] = list(decision.warnings)
    for issue in decision.issues:
        if issue.decision in ("ask", "tell"):
            parts += [issue.issue or "", issue.question or "", issue.insight_text or "", issue.reasoning or ""]
    parts.append(decision.search_consequence_summary or "")
    return " ".join(parts)


def analyse_run(scenario: Scenario, result: IntakeResult) -> Dict[str, Any]:
    asks = [i for i in result.decision.issues if i.decision == "ask"]
    ask_rows = []
    for issue in asks:
        text = f"{issue.issue} {issue.question or ''}"
        expected = bool(scenario.expected_ask and re.search(scenario.expected_ask, text, re.IGNORECASE))
        a, b = issue.consequence_if_answer_a or "", issue.consequence_if_answer_b or ""
        material = bool(a and b and a.strip().lower() != b.strip().lower() and MATERIAL_FIELDS.search(a) and MATERIAL_FIELDS.search(b))
        ask_rows.append({"issue": issue.issue, "question": issue.question, "expected": expected, "material": material, "backstop": issue.injected_by_backstop})
    found = bool(scenario.expected_finding and re.search(scenario.expected_finding, surfaced_text(result.decision), re.IGNORECASE))
    tells = [i.insight_text for i in result.decision.issues if i.decision == "tell" and i.insight_text]
    fi = result.decision.final_search_intent
    return {
        "ask_count": len(asks),
        "false_positive_asks": sum(1 for row in ask_rows if not row["expected"]),
        "asks": ask_rows,
        "finding_hit": found if scenario.expected_finding else None,
        "tells": tells,
        "warnings": list(result.decision.warnings),
        "consequence": result.decision.search_consequence_summary,
        "hard": list(fi.hard_requirements),
        "strong": list(fi.strong_signals),
        "preferred": list(fi.preferred_differentiators),
        "query": fi.natural_language_search_query,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    key = get_openai_api_key()
    if not key:
        raise SystemExit("OPENAI_API_KEY is not configured.")
    client = OpenAI(api_key=key)
    reasoner = IntakeReasoner(client=client)
    OUT.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    started = time.time()
    for scenario in SCENARIOS:
        a_raw = reasoner._call_json(client, reasoner._load_prompt("intake_task_a_understanding.txt"), reasoner._task_a_user_prompt(scenario.jd, scenario.posted_title or None))
        understanding = parse_role_understanding(a_raw)
        apply_posted_title(understanding, scenario.jd, scenario.posted_title or None)
        slice_ = select_knowledge_slice(role_understanding_to_dict(understanding))
        print(f"\n{scenario.id} {scenario.label}: identity={understanding.primary_candidate_identity.value!r} slice={slice_.sources} ({len(slice_.text)} chars)")
        for condition, text in (("without", None), ("with", slice_.text)):
            for run in range(1, args.runs + 1):
                result = decide(reasoner, client, scenario, understanding, text)
                analysis = analyse_run(scenario, result)
                analysis.update({"scenario": scenario.id, "condition": condition, "run": run})
                rows.append(analysis)
                print(f"  {condition:7s} run{run}: asks={analysis['ask_count']} fp={analysis['false_positive_asks']} finding={analysis['finding_hit']}")
        (OUT / f"{scenario.id}_task_a.json").write_text(json.dumps(role_understanding_to_dict(understanding), indent=1), encoding="utf-8")
        (OUT / f"{scenario.id}_slice.txt").write_text(slice_.text, encoding="utf-8")

    (OUT / "runs.json").write_text(json.dumps(rows, indent=1, default=str), encoding="utf-8")
    print(f"\nWrote {OUT / 'runs.json'} ({len(rows)} runs, {time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
