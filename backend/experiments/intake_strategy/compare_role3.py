"""Role 3 analysis + cross-role field usage, computed OFFLINE from stored run files (EXPERIMENT ONLY; no model, no network, compiler unmodified).

    python -m backend.experiments.intake_strategy.compare_role3

1. the Role 3 gold table: as it ran (pre-registered evaluator) and with the current evaluator (one disclosed post-run correction)
2. descriptive per-run observations (not assertions)
3. field USAGE across the stored Role 1 (v3), Role 2 and Role 3 runs: how often each experimental field is populated, and with what values
4. the UNMODIFIED production compiler applied offline to each Role 3 intent, recorded as downstream follow-ups, never fixed
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from backend.experiments.intake_strategy import gold_role3 as gold
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent
from backend.experiments.intake_strategy.run_baseline import DEFAULT_OUT
from backend.experiments.intake_strategy.run_role3 import load_inputs, stability
from backend.services.search_compiler import compile_intent

ROOT = Path(__file__).parent
RESULTS = ROOT / "results"


def _fmt(c: Counter) -> str:
    return " ".join(f"{k}x{v}" for k, v in sorted(c.items(), key=lambda kv: ("PASS", "PARTIAL", "FAIL").index(kv[0])))


def usage(it: ExperimentalHiringIntent) -> Dict[str, Any]:
    skills = list(it.skills) + [s for p in it.sourcing_paths for s in p.skills]
    rel = Counter(s.relationship for s in skills) + Counter(g.relationship for g in it.skill_any_of)
    locs = [x for x in [it.location] + [p.location for p in it.sourcing_paths] if x]
    return {
        "sourcing_paths": len(it.sourcing_paths) > 0, "reconciliations": len(it.reconciliations) > 0, "semantic_exclusions": len(it.semantic_exclusions) > 0,
        "exclusions": len(it.exclusions) > 0, "domain": len(it.domain) + sum(len(p.domain) for p in it.sourcing_paths) > 0,
        "seniority.alternatives": any(s and s.alternatives for s in [it.seniority] + [p.seniority for p in it.sourcing_paths]),
        "seniority.leadership": any(s and s.leadership for s in [it.seniority] + [p.seniority for p in it.sourcing_paths]),
        "location.countries": any(l.countries for l in locs), "location.remote": any(l.remote for l in locs), "location.work_mode": any(l.work_mode for l in locs),
        "companies": len(it.companies) > 0, "skill_any_of": len(it.skill_any_of) > 0,
        "proficiency_levels": sorted({s.proficiency for s in skills if s.proficiency}), "proficiency_atoms": sum(1 for s in skills if s.proficiency),
        "relationship_current": rel.get("current", 0), "relationship_any": rel.get("any", 0), "relationship_past": rel.get("past", 0),
    }


def _arm_usage(directory: Path, pattern: str) -> Dict[str, Any]:
    rows = []
    for p in sorted(directory.glob(pattern)):
        rec = json.loads(p.read_text(encoding="utf-8"))
        if rec.get("intent"):
            rows.append(usage(ExperimentalHiringIntent.model_validate(rec["intent"])))
    out: Dict[str, Any] = {"runs": len(rows)}
    for key in rows[0]:
        vals = [r[key] for r in rows]
        if key == "proficiency_levels":
            out[key] = dict(Counter(l for v in vals for l in v))
        elif isinstance(vals[0], bool):
            out[key] = f"{sum(vals)}/{len(vals)}"
        else:
            out[key] = vals
    return out


def analyse(root: Path = DEFAULT_OUT / "role3") -> Dict[str, Any]:
    jd = load_inputs()["jd"]
    raw = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(root.glob("role3_run*.json"))]
    records, as_run, corrected = [], {}, {}
    for r in raw:
        if not r.get("intent"):
            records.append(r)
            continue
        it = ExperimentalHiringIntent.model_validate(r["intent"])
        records.append({**r, "stored_gold": r["gold"], "gold": gold.evaluate(it, jd)})
    ok = [r for r in records if r.get("intent")]
    for r in ok:
        for g in r["stored_gold"]["critical"]:
            as_run.setdefault(g["id"], Counter())[g["status"]] += 1
        for g in r["gold"]["critical"]:
            corrected.setdefault(g["id"], Counter())[g["status"]] += 1
    classes: Dict[str, Counter] = {}
    for r in ok:
        for g in r["gold"]["critical"]:
            if g["failure_class"]:
                classes.setdefault(g["id"], Counter())[g["failure_class"]] += 1
    table = [{"id": i, "as_run": _fmt(as_run[i]), "corrected": _fmt(corrected[i]), "class": dict(classes.get(i, {}))} for i in corrected]

    per_run: List[Dict[str, Any]] = []
    downstream: List[Dict[str, Any]] = []
    for r in ok:
        it = ExperimentalHiringIntent.model_validate(r["intent"])
        pbi_group = [g.any_of for g in it.skill_any_of if any("power" in o.lower() for o in g.any_of)]
        pbi_signal = [e.name[:90] for e in it.evidence_signals if "working knowledge" in e.name.lower() and "power" in e.name.lower()]
        per_run.append({
            "run": r["run"], "elapsed_s": r["elapsed_s"], "role_family": it.role_family,
            "seniority": (it.seniority.value, it.seniority.leadership) if it.seniority else None,
            "power_bi_as_or_group": pbi_group, "power_bi_depth_kept_as_text": pbi_signal,
            "domain": [(d.name[:60], d.strength) for d in it.domain],
            "signals_by_strength": dict(Counter(e.strength for e in it.evidence_signals)),
            "skills": len(it.skills), "skill_any_of": [g.any_of for g in it.skill_any_of],
            "companies": [(c.name, c.strength, c.relationship) for c in it.companies],
            "semantic_exclusions": [(x.concept[:90], len(x.includes)) for x in it.semantic_exclusions],
            "status_counts": r["gold"]["validation"]["status_counts"], "validator_errors": r["gold"]["validation"]["errors"],
            "diagnostic_codes": dict(Counter(d["code"] for d in r["gold"]["validation"]["diagnostics"])),
        })
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
            "run": r["run"], "hard_filter_leaves": len(leaves), "title_filter": [l.get("value") for l in leaves if str(l.get("field", "")).endswith("current.title")],
            "retrieval_title_family": plan.retrieval_title_family, "experience_leaf": [(l.get("type"), l.get("value")) for l in leaves if "years_of_experience" in str(l.get("field", ""))],
            "location_leaves": [(l.get("field").split(".")[-1], l.get("value")) for l in leaves if "location" in str(l.get("field", ""))],
            "education_leaves": [(l.get("field").split(".")[-1], l.get("value")) for l in leaves if "education" in str(l.get("field", "")) or "field_of_study" in str(l.get("field", ""))],
            "company_routes": [(a.source, a.route, a.strength, a.temporal) for a in plan.audit if a.source.startswith("company")],
            "seniority_audit": [(a.source, a.route, a.note) for a in plan.audit if a.source == "seniority"],
            "skill_routes": dict(Counter(a.route for a in plan.audit if a.source.startswith("skill"))),
            "warnings": plan.warnings[:4],
        })
    usage_table = {"role1_v3": _arm_usage(RESULTS / "experimental_v3", "experimental_run*.json"), "role2": _arm_usage(RESULTS / "role2", "role2_run*.json"),
                   "role3": _arm_usage(root, "role3_run*.json")}
    return {"table": table, "per_run": per_run, "downstream": downstream, "usage": usage_table, "stability": stability(records), "parsed": f"{len(ok)}/{len(raw)}",
            "tokens": {"input": sum(c["input_tokens"] for r in ok for c in r["model_calls"]), "output": sum(c["output_tokens"] for r in ok for c in r["model_calls"]),
                       "elapsed_s": [r["elapsed_s"] for r in ok]},
            "transient_retries": {r["run"]: r["transient_retries"] for r in raw if r.get("transient_retries")}}


def main(argv: List[str] | None = None) -> int:
    root = Path(argv[0]) if argv else DEFAULT_OUT / "role3"
    result = analyse(root)
    (root.parent / "role3_analysis.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print("| assertion | as run (pre-registered) | corrected | class |\n|---|---|---|---|")
    for row in result["table"]:
        print(f"| `{row['id']}` | {row['as_run']} | {row['corrected']} | {row['class'] or ''} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
