"""Role 2 analysis, computed OFFLINE from the stored run files (EXPERIMENT ONLY; no model call, no network, compiler unmodified).

    python -m backend.experiments.intake_strategy.compare_role2

Three kinds of output, kept apart so a reader can tell them apart:
  1. the gold table: as it ran (pre-registered evaluator) and re-evaluated with the current evaluator (post-run corrections)
  2. DESCRIPTIVE observations that were NOT pre-registered (found by reading); never counted as assertions
  3. downstream observations: the UNMODIFIED production compiler applied offline to each intent's base fields, recorded as
     follow-ups, not fixed
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from backend.experiments.intake_strategy import gold_role2 as gold
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent
from backend.experiments.intake_strategy.run_baseline import DEFAULT_OUT
from backend.experiments.intake_strategy.run_role2 import load_inputs, stability
from backend.experiments.intake_strategy.validators import quote_in
from backend.services.search_compiler import compile_intent

I = re.IGNORECASE
# descriptive only: which hands_on items does the JD's own wording support?
_STATED_DEPTH = re.compile(r"\bpython\b|\bjava\b(?!\s*script)|generative ai|\bgenai\b", I)                                   # "Advanced" / "Hands-on experience"
_DEPTH_CUE = re.compile(r"hands-on|hands on|advanced|proficien|expert|working knowledge|familiar", I)  # does the CITED quote state any depth?
_HANDS_ON_FRAMING = re.compile(r"full stack|\bapis?\b|services?\b|distributed|software (development|engineering)|enterprise[- ]scale", I)  # "hands-on engineering role"


def _fmt(counter: Counter) -> str:
    return " ".join(f"{k}x{v}" for k, v in sorted(counter.items(), key=lambda kv: ("PASS", "PARTIAL", "FAIL").index(kv[0])))


def _load(root: Path) -> List[Dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(root.glob("role2_run*.json"))]


def _tally(records: List[Dict[str, Any]], key: str) -> Dict[str, Counter]:
    t: Dict[str, Counter] = {}
    for r in records:
        if r.get("intent"):
            for g in r[key]["critical"]:
                t.setdefault(g["id"], Counter())[g["status"]] += 1
    return t


def analyse(root: Path = DEFAULT_OUT / "role2") -> Dict[str, Any]:
    inputs = load_inputs()
    raw = _load(root)
    records = []
    for r in raw:
        if not r.get("intent"):
            records.append(r)
            continue
        it = ExperimentalHiringIntent.model_validate(r["intent"])
        records.append({**r, "stored_gold": r["gold"], "gold": gold.evaluate(it, inputs["jd"], inputs["brief"])})
    ok = [r for r in records if r.get("intent")]
    as_run, corrected = _tally([{**r, "gold": r["stored_gold"]} for r in ok], "gold"), _tally(ok, "gold")
    classes: Dict[str, Counter] = {}
    for r in ok:
        for g in r["gold"]["critical"]:
            if g["failure_class"]:
                classes.setdefault(g["id"], Counter())[g["failure_class"]] += 1
    table = [{"id": i, "as_run": _fmt(as_run[i]), "corrected": _fmt(corrected[i]), "class": dict(classes.get(i, {}))} for i in corrected]

    jd_resp_end = inputs["jd"].index("Requirements / Skills")
    resp_text, req_text = inputs["jd"][:jd_resp_end], inputs["jd"][jd_resp_end:]
    per_run: List[Dict[str, Any]] = []
    downstream: List[Dict[str, Any]] = []
    for r in ok:
        it = ExperimentalHiringIntent.model_validate(r["intent"])
        hands = [s.name for s in it.skills if s.proficiency == "hands_on"]
        a = [n for n in hands if _STATED_DEPTH.search(n)]
        bset = [n for n in hands if n not in a and _HANDS_ON_FRAMING.search(n)]
        c = [n for n in hands if n not in a and n not in bset]
        sig_resp = [e for e in it.evidence_signals if e.strength == "required" and e.basis and quote_in(e.basis.quote, resp_text) and not quote_in(e.basis.quote, req_text)]
        sig_req = [e for e in it.evidence_signals if e.strength == "required" and e.basis and quote_in(e.basis.quote, req_text)]
        names = {s.name.strip().lower(): s for s in it.skills}
        per_run.append({
            "run": r["run"], "role_family": it.role_family, "seniority_typed": it.seniority.value if it.seniority else None,
            "staff_in_text": [e.name for e in it.evidence_signals if re.search(r"\bstaff\b", e.name, I)],
            "remote": it.location.remote if it.location else None, "hybrid_in_text": [e.name for e in it.evidence_signals if re.search("hybrid", e.name, I)],
            "counts": {"skills": len(it.skills), "any_of": len(it.skill_any_of), "evidence_signals": len(it.evidence_signals), "domain": len(it.domain),
                       "required_evidence_signals": sum(e.strength == "required" for e in it.evidence_signals), "reconciliations": len(it.reconciliations)},
            "hands_on": {"total": len(hands), "A_source_states_depth": a, "B_defensible_by_hands_on_framing": bset, "C_no_depth_wording": c},
            "hands_on_quote_states_depth": f"{sum(1 for s in it.skills if s.proficiency == 'hands_on' and s.basis and s.basis.quote and _DEPTH_CUE.search(s.basis.quote))}/{len(hands)}",
            "required_skills_relationship": dict(Counter(s.relationship for s in it.skills if s.strength == "required")),
            "required_signals_from_responsibilities_only": [e.name[:90] for e in sig_resp],
            "required_signals_from_requirements": len(sig_req),
            "aks_and_eks_both_required_separately": ("aks" in names and "eks" in names and names["aks"].strength == "required" and names["eks"].strength == "required"),
            "domain_atoms": [(d.name, d.strength) for d in it.domain],
            "validator_errors": r["gold"]["validation"]["errors"], "diagnostic_codes": dict(Counter(d["code"] for d in r["gold"]["validation"]["diagnostics"])),
        })
        # --- downstream: the UNMODIFIED compiler on the base fields, offline
        plan = compile_intent(it)
        leaves: List[Dict[str, Any]] = []

        def walk(t: Any) -> None:
            if isinstance(t, dict) and "op" in t:
                for x in t.get("conditions", []):
                    walk(x)
            elif isinstance(t, dict):
                leaves.append(t)
        walk(plan.filter_tree)
        downstream.append({
            "run": r["run"], "hard_filter_leaves": len(leaves), "top_level_conditions": len(plan.filter_tree.get("conditions", [])),
            "retrieval_title_family": plan.retrieval_title_family,
            "title_filter": [l.get("value") for l in leaves if str(l.get("field", "")).endswith("current.title")],
            "experience_leaf": [(l.get("type"), l.get("value")) for l in leaves if "years_of_experience" in str(l.get("field", ""))],
            "location_leaves": [(l.get("field").split(".")[-1], l.get("value")) for l in leaves if "location" in str(l.get("field", ""))],
            "required_skill_groups_as_hard_ands": sum(1 for c in plan.filter_tree.get("conditions", []) if c.get("op") == "or"),
            "audit_routes": dict(Counter(a.route for a in plan.audit)), "warnings": plan.warnings[:3],
            "seniority_audit": [(a.source, a.route, a.note) for a in plan.audit if a.source == "seniority"],
        })
    return {"table": table, "per_run": per_run, "downstream": downstream, "stability": stability(records),
            "tokens": {"input": sum(c["input_tokens"] for r in ok for c in r["model_calls"]), "output": sum(c["output_tokens"] for r in ok for c in r["model_calls"]),
                       "elapsed_s": [r["elapsed_s"] for r in ok]}, "parsed": f"{len(ok)}/{len(raw)}"}


def render(result: Dict[str, Any]) -> str:
    lines = ["| assertion | as run (pre-registered) | corrected evaluator | class |", "|---|---|---|---|"]
    for row in result["table"]:
        lines.append(f"| `{row['id']}` | {row['as_run']} | {row['corrected']} | {row['class'] or ''} |")
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    root = Path(argv[0]) if argv else DEFAULT_OUT / "role2"
    result = analyse(root)
    (root.parent / "role2_analysis.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
