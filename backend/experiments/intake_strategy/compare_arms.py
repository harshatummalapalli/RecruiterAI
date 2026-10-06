"""Baseline vs experimental comparison, computed OFFLINE from the stored run files (EXPERIMENT ONLY; no model call).

    python -m backend.experiments.intake_strategy.compare_arms

The experimental intents are re-evaluated with the CURRENT evaluator and validators, so the table is reproducible from
the stored intents rather than from whatever evaluator version ran at capture time. Baseline statuses are the stored
ones, except `no_invented_company_exclusion`, which did not exist at baseline and is computed from the stored baseline
intents (the baseline emitted `exclude_current_company: "Security firms"`).

Three arms: the stored baseline; the previous experimental arm (v2) RE-EVALUATED with the hardened evaluator (it predates the
typed fields, so some new checks cannot pass for it by construction); and v3. v3 is shown as it ran and with the evaluator
as corrected afterwards, so the correction is visible. Also reports observations the gold does NOT gate.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from backend.experiments.intake_strategy import gold_experimental as gold
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent, effective_view
from backend.experiments.intake_strategy.run_baseline import DEFAULT_OUT, load_inputs
from backend.experiments.intake_strategy.run_experimental import stability


def _load(directory: Path, prefix: str) -> List[Dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob(f"{prefix}_run*.json"))]


def _fmt(counter: Counter) -> str:
    return " ".join(f"{k}x{v}" for k, v in sorted(counter.items(), key=lambda kv: ("PASS", "PARTIAL", "FAIL").index(kv[0]) if kv[0] in ("PASS", "PARTIAL", "FAIL") else 9))


def _reevaluate(records: List[Dict[str, Any]], inputs: Dict[str, str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in records:
        if not r.get("intent"):
            out.append(r)
            continue
        intent = ExperimentalHiringIntent.model_validate(r["intent"])
        out.append({**r, "stored_gold": r["gold"], "gold": gold.evaluate(intent, inputs["jd"], inputs["brief"])})
    return out


def _tally(records: List[Dict[str, Any]], key: str = "gold") -> Dict[str, Counter]:
    t: Dict[str, Counter] = {}
    for r in records:
        if r.get("intent"):
            for g in r[key]["critical"]:
                t.setdefault(g["id"], Counter())[g["status"]] += 1
    return t


def compare(root: Path = DEFAULT_OUT) -> Dict[str, Any]:
    inputs = load_inputs()
    base = [r for r in _load(root / "baseline", "baseline") if r.get("intent")]
    v2 = _reevaluate(_load(root / "experimental", "experimental"), inputs)
    v3_raw = _load(root / "experimental_v3", "experimental")
    v3 = _reevaluate(v3_raw, inputs)
    v3_ok = [r for r in v3 if r.get("intent")]

    base_status: Dict[str, Counter] = {}
    for r in base:
        for g in r["gold"]["critical"] + r["gold"]["compiler"]:
            base_status.setdefault(g["id"], Counter())[g["status"]] += 1
        base_status.setdefault("no_invented_company_exclusion", Counter())["FAIL" if [x for x in r["intent"].get("exclusions", []) if "company" in x["kind"]] else "PASS"] += 1
    v2_status, v3_status = _tally(v2), _tally(v3)
    v3_runtime = _tally([{**r, "gold": r["stored_gold"]} for r in v3_ok])  # the evaluator as it ran, before the negation correction
    v3_class: Dict[str, Counter] = {}
    for r in v3_ok:
        for g in r["gold"]["critical"]:
            if g["failure_class"]:
                v3_class.setdefault(g["id"], Counter())[g["failure_class"]] += 1

    ids = list(v3_status)
    table = []
    for i in ids:
        table.append({
            "id": i,
            "baseline": _fmt(base_status[i]) if i in base_status else "not expressible",
            "v2_reevaluated": _fmt(v2_status[i]) if i in v2_status else "n/a",
            "v3_as_run": _fmt(v3_runtime[i]) if i in v3_runtime else "n/a",
            "v3": _fmt(v3_status[i]),
            "v3_failure_class": dict(v3_class.get(i, {})),
        })
    compiler = [{"id": i, "baseline": _fmt(base_status[i])} for i in base_status if i.startswith("compiler_")]

    obs: Dict[str, Any] = {"runs": {"v3_attempted": len(v3_raw), "v3_parsed": len(v3_ok)}}
    per_run: List[Dict[str, Any]] = []
    for r in v3_ok:
        it = ExperimentalHiringIntent.model_validate(r["intent"])
        a, b = gold.find_paths(it)
        va, vb = (effective_view(it, a.id) if a else None), (effective_view(it, b.id) if b else None)
        firm = [x for x in it.semantic_exclusions if "security firm" in (x.concept + " ".join(x.includes)).lower()]
        per_run.append({
            "run": r["run"], "path_ids": [p.id for p in it.sourcing_paths],
            "A_location": {"countries": va["location"].countries, "entries": va["location"].entries, "remote": va["location"].remote} if va and va["location"] else None,
            "B_location": {"countries": vb["location"].countries, "entries": vb["location"].entries, "remote": vb["location"].remote} if vb and vb["location"] else None,
            "A_levels": [va["seniority"].value, *va["seniority"].alternatives] if va and va["seniority"] else None,
            "B_levels": [vb["seniority"].value, *vb["seniority"].alternatives] if vb and vb["seniority"] else None,
            "A_experience": (va["experience"].minimum_years, va["experience"].strength) if va and va["experience"] else None,
            "B_experience": (vb["experience"].minimum_years, vb["experience"].strength) if vb and vb["experience"] else None,
            "security_firm_exclusion": [x.concept for x in firm],
            "validator_errors": r["gold"]["validation"]["errors"],
            "diagnostic_codes": dict(Counter(d["code"] for d in r["gold"]["validation"]["diagnostics"])),
            "reconciliations": [(x.topic, x.action, x.path_id) for x in it.reconciliations],
            "counts": {"domain_atoms": len(it.domain) + sum(len(p.domain) for p in it.sourcing_paths), "evidence_signals": len(it.evidence_signals),
                       "semantic_exclusions": len(it.semantic_exclusions), "reconciliations": len(it.reconciliations)},
        })
    obs["per_run"] = per_run
    # the generic validators replayed on the PREVIOUS (v2) outputs: would they have caught what the owner found?
    obs["v2_replayed_errors"] = [r["gold"]["validation"]["errors"] for r in v2 if r.get("intent")]
    tokens = {"v3": {"input": sum(c["input_tokens"] for r in v3_ok for c in r["model_calls"]), "output": sum(c["output_tokens"] for r in v3_ok for c in r["model_calls"])},
              "elapsed_s": [r["elapsed_s"] for r in v3_ok]}
    return {"table": table, "compiler": compiler, "observations": obs, "tokens": tokens, "v3_stability": stability(v3)}


def render(result: Dict[str, Any]) -> str:
    lines = ["| assertion | baseline | v2 re-evaluated | v3 as run | v3 (evaluator corrected) | v3 failure class |", "|---|---|---|---|---|---|"]
    for row in result["table"]:
        lines.append(f"| `{row['id']}` | {row['baseline']} | {row['v2_reevaluated']} | {row['v3_as_run']} | {row['v3']} | {row['v3_failure_class'] or ''} |")
    lines += ["", "Compiler checks (compiler unchanged, out of scope): " + "; ".join(f"`{c['id']}` baseline {c['baseline']}" for c in result["compiler"])]
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    root = Path(argv[0]) if argv else DEFAULT_OUT
    result = compare(root)
    (root / "comparison.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(render(result))
    print()
    print(json.dumps({"observations": result["observations"], "tokens": result["tokens"]}, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
