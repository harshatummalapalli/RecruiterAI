"""Baseline vs experimental comparison, computed OFFLINE from the stored run files (EXPERIMENT ONLY; no model call).

    python -m backend.experiments.intake_strategy.compare_arms

The experimental intents are re-evaluated with the CURRENT evaluator and validators, so the table is reproducible from
the stored intents rather than from whatever evaluator version ran at capture time. Baseline statuses are the stored
ones, except `no_invented_company_exclusion`, which did not exist at baseline and is computed from the stored baseline
intents (the baseline emitted `exclude_current_company: "Security firms"`).

Also reports observations the gold does NOT gate, so a green table is not mistaken for a complete picture.
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


def compare(root: Path = DEFAULT_OUT) -> Dict[str, Any]:
    inputs = load_inputs()
    base = [r for r in _load(root / "baseline", "baseline") if r.get("intent")]
    exp_raw = _load(root / "experimental", "experimental")
    exp_records: List[Dict[str, Any]] = []
    for r in exp_raw:
        if not r.get("intent"):
            exp_records.append(r)
            continue
        intent = ExperimentalHiringIntent.model_validate(r["intent"])
        exp_records.append({**r, "gold": gold.evaluate(intent, inputs["jd"], inputs["brief"])})
    ok = [r for r in exp_records if r.get("intent")]

    base_status: Dict[str, Counter] = {}
    for r in base:
        for g in r["gold"]["critical"] + r["gold"]["compiler"]:
            base_status.setdefault(g["id"], Counter())[g["status"]] += 1
        company_x = [x for x in r["intent"].get("exclusions", []) if "company" in x["kind"]]
        base_status.setdefault("no_invented_company_exclusion", Counter())["FAIL" if company_x else "PASS"] += 1
    exp_status: Dict[str, Counter] = {}
    exp_class: Dict[str, Counter] = {}
    for r in ok:
        for g in r["gold"]["critical"]:
            exp_status.setdefault(g["id"], Counter())[g["status"]] += 1
            if g["failure_class"]:
                exp_class.setdefault(g["id"], Counter())[g["failure_class"]] += 1

    ids = list(exp_status)
    table = [{"id": i, "baseline": _fmt(base_status[i]) if i in base_status else "not expressible (no field)",
              "experimental": _fmt(exp_status[i]), "experimental_failure_class": dict(exp_class.get(i, {}))} for i in ids]
    compiler_ids = [i for i in base_status if i.startswith("compiler_")]
    compiler = [{"id": i, "baseline": _fmt(base_status[i]), "experimental": "not run (compiler unchanged, out of scope)"} for i in compiler_ids]

    # ---- observations the gold does not gate
    obs: Dict[str, Any] = {"runs": {"baseline_parsed": len(base), "experimental_parsed": len(ok), "experimental_attempted": len(exp_raw)}}
    sec_firm, seniority_a, domain_counts, a_exp, remote_in_text, neg_counts, rec_counts, overlap_low, overlap_all = [], [], [], [], [], [], [], 0, 0
    for r in ok:
        it = ExperimentalHiringIntent.model_validate(r["intent"])
        a, _ = gold.find_paths(it)
        va = effective_view(it, a.id) if a else None
        sec_firm.append(any(("security firm" in (x.concept + " ".join(x.includes)).lower()) for x in it.semantic_exclusions))
        seniority_a.append(f"{va['seniority'].value}/{va['seniority'].strength}" if va and va["seniority"] else None)
        domain_counts.append(len(it.domain) + sum(len(p.domain) for p in it.sourcing_paths))
        a_exp.append(f"{va['experience'].minimum_years}+/{va['experience'].strength}" if va and va["experience"] else None)
        blob = json.dumps(r["intent"]).lower()
        loc_blob = " ".join(json.dumps(x).lower() for x in [va["location"].model_dump() if va and va["location"] else {}])
        remote_in_text.append("remote" in blob)
        neg_counts.append(len(it.semantic_exclusions))
        rec_counts.append(len(it.reconciliations))
        for atom in r["gold"]["validation"]["atoms"]:
            if atom.get("quote_overlap") is not None:
                overlap_all += 1
                overlap_low += atom["quote_overlap"] < 0.5
    obs.update({
        "semantic_negative_about_security_firms": f"{sum(sec_firm)}/{len(ok)} runs (the brief states it; the model kept it as a semantic concept, not a company filter)",
        "path_a_effective_seniority": dict(Counter(map(str, seniority_a))),
        "path_a_effective_experience": dict(Counter(map(str, a_exp))),
        "domain_atoms_per_run": domain_counts,
        "semantic_exclusions_per_run": neg_counts,
        "reconciliations_per_run": rec_counts,
        "remote_mentioned_anywhere_in_intent": f"{sum(remote_in_text)}/{len(ok)} (no typed field: lives only in quote / label text)",
        "quote_overlap_below_0.5": f"{overlap_low}/{overlap_all} atoms with a quote (paraphrase vs mismatch is undecidable lexically)",
        "validation_status_counts": [r["gold"]["validation"]["status_counts"] for r in ok],
        "diagnostic_codes": dict(Counter(d["code"] for r in ok for d in r["gold"]["validation"]["diagnostics"])),
    })
    tokens = {
        "baseline": {"input": sum(c["input_tokens"] for r in base for c in r["model_calls"]), "output": sum(c["output_tokens"] for r in base for c in r["model_calls"])},
        "experimental": {"input": sum(c["input_tokens"] for r in ok for c in r["model_calls"]), "output": sum(c["output_tokens"] for r in ok for c in r["model_calls"])},
    }
    return {"table": table, "compiler": compiler, "observations": obs, "tokens": tokens, "experimental_stability": stability(exp_records)}


def render(result: Dict[str, Any]) -> str:
    lines = ["| assertion | baseline (5 runs) | experimental (5 runs) | experimental failure class |", "|---|---|---|---|"]
    for row in result["table"]:
        lines.append(f"| `{row['id']}` | {row['baseline']} | {row['experimental']} | {row['experimental_failure_class'] or ''} |")
    lines += ["", "Compiler checks (separate class; compiler unchanged, so only the baseline ran them):", ""]
    for row in result["compiler"]:
        lines.append(f"- `{row['id']}`: baseline {row['baseline']}")
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
