"""Field fate by counterfactual ablation, against the UNCHANGED compiler.

For each atom: recompile with only that atom removed (or reset), diff the whole output; the delta is the atom's destination. See
CONTRACT_EXPECTATIONS.md section 1 for the rules, which were fixed before any output was examined."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.experiments.compiler_contract import signature as S
from backend.experiments.compiler_contract.atoms import Atom, enumerate_atoms
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent
from backend.services.search_compiler import CompiledPlan, compile_intent

FATES = ("ENFORCED", "VERIFIED_DOWNSTREAM", "PREFERENCE_CONTEXT", "NORMALIZED", "UNRESOLVED", "DROPPED_WITH_JUSTIFICATION", "SILENTLY_DROPPED")

_ROUTE_FATE = {
    "provider_hard_filter": "ENFORCED",
    "downstream_evidence": "VERIFIED_DOWNSTREAM",
    "admission_level_fit": "VERIFIED_DOWNSTREAM",
    "context_or_evidence": "PREFERENCE_CONTEXT",
    "disclose": "UNRESOLVED",
}


def _leaf_values(leaf_list) -> List[str]:
    import json
    vals: List[str] = []
    for _f, _t, v in leaf_list:
        x = json.loads(v)
        vals += [str(i) for i in x] if isinstance(x, list) else [str(x)]
    return vals


def classify(atom: Atom, dl: Dict[str, Any], base_plan: CompiledPlan) -> Dict[str, Any]:
    """Map an atom's destination delta to a fate (+ deviation flags)."""
    notes: List[str] = []
    rows = dl["audit_lost"]
    routes = sorted({r[2] for r in rows})
    flags: List[str] = []
    if dl["empty"]:
        # DROPPED_WITH_JUSTIFICATION needs an explicit audit statement that THIS atom was dropped on purpose: a note or warning that names the
        # atom AND says it is dropped / ignored / not enforced. A note that merely contains the same word (a global row for the same value) is not
        # a justification. The compiler emits no such statement, so none is expected.
        needle = atom.label.lower()
        marker = ("dropped", "ignored", "discard", "not enforced", "not used")
        texts = [(c.note or "").lower() for c in base_plan.audit] + [w.lower() for w in base_plan.warnings]
        reasoned = any(needle and needle in t and any(m in t for m in marker) for t in texts)
        fate = "DROPPED_WITH_JUSTIFICATION" if reasoned else "SILENTLY_DROPPED"
        return {"fate": fate, "routes": routes, "flags": flags, "destination": None, "delta": dl}
    if dl["leaves_lost"]:
        fate = "ENFORCED"
        provider_vals = {v.lower() for v in _leaf_values(dl["leaves_lost"])}
        label = atom.label.lower()
        if dl["normalizations_changed"]:
            fate = "NORMALIZED"
            notes.append("alias normalization recorded")
        elif atom.concept in ("role_family", "education.degree") and provider_vals and provider_vals != {label}:
            fate = "NORMALIZED"
            notes.append("provider value differs from intent value")
        if atom.strength in ("preferred", "context"):
            flags.append("STRENGTHENED:preference->hard_filter")
        if atom.scope != "global":
            flags.append("SCOPE_CHANGED:path_atom_applied_globally")
    elif rows:
        fates = {_ROUTE_FATE.get(r, "UNRESOLVED") for r in routes}
        fate = "ENFORCED" if "ENFORCED" in fates else next(f for f in ("VERIFIED_DOWNSTREAM", "PREFERENCE_CONTEXT", "UNRESOLVED") if f in fates)
        if atom.strength == "required" and fate == "PREFERENCE_CONTEXT":
            flags.append("WEAKENED:required->context_only")
    else:  # only a warning / checklist / title / normalization / tree-shape changed
        fate = "VERIFIED_DOWNSTREAM" if (dl["checklist_lost"] or dl["checklist_gained"]) else "NORMALIZED" if dl["normalizations_changed"] else "UNRESOLVED"
    return {"fate": fate, "routes": routes, "flags": flags, "notes": notes,
            "destination": {"leaves": [list(x) for x in dl["leaves_lost"]], "audit_sources": [r[0] for r in rows], "audit_routes": routes,
                            "capability": sorted({str(r[5]) for r in rows})},
            "delta": dl}


def analyse(intent: ExperimentalHiringIntent) -> Dict[str, Any]:
    base_plan = compile_intent(intent)
    base = S.signature(base_plan)
    d = intent.model_dump()
    out: List[Dict[str, Any]] = []
    for a in enumerate_atoms(intent):
        abl_plan = compile_intent(ExperimentalHiringIntent.model_validate(a.ablate(d)))
        dl = S.delta(base, S.signature(abl_plan))
        res = classify(a, dl, base_plan)
        res.pop("delta")
        row = a.row()
        row.update(res)
        out.append(row)
    return {"atoms": out, "plan": plan_record(base_plan)}


def plan_record(plan: CompiledPlan) -> Dict[str, Any]:
    from backend.services.compiler_audit import judge_checklist
    return {
        "filter_tree": plan.filter_tree,
        "leaves": [list(x) for x in sorted(S.leaves(plan.filter_tree))],
        "retrieval_title_family": plan.retrieval_title_family,
        "audit": [{"source": c.source, "strength": c.strength, "route": c.route, "provider_fields": c.provider_fields,
                   "temporal": c.temporal, "capability": c.capability, "note": c.note} for c in plan.audit],
        "warnings": plan.warnings,
        "normalizations": plan.normalizations,
        "downstream_checklist": [{"tier": t, "requirement": s} for t, s in judge_checklist(plan)],
    }
