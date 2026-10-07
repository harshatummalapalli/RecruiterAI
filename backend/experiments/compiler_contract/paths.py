"""Path-structure test, against the UNCHANGED compiler.

The compiler reads only the global intent, so `sourcing_paths` cannot affect it. To measure what that costs, each path's effective view
(global + that path's overrides, via the frozen `effective_view`) is compiled by the SAME compiler and compared to the plan compiled from the
whole intent:
  leaves/rows the path needs that the whole-intent plan lacks   -> the plan is WEAKER than that path
  leaves/rows the whole-intent plan has that the path does not  -> the plan is STRONGER than that path (a path requirement applied to everyone)
A path-aware plan would be an OR over the per-path plans; the union below shows how far the flat plan is from it."""

from __future__ import annotations

from typing import Any, Dict, List

from backend.experiments.compiler_contract import signature as S
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent, effective_view
from backend.services.search_compiler import compile_intent


def path_intent(intent: ExperimentalHiringIntent, path_id: str) -> ExperimentalHiringIntent:
    v = effective_view(intent, path_id)
    d = intent.model_dump()

    def dump(x):
        if x is None:
            return None
        if isinstance(x, list):
            return [i.model_dump() for i in x]
        return x.model_dump()

    d["seniority"] = dump(v["seniority"])
    d["experience"] = dump(v["experience"])
    d["location"] = dump(v["location"])
    d["skills"] = dump(v["skills"])
    d["domain"] = dump(v["domain"])
    d["sourcing_paths"] = []
    d["reconciliations"] = []
    return ExperimentalHiringIntent.model_validate(d)


def compare(intent: ExperimentalHiringIntent) -> Dict[str, Any]:
    if not intent.sourcing_paths:
        return {"has_paths": False}
    whole = compile_intent(intent)
    wsig = S.signature(whole)
    per_path: List[Dict[str, Any]] = []
    union_leaves = set()
    for p in intent.sourcing_paths:
        pl = compile_intent(path_intent(intent, p.id))
        psig = S.signature(pl)
        union_leaves |= psig["leaves"]
        per_path.append({
            "path": p.id,
            "strategy": p.strategy,
            "path_plan_leaves": [list(x) for x in sorted(psig["leaves"])],
            "needed_by_path_but_absent_from_plan": [list(x) for x in sorted(psig["leaves"] - wsig["leaves"])],
            "in_plan_but_not_needed_by_path": [list(x) for x in sorted(wsig["leaves"] - psig["leaves"])],
            "rows_needed_by_path_absent_from_plan": sorted({r[0] for r in psig["audit"]} - {r[0] for r in wsig["audit"]}),
            "rows_in_plan_not_in_path": sorted({r[0] for r in wsig["audit"]} - {r[0] for r in psig["audit"]}),
            "path_plan_equals_whole_plan": psig["tree"] == wsig["tree"],
        })
    return {
        "has_paths": True,
        "whole_plan_leaves": [list(x) for x in sorted(wsig["leaves"])],
        "plan_mentions_any_path": any("path" in r[0].lower() for r in wsig["audit"]),
        "paths": per_path,
        "union_of_path_leaves": [list(x) for x in sorted(union_leaves)],
        "whole_plan_is_flat_and_of_global_atoms_only": True,
    }
