"""FINAL Evidence Depth hardening pass: `evidence_basis` + the deterministic CEILING, on the SAME frozen 90-cell matrix, SAME model (gpt-4o-mini, temperature 0).

What is new in the Judge (and nothing else): for every skill the model also reports an `evidence_basis` (explicit_depth / concrete_skill_use / routine_skill_use /
generic_involvement / no_depth_evidence). CODE maps the basis to the MAXIMUM SUPPORTED DEPTH and the credited depth is `min(model's observed_depth, ceiling)`:

    no_depth_evidence -> unspecified      generic_involvement -> unspecified     routine_skill_use -> working_knowledge
    concrete_skill_use -> hands_on        explicit_depth -> the depth the quote itself states (a recognised cue in a clause naming the skill), else unspecified

Not changed: the matrix, the evidence texts, the checks, the requirement / exclusion prompts, the quote gate, the binding validator, the verifier, the model. The depth prompt
gained ONLY the evidence_basis definitions and output field (`prompt_without_basis()` reproduces the previous prompt exactly).

DECLARED BEFORE THE RUN (not tuned afterwards):
  hard gate    no evidence is credited above the maximum depth the contract allows: credited depth <= ceiling(basis) in every cell, and no `met` verdict on the named-only (none)
               or familiar levels. A shortfall is INSUFFICIENT_EVIDENCE (`not_evidenced`), never a false positive.
  quality      zero quote-gate / binding / check-id / comparison violations; false-positive depth cases materially reduced against the frozen baseline (>= 50% fewer).
  acceptable evidence_basis per level (the generic definitions, applied to the fixed profile texts):
      none -> generic_involvement | no_depth_evidence      familiar -> no_depth_evidence | generic_involvement | explicit_depth (no cue, so ceiling unspecified)
      working_knowledge -> routine_skill_use | explicit_depth      hands_on -> concrete_skill_use      advanced -> explicit_depth
  expected maximum_supported_depth = the profile's level.

    python -m backend.experiments.compiler_contract.depth_basis run
    python -m backend.experiments.compiler_contract.depth_basis analyze
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from backend.experiments.compiler_contract import depth_compare as dc
from backend.experiments.compiler_contract import depth_matrix as dm
from backend.services import requirement_judge as rj
from backend.services.evidence_check import DEPTH_ORDER, meets_depth

RAW_BASIS = dm.RESULTS / "raw_basis"
ANALYSIS = dm.RESULTS / "analysis_basis.json"
ACCEPTABLE_BASIS = {
    "none": {"generic_involvement", "no_depth_evidence"},
    "familiar": {"no_depth_evidence", "generic_involvement", "explicit_depth"},
    "working_knowledge": {"routine_skill_use", "explicit_depth"},
    "hands_on": {"concrete_skill_use"},
    "advanced": {"explicit_depth"},
}
DEPTH_PROMPT_HEAD = "You read a candidate's profile and report how deeply"


def prompt_without_basis(prompt: str = None) -> str:
    """The depth prompt of the previous phases: the current prompt minus the evidence_basis block and output field (used to prove the old runs and the new runs differ in
    that addition only)."""
    p = prompt or rj._DEPTH_PROMPT
    a, b = p.index("For every skill also report the evidence_basis"), p.index("Return only JSON")
    p = p[:a] + p[b:]
    return p.replace('"evidence_basis":"explicit_depth|concrete_skill_use|routine_skill_use|generic_involvement|no_depth_evidence",', "")


def run(runs: int = 6, workers: int = 6) -> None:
    dm.run(runs, workers, None, RAW_BASIS)


def _cells(raw: Path) -> List[Dict[str, Any]]:
    prof = {p.key: p for p in dm.PROFILES}
    out: List[Dict[str, Any]] = []
    for j in dm.load(raw):
        level = prof[j["candidate"]].level
        by_id = {c["check_id"]: c for c in j["checks"]}
        for x in j["judgments"]:
            c = by_id[x["check_id"]]
            if c["kind"] != "proficiency":
                continue
            req = c["proficiency"]
            claimed = x.get("claimed_depth") or "unspecified"
            accepted = x.get("observed_depth") or "unspecified"
            ceiling = x.get("maximum_supported_depth") or "unspecified"
            out.append({"profile": j["candidate"], "run": j["run"], "skill": c["subject"], "required": req, "level": level, "basis": x.get("evidence_basis"), "claimed": claimed,
                        "ceiling": ceiling, "accepted": accepted, "verdict": x["verdict"], "truth": dm.expected_verdict(level, req),
                        "code_verdict": "met" if meets_depth(accepted, req) else ("partly" if accepted != "unspecified" else "not_evidenced"), "discard": x.get("discard_reason"),
                        "capped": bool(x.get("capped"))})
    return out


def analyze(write: bool = True, raw: Path = RAW_BASIS) -> Dict[str, Any]:
    cells = _cells(raw)
    n = len(cells)
    rank = lambda d: DEPTH_ORDER[d]                                                                   # noqa: E731
    shared = dc.one_model(raw, "gpt-4o-mini")                                                        # quote gate (D) and binding (E) of the earlier phase, same evaluator
    base_cells = _cells(dm.RAW)                                                                        # the frozen baseline: the same matrix with the previous depth prompt
    base_key = {(c["profile"], c["skill"], c["run"]): c for c in base_cells}

    def fp(cs): return [c for c in cs if c["verdict"] == "met" and c["truth"] != "met"]              # noqa: E704
    def over(cs, f): return [c for c in cs if rank(c[f]) > rank(c["level"])]                          # noqa: E704
    A = sum(1 for c in cells if c["basis"] in ACCEPTABLE_BASIS[c["profile"]])
    B_claim = sum(1 for c in cells if c["claimed"] == c["level"])
    B_final = sum(1 for c in cells if c["accepted"] == c["level"])
    C = sum(1 for c in cells if c["ceiling"] == c["level"])
    D = sum(1 for c in cells if c["verdict"] == c["code_verdict"])
    E_met = sum(1 for c in cells if (c["verdict"] == "met") == (c["truth"] == "met"))
    E_three = sum(1 for c in cells if c["verdict"] == c["truth"])
    gate_cells = [c for c in cells if c["profile"] in ("none", "familiar")]
    too_deep_before = over(base_cells, "claimed")
    new_by = {(c["profile"], c["skill"], c["run"]): c for c in cells}
    prior_now = [new_by[(c["profile"], c["skill"], c["run"])] for c in too_deep_before if (c["profile"], c["skill"], c["run"]) in new_by]
    claimed_too_deep = over(cells, "claimed")
    summary = {
        "model": sorted({j["model"] for j in dm.load(raw)}), "cells": n, "jobs": shared["jobs"], "calls": shared["calls"], "estimated_cost_usd": shared["estimated_cost_usd"],
        "A_evidence_basis": {"correct": A, "of": n, "acceptable": {k: sorted(v) for k, v in ACCEPTABLE_BASIS.items()},
                             "distribution": {p.key: _count([c["basis"] for c in cells if c["profile"] == p.key]) for p in dm.PROFILES},
                             "missing_or_unrecognised": sum(1 for c in cells if c["basis"] is None)},
        "B_observed_depth": {"model_claim_correct": B_claim, "credited_correct": B_final, "of": n},
        "C_maximum_supported_depth": {"correct": C, "of": n, "by_level": {p.key: {"ceiling": _count([c["ceiling"] for c in cells if c["profile"] == p.key])} for p in dm.PROFILES}},
        "D_deterministic_comparison": {"correct": D, "of": n},
        "E_final_verdict": {"met_vs_not_correct": E_met, "three_way_correct": E_three, "of": n},
        "F_quote_gate": shared["D_quote_gate"],
        "G_binding": shared["E_binding"],
        "gate": {
            "credited_above_ceiling": sum(1 for c in cells if c["claimed"] != "unspecified" and c["accepted"] != "unspecified" and rank(c["accepted"]) > rank(c["ceiling"])),
            "credited_above_the_evidence_level": len(over(cells, "accepted")), "credited_above_the_evidence_level_cells": sorted({f"{c['level']}|{c['skill']}|credited {c['accepted']}" for c in over(cells, "accepted")}),
            "met_on_named_only_or_familiar": sum(1 for c in gate_cells if c["verdict"] == "met"),
            "named_only_or_familiar_verdicts": _count([c["verdict"] for c in gate_cells]),
            "false_positive_met": len(fp(cells)), "false_positive_cells": sorted({f"{c['level']}|{c['skill']}|required {c['required']}" for c in fp(cells)}),
            "false_negative_not_met_though_the_evidence_suffices": sum(1 for c in cells if c["truth"] == "met" and c["verdict"] != "met"),
            "false_negative_cells": sorted({f"{c['level']}|{c['skill']}|required {c['required']}|{c['verdict']}" for c in cells if c["truth"] == "met" and c["verdict"] != "met"}),
            "insufficient_instead_of_false_positive": sum(1 for c in cells if c["truth"] != "met" and c["level"] == "unspecified" and c["verdict"] == "not_evidenced"),
        },
        "ceiling": {"model_claimed_too_deep": len(claimed_too_deep), "of_which_capped_by_the_ceiling": sum(1 for c in claimed_too_deep if rank(c["accepted"]) < rank(c["claimed"])),
                    "of_which_still_credited_too_deep": len(over(claimed_too_deep, "accepted")), "capped_cells": sorted({f"{c['level']}|{c['skill']}|{c['claimed']}->{c['accepted']}|{c['basis']}" for c in cells if c["capped"]}),
                    "cells_capped": sum(1 for c in cells if c["capped"])},
        "baseline": {"model_claimed_too_deep": len(too_deep_before), "false_positive_met": len(fp(base_cells)), "false_positive_cells": sorted({f"{c['level']}|{c['skill']}|required {c['required']}" for c in fp(base_cells)}),
                     "credited_above_the_evidence_level": len(over(base_cells, "accepted")), "observed_depth_correct": sum(1 for c in base_cells if c["claimed"] == c["level"]), "of": len(base_cells),
                     "previously_too_deep_cells_now_credited_at_or_below_the_evidence": sum(1 for c in prior_now if rank(c["accepted"]) <= rank(c["level"])),
                     "previously_too_deep_cells_now_still_credited_too_deep": sum(1 for c in prior_now if rank(c["accepted"]) > rank(c["level"])),
                     "previously_too_deep_cells_now_not_credited_at_all": sum(1 for c in prior_now if c["accepted"] == "unspecified")},
        "per_cell": _per_cell(cells),
        "stronger_than_required": {"met": sum(1 for c in cells if rank(c["level"]) > rank(c["required"]) and c["verdict"] == "met"), "of": sum(1 for c in cells if rank(c["level"]) > rank(c["required"]))},
        "depth_payload_violations": shared["depth_payload_violations"], "leak_token_hits": shared["leak_token_hits"],
        "failed_jobs": shared["failed_jobs"], "missing_basis_discards": sum(1 for c in cells if c["discard"] == "missing_evidence_basis"),
    }
    g, b = summary["gate"], summary["baseline"]
    reduction = None if b["false_positive_met"] == 0 else round(1 - g["false_positive_met"] / b["false_positive_met"], 3)
    violations = (shared["D_quote_gate"]["accepted_depths_failing_the_gate"] + shared["E_binding"]["accepted_not_naming_own_skill"] + shared["E_binding"]["accepted_not_work_evidence"]
                  + shared["E_binding"]["unknown_or_duplicate_check_id"] + (n - D) + summary["depth_payload_violations"] + summary["leak_token_hits"])
    summary["acceptance"] = {
        "rule": "hard gate: nothing credited above its ceiling, no `met` on named-only/familiar evidence; quality: zero structural violations and false-positive depth cases reduced by >= 50% against the frozen baseline",
        "no_credit_above_ceiling": g["credited_above_ceiling"] == 0, "no_met_on_named_only_or_familiar": g["met_on_named_only_or_familiar"] == 0,
        "structural_violations": violations, "false_positive_reduction": reduction,
        "false_positive_before": b["false_positive_met"], "false_positive_after": g["false_positive_met"],
        "accepted": bool(g["credited_above_ceiling"] == 0 and g["met_on_named_only_or_familiar"] == 0 and violations == 0 and n == 90 and summary["failed_jobs"] == 0
                         and (reduction is None or reduction >= 0.5) and g["false_positive_met"] == 0)}
    if write:
        ANALYSIS.write_text(json.dumps(summary, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _count(xs: List[Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for x in xs:
        out[str(x)] = out.get(str(x), 0) + 1
    return dict(sorted(out.items()))


def _per_cell(cells: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    d: Dict[str, Dict[str, Any]] = {}
    for c in cells:
        k = f"{c['profile']}|{c['skill']}"
        e = d.setdefault(k, {"profile": c["profile"], "level": c["level"], "skill": c["skill"], "required": c["required"], "truth": c["truth"], "runs": 0, "basis": {}, "claimed": {},
                             "ceiling": {}, "accepted": {}, "verdicts": {}})
        e["runs"] += 1
        for f, key in (("basis", "basis"), ("claimed", "claimed"), ("ceiling", "ceiling"), ("accepted", "accepted"), ("verdicts", "verdict")):
            e[f][str(c[key])] = e[f].get(str(c[key]), 0) + 1
    return sorted(d.values(), key=lambda e: (list(DEPTH_ORDER).index(e["level"]), [p.key for p in dm.PROFILES].index(e["profile"]), e["skill"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "analyze"])
    ap.add_argument("--runs", type=int, default=6)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.runs, a.workers)
    else:
        s = analyze()
        print(json.dumps({k: v for k, v in s.items() if k != "per_cell"}, indent=1, default=str))
