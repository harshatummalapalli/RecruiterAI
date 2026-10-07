"""Compares two Judge models on the FROZEN depth matrix (the only experimental variable is the model).

The matrix (`depth_matrix.PROFILES`, the intent, the checks), the requirement / exclusion / depth prompts, the verifier, the quote gate and the evaluator
(`depth_matrix.analyze`) are the same code for both models. This module adds nothing to the evaluation; it reads the same stored runs and reports the measures asked for:

  A  observed-depth accuracy (overall, per skill, per evidence level, one-level bias, run-to-run instability)
  B  deterministic comparison accuracy (code recomputed independently of the Judge)
  C  end-to-end verdict accuracy (met / not met, and the three-way satisfied / not satisfied / insufficient)
  D  quote-gate correctness (every accepted depth has a quote that passes the gate; first-pass claims that failed it, and what happened to them)
  E  evidence-to-check binding (every judgment maps to one known check_id; every accepted quote names ITS skill and comes from demonstrated work; cross-check attempts)

    python -m backend.experiments.compiler_contract.depth_compare analyze
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from backend.experiments.compiler_contract import depth_matrix as dm
from backend.services.evidence_check import DEPTH_ORDER, subject_in, verify_quote

MODELS = {"gpt-4o-mini": dm.RAW, "gpt-4.1": dm.RESULTS / "raw_gpt-4.1"}
# list prices per 1M tokens (an ASSUMPTION used only to estimate spend, not a billing figure)
PRICES = {"gpt-4o-mini": (0.15, 0.60), "gpt-4.1": (2.00, 8.00)}
DEPTH_PROMPT_HEAD = "You read a candidate's profile and report how deeply"
LEVELS = [p.key for p in dm.PROFILES]
SKILLS = [n for n, _d, _q in dm.SKILLS]


def one_model(raw: Path, model: str) -> Dict[str, Any]:
    base = dm.analyze(raw, write=False)                                  # A / B / C of the previous phase: the same evaluator
    jobs = dm.load(raw)
    prof = {p.key: p for p in dm.PROFILES}
    rows: List[Dict[str, Any]] = []
    # D / E, read from the same stored runs
    gate_first_pass = {"claims": 0, "failed_gate": 0, "ellipsis": 0}
    accepted_gate_failures = 0
    binding = {"judgments": 0, "unknown_or_duplicate_check_id": 0, "accepted_not_naming_own_skill": 0, "accepted_not_work_evidence": 0, "discarded_by_binding": 0, "cross_check_attempts": 0}
    for j in jobs:
        by_id = {c["check_id"]: c for c in j["checks"]}
        ids = [x["check_id"] for x in j["judgments"]]
        binding["unknown_or_duplicate_check_id"] += sum(1 for i in ids if i not in by_id) + (len(ids) - len(set(ids)))
        passages = dm._passages(j)
        for r in j["requests"]:
            if r["system"].startswith(DEPTH_PROMPT_HEAD) and "instruction" not in json.loads(r["user"]) and r.get("response"):
                for x in json.loads(r["response"]).get("results", []):
                    if x.get("observed_depth") in ("working_knowledge", "hands_on", "advanced"):
                        gate_first_pass["claims"] += 1
                        ok, why = verify_quote(str(x.get("quote") or ""), next((p["text"] for p in passages if p["p"] == x.get("p")), None))
                        gate_first_pass["failed_gate"] += 0 if ok else 1
                        gate_first_pass["ellipsis"] += 1 if why == "ellipsis" else 0
        for x in j["judgments"]:
            c = by_id.get(x["check_id"])
            if not c or c["kind"] != "proficiency":
                continue
            binding["judgments"] += 1
            if (x.get("observed_depth") or "unspecified") != "unspecified":
                if not any(verify_quote(x["quote"], p["text"])[0] for p in passages):
                    accepted_gate_failures += 1
                if c["subject_terms"] and not subject_in(x["quote"], tuple(c["subject_terms"])):
                    binding["accepted_not_naming_own_skill"] += 1
                if x.get("evidence_type") not in ("demonstrated_work", "certification"):
                    binding["accepted_not_work_evidence"] += 1
            level = prof[j["candidate"]].level
            claimed = x.get("claimed_depth") or "unspecified"
            rows.append({"profile": j["candidate"], "skill": c["subject"], "required": c["proficiency"], "level": level, "run": j["run"], "claimed": claimed,
                         "signed_error": DEPTH_ORDER[claimed] - DEPTH_ORDER[level], "verdict": x["verdict"], "truth": dm.expected_verdict(level, c["proficiency"])})
        binding["discarded_by_binding"] += len(j["binding_discards"])
        binding["cross_check_attempts"] += sum(1 for d in j["binding_discards"] if d["reason"] == "binding:subject_not_in_quote")
    n = len(rows)
    acc = lambda sel: {"correct": sum(1 for r in sel if r["signed_error"] == 0), "of": len(sel)}                  # noqa: E731
    errs = [r for r in rows if r["signed_error"] != 0]
    per_cell: Dict[str, List[int]] = {}
    for r in rows:
        per_cell.setdefault(f"{r['profile']}|{r['skill']}", []).append(r["signed_error"])
    unstable_cells = [k for k, v in per_cell.items() if len(set(v)) > 1]
    t = base["totals"]
    p_in, p_out = PRICES[model]
    return {
        "model": model, "temperature": t["temperatures"], "models_recorded": t["models"], "jobs": t["jobs"], "cells": n, "calls": t["calls"], "input_tokens": t["input_tokens"], "output_tokens": t["output_tokens"],
        "estimated_cost_usd": round((t["input_tokens"] * p_in + t["output_tokens"] * p_out) / 1e6, 4), "failed_jobs": t["failed_jobs"],
        "A_overall": acc(rows), "A_per_skill": {s: acc([r for r in rows if r["skill"] == s]) for s in SKILLS}, "A_per_evidence_level": {k: acc([r for r in rows if r["profile"] == k]) for k in LEVELS},
        "A_by_required_depth": {d: acc([r for r in rows if r["required"] == d]) for d in ("working_knowledge", "hands_on", "advanced")},
        "error_profile": {"errors": len(errs), "over_by_one": sum(1 for r in errs if r["signed_error"] == 1), "under_by_one": sum(1 for r in errs if r["signed_error"] == -1),
                          "two_or_more": sum(1 for r in errs if abs(r["signed_error"]) >= 2), "mean_signed_error": round(sum(r["signed_error"] for r in rows) / n, 3) if n else None,
                          "mean_signed_error_when_wrong": round(sum(r["signed_error"] for r in errs) / len(errs), 3) if errs else None},
        "instability": {"cells": len(per_cell), "cells_with_run_to_run_disagreement": len(unstable_cells), "cells_wrong_on_every_run": sum(1 for v in per_cell.values() if all(e != 0 for e in v)),
                        "cells_right_on_every_run": sum(1 for v in per_cell.values() if all(e == 0 for e in v)), "unstable_cells": sorted(unstable_cells)},
        "B_code_comparison": base["B_code_comparison"], "C_end_to_end_met_vs_not": base["B_end_to_end_verdict"],
        "C_three_way": {"correct": sum(1 for r in rows if r["verdict"] == r["truth"]), "of": n},
        "C_stronger_than_required": base["B_stronger_than_required"],
        "D_quote_gate": {"accepted_depths_failing_the_gate": accepted_gate_failures, **gate_first_pass, "retried_checks": t["retried_checks"], "retries_recovered": t["retries_recovered"]},
        "E_binding": binding, "depth_payload_violations": base["depth_payload_violations"], "leak_token_hits": base["leak_token_hits"], "cells_detail": base["cells"],
        "error_cells": sorted({f"{r['level']}|{r['skill']}|claimed {r['claimed']}" for r in errs}),
    }


def analyze(write: bool = True) -> Dict[str, Any]:
    out = {m: one_model(p, m) for m, p in MODELS.items()}
    a, b = out["gpt-4o-mini"], out["gpt-4.1"]
    ea, eb = a["error_profile"]["errors"], b["error_profile"]["errors"]
    reduction = None if ea == 0 else round(1 - eb / ea, 3)
    new_violations = (b["D_quote_gate"]["accepted_depths_failing_the_gate"] + b["E_binding"]["accepted_not_naming_own_skill"] + b["E_binding"]["accepted_not_work_evidence"]
                      + b["E_binding"]["unknown_or_duplicate_check_id"] + b["B_code_comparison"]["of"] - b["B_code_comparison"]["correct"])
    base_violations = (a["D_quote_gate"]["accepted_depths_failing_the_gate"] + a["E_binding"]["accepted_not_naming_own_skill"] + a["E_binding"]["accepted_not_work_evidence"]
                       + a["E_binding"]["unknown_or_duplicate_check_id"] + a["B_code_comparison"]["of"] - a["B_code_comparison"]["correct"])
    out["comparison"] = {"errors_before": ea, "errors_after": eb, "relative_reduction": reduction, "rule": "material improvement = at least a 50% relative reduction in wrong observed-depth classifications, with no increase in "
                         "quote-gate, binding, check-id or comparison violations (declared before the stronger-model run)",
                         "violations_before": base_violations, "violations_after": new_violations,
                         "materially_improves": bool(reduction is not None and reduction >= 0.5 and new_violations <= base_violations)}
    if write:
        (dm.RESULTS / "comparison.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    r = analyze()
    for m in MODELS:
        x = r[m]
        print(m, "A", x["A_overall"], "err", x["error_profile"], "B", x["B_code_comparison"], "C", x["C_end_to_end_met_vs_not"], x["C_three_way"], "D", x["D_quote_gate"], "E", x["E_binding"], "inst", {k: v for k, v in x["instability"].items() if k != "unstable_cells"}, "$", x["estimated_cost_usd"])
    print(r["comparison"])
