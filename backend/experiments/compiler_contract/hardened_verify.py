"""INDEPENDENT verification of the hardened compiler (offline; no model, no provider).

The compiler declares a fate for every atom (`plan.atom_audit`). This module does not trust that: it re-enumerates the intent's atoms from the SCHEMA
(`atoms.enumerate_atoms`, the same enumerator used for the baseline), removes each atom, recompiles with the LIVE compiler, and diffs the whole output.
  * silent drop  = the whole output (provider plan, every audit row, the checklists, the per-atom audit, the paths) does not depend on the atom
  * consistent   = the declared fate matches what the delta shows (an ENFORCED atom's leaf disappears; a downstream atom's row disappears; ...)
  * one fate     = the atom's record(s) carry exactly one fate from the closed set
    python -m backend.experiments.compiler_contract.hardened_verify
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.experiments.compiler_contract import loader
from backend.experiments.compiler_contract.atoms import Atom, enumerate_atoms
from backend.experiments.compiler_contract.signature import leaves
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent
from backend.services import compiler_audit
# This module verifies compiler CONTRACT-1 as it was (the pinned snapshot, no source text). The live compiler, with sources and the downstream context, is verified by runtime_verify.py.
from backend.experiments.compiler_contract.compiler_contract1_snapshot import COMPILER_VERSION, CONTRACT_VERSION, FATES, CompiledPlan, canonicalize, compile_intent

OUT = Path(__file__).resolve().parent / "results"


def _rec_key(a) -> tuple:
    return (a.atom_id, a.fate, a.destination, a.justification, a.value, a.strength, a.proficiency, a.relationship,
            json.dumps(a.provenance, sort_keys=True), json.dumps(a.components, sort_keys=True))


def signature(plan: CompiledPlan) -> Dict[str, Any]:
    paths = plan.paths
    checklists = ({p.path_id: (tuple(compiler_audit.judge_checklist(plan, p.path_id)), tuple(compiler_audit.exclusion_checklist(plan, p.path_id))) for p in paths}
                  if paths else {"": (tuple(compiler_audit.judge_checklist(plan)), tuple(compiler_audit.exclusion_checklist(plan)))})
    return {
        "leaves": frozenset(leaves(plan.filter_tree)),
        "tree": repr(canonicalize(plan.filter_tree)),
        "paths": tuple((p.path_id, repr(canonicalize(p.filter_tree))) for p in paths),
        "audit": frozenset((c.source, c.strength, c.route, tuple(c.provider_fields), c.temporal, c.capability, c.note, c.scope, c.semantic) for c in plan.audit),
        "checklists": json.dumps({k: [list(map(list, v[0])), list(v[1])] for k, v in checklists.items()}, sort_keys=True),
        "atoms": {a.atom_id: _rec_key(a) for a in plan.atom_audit},
        "warnings": tuple(plan.warnings),
        "titles": tuple(plan.retrieval_title_family),
    }


def delta(base: Dict[str, Any], other: Dict[str, Any]) -> Dict[str, Any]:
    lost = sorted(set(base["atoms"]) - set(other["atoms"]))
    changed = sorted(k for k in set(base["atoms"]) & set(other["atoms"]) if base["atoms"][k] != other["atoms"][k])
    d = {
        "leaves_lost": sorted(base["leaves"] - other["leaves"]),
        "audit_lost": sorted(base["audit"] - other["audit"], key=repr),
        "atoms_lost": lost,
        "atoms_changed": changed,
        "paths_changed": base["paths"] != other["paths"],
        "tree_changed": base["tree"] != other["tree"],
        "checklists_changed": base["checklists"] != other["checklists"],
        "warnings_changed": base["warnings"] != other["warnings"],
    }
    d["empty"] = not (d["leaves_lost"] or d["audit_lost"] or lost or changed or d["paths_changed"] or d["tree_changed"] or d["checklists_changed"] or d["warnings_changed"])
    return d


_DOWNSTREAM_ROUTES = {"downstream_evidence", "downstream_exclusion", "admission_level_fit"}


def _owns(rec, atom: Atom) -> bool:
    """Does this compiler record belong to this schema atom? By concept, scope and value (the enumerator shortens long values with an ellipsis).
    Not by id: ids are positional and shift when an earlier atom is removed."""
    truncated = atom.label.endswith("…")
    same_value = rec.value.startswith(atom.label[:-1]) if truncated else rec.value == atom.label
    return rec.concept == atom.concept and rec.scope == atom.scope and same_value


def verify_atom(atom: Atom, base_plan: CompiledPlan, base_sig, dl) -> Dict[str, Any]:
    ids = set(dl["atoms_lost"]) | set(dl["atoms_changed"])
    recs = [a for a in base_plan.atom_audit if _owns(a, atom)]
    # an atom must have its own record; the records it touched are the ones it owns, not every record its removal re-indexed or re-annotated
    if not recs:
        recs = [a for a in base_plan.atom_audit if a.atom_id in ids and a.concept == atom.concept]
    fates = sorted({r.fate for r in recs})
    row: Dict[str, Any] = atom.row()
    row.update({"declared_fates": fates, "records": [r.atom_id for r in recs], "silent": dl["empty"]})
    if dl["empty"]:
        row.update({"fate": "SILENTLY_DROPPED", "consistent": False, "why": "the output does not depend on this atom"})
        return row
    if atom.concept == "provenance.basis":
        row.update({"fate": "CARRIED", "consistent": bool(dl["atoms_changed"]), "why": "provenance is a column of every atom record"})
        return row
    if not recs:
        # the atom changed provider leaves / rows without owning a record: acceptable only if a leaf or row moved
        row.update({"fate": "NO_RECORD", "consistent": False, "why": "output moved but no atom record owns this atom"})
        return row
    fate = fates[0] if len(fates) == 1 else "MULTIPLE"
    ok = len(fates) == 1 and fate in FATES
    why = ""
    if ok and fate in ("ENFORCED", "NORMALIZED"):
        ok = bool(dl["leaves_lost"] or dl["paths_changed"] or dl["tree_changed"])
        why = "provider leaf moved" if ok else "declared enforced but no provider leaf depends on it"
    elif ok and fate in ("VERIFIED_DOWNSTREAM", "PREFERENCE_CONTEXT"):
        ok = bool(dl["audit_lost"] or dl["checklists_changed"])
        why = "an audit row / checklist item moved" if ok else "declared routed but no audit row or checklist item depends on it"
    elif ok:  # UNRESOLVED / DROPPED_WITH_JUSTIFICATION
        ok = all(r.justification.strip() for r in recs)
        why = "carries a justification" if ok else "no justification"
    row.update({"fate": fate, "consistent": ok, "why": why})
    return row


def verify_intent(intent: ExperimentalHiringIntent) -> Dict[str, Any]:
    base_plan = compile_intent(intent)
    base = signature(base_plan)
    d = intent.model_dump()
    rows = []
    for a in enumerate_atoms(intent):
        ab = compile_intent(ExperimentalHiringIntent.model_validate(a.ablate(d)))
        rows.append(verify_atom(a, base_plan, base, delta(base, signature(ab))))
    ids = [a.atom_id for a in base_plan.atom_audit]
    return {"atoms": rows, "plan": base_plan, "duplicate_atom_ids": sorted(i for i, n in Counter(ids).items() if n > 1),
            "bad_fates": sorted({a.fate for a in base_plan.atom_audit} - set(FATES)),
            "records_without_justification": [a.atom_id for a in base_plan.atom_audit if not a.justification.strip()]}


def invented_model_only_hard_filters(intent: ExperimentalHiringIntent, plan: CompiledPlan) -> List[str]:
    """Independent audit of the provenance gate. A provider leaf is INVENTED when it rests on (a) an atom whose only basis is model inference, or
    (b) a location state/country that its own cited source text does not contain (and no approved normalization supplies)."""
    out: List[str] = []
    for rec in plan.atom_audit:
        if rec.fate in ("ENFORCED", "NORMALIZED") and rec.provenance["state"] == "model_only":
            out.append(f"{rec.atom_id}: enforced on model-only provenance")
    locs = [(intent.location, "global")] if intent.location else []
    locs += [(p.location, f"path:{p.id}") for p in intent.sourcing_paths if p.location]
    quotes = " ".join(" ".join((loc.basis.quote or "").casefold().split()) for loc, _ in locs if loc.basis)
    for lf in leaves(plan.filter_tree):
        fld, _typ, val = lf
        if fld.endswith("location.state") or fld.endswith("location.country"):
            for v in json.loads(val):
                if locs and all(l.basis for l, _ in locs) and " ".join(v.casefold().split()) not in quotes:
                    # a country-wide `countries` entry is its own atom (sources-level); only entries-derived values are component-gated
                    if not any(v in (l.countries or []) for l, _ in locs):
                        out.append(f"{fld}={v}: not in any cited location source text")
    return out


def run() -> Dict[str, Any]:
    (OUT / "hardened").mkdir(parents=True, exist_ok=True)
    summary: Dict[str, Any] = {"compiler_version": COMPILER_VERSION, "contract_version": CONTRACT_VERSION, "runs": {}}
    for (role, n), it in loader.load_all().items():
        res = verify_intent(it)
        plan: CompiledPlan = res["plan"]
        invented = invented_model_only_hard_filters(it, plan)
        record = {
            "role": role, "run": n, "atoms": res["atoms"], "invented_model_only_hard_filters": invented,
            "duplicate_atom_ids": res["duplicate_atom_ids"], "bad_fates": res["bad_fates"], "records_without_justification": res["records_without_justification"],
            "filter_tree": plan.filter_tree, "leaves": [list(x) for x in sorted(leaves(plan.filter_tree))],
            "paths": [{"path_id": p.path_id, "label": p.label, "strategy": p.strategy, "filter_tree": p.filter_tree} for p in plan.paths],
            "audit_record": compiler_audit.build_audit_record(it, plan, search_id=f"{role}-run{n}"),
            "warnings": plan.warnings,
        }
        (OUT / "hardened" / f"{role}_run{n}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        summary["runs"][f"{role}/{n}"] = {
            "atoms": len(res["atoms"]), "silently_dropped": sum(a["silent"] for a in res["atoms"]),
            "inconsistent": sum(1 for a in res["atoms"] if not a["silent"] and not a["consistent"]),
            "invented_model_only_hard_filters": len(invented), "duplicate_atom_ids": len(res["duplicate_atom_ids"]),
            "fates": dict(Counter(a["fate"] for a in res["atoms"])),
        }
    (OUT / "hardened_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


if __name__ == "__main__":
    s = run()
    tot = Counter()
    for k, v in s["runs"].items():
        tot["atoms"] += v["atoms"]; tot["silent"] += v["silently_dropped"]; tot["inconsistent"] += v["inconsistent"]; tot["invented"] += v["invented_model_only_hard_filters"]
    print(dict(tot))
