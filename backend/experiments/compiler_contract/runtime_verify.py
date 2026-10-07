"""Offline RUNTIME-INTEGRATION verification of the LIVE compiler plus the downstream context (no model, no provider, no scoring).

For each frozen intent, with the verbatim JD / brief it was extracted from:
  1. compile (live) -> per-path downstream contexts
  2. remove every schema atom -> recompile -> rebuild the contexts: an atom that changes NOTHING downstream did not survive the compiler boundary
  3. check where each atom landed: a global atom reaches EVERY path that inherits it (decided independently of the compiler, from the frozen
     inheritance rule), a path atom reaches ONLY its own path, and the entry kind agrees with the atom's fate
  4. audit hard-filter provenance: every provider-enforced atom rests on a source / approved-normalization provenance
    python -m backend.experiments.compiler_contract.runtime_verify
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

from backend.experiments.compiler_contract import loader
from backend.experiments.compiler_contract.atoms import Atom, enumerate_atoms
from backend.experiments.compiler_contract.signature import leaves
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent
from backend.services import compiler_audit
from backend.services.downstream_context import (ADMISSION, JUDGE_EXCLUSION, JUDGE_REQUIREMENT, JUSTIFIED_DROP, PATH, PREFERENCE, PROVIDER_ENFORCED, RECORD,
                                                 UNRESOLVED_ITEM, DownstreamContext, build_downstream_contexts, legacy_consumer_gaps, to_judge_signals)
from backend.services.search_compiler import COMPILER_VERSION, CONTRACT_VERSION, compile_intent
from backend.services.source_provenance import SourceTexts

OUT = Path(__file__).resolve().parent / "results" / "runtime"
HARD_OK_STATES = {"source", "knowledge"}                      # (+ "unrecorded" only in a legacy intent)
_FATE_KINDS = {"ENFORCED": {PROVIDER_ENFORCED}, "NORMALIZED": {PROVIDER_ENFORCED}, "VERIFIED_DOWNSTREAM": {JUDGE_REQUIREMENT, JUDGE_EXCLUSION, ADMISSION},
               "PREFERENCE_CONTEXT": {PREFERENCE}, "UNRESOLVED": {UNRESOLVED_ITEM}, "DROPPED_WITH_JUSTIFICATION": {RECORD, JUSTIFIED_DROP}}


def signature(ctxs: List[DownstreamContext]) -> str:
    return json.dumps([c.to_dict() for c in ctxs], sort_keys=True, default=str)


def _owns(entry, atom: Atom) -> bool:
    truncated = atom.label.endswith("…")
    same = entry.value.startswith(atom.label[:-1]) if truncated else entry.value == atom.label
    # (a reconciliation's scope is its own `path_id`, which the schema enumerator does not carry on the atom: match it by concept and value)
    return entry.concept == atom.concept and (entry.scope == atom.scope or atom.concept == "reconciliation") and same


def applies_in_path(atom: Atom, intent: ExperimentalHiringIntent, path_id: str) -> bool:
    """INDEPENDENT of the compiler: does this atom apply in this path? A path atom: only in its own path. A global atom: in every path that does not
    override it (a singleton the path states replaces the global one; a same-named skill or domain replaces)."""
    if atom.scope != "global":
        return atom.scope == f"path:{path_id}"
    p = next(p for p in intent.sourcing_paths if p.id == path_id)
    c = atom.concept
    if c.startswith("seniority."):
        return p.seniority is None
    if c.startswith("experience."):
        return p.experience is None
    if c.startswith("location."):
        return p.location is None
    if c in ("skill", "skill.proficiency"):
        name = atom.label.split(" = ")[0].strip().lower()
        return not any(s.name.strip().lower() == name for s in p.skills)
    if c == "domain":
        prefix = atom.label.rstrip("…").strip().lower()
        return not any(d.name.strip().lower().startswith(prefix) for d in p.domain)
    return True


def verify_intent(intent: ExperimentalHiringIntent, sources: SourceTexts) -> Dict[str, Any]:
    plan = compile_intent(intent, sources)
    ctxs = build_downstream_contexts(plan)
    base = signature(ctxs)
    d = intent.model_dump()
    path_ids = [c.path_id for c in ctxs]
    rows: List[Dict[str, Any]] = []
    for a in enumerate_atoms(intent):
        ab = compile_intent(ExperimentalHiringIntent.model_validate(a.ablate(d)), sources)
        silent = signature(build_downstream_contexts(ab)) == base
        row: Dict[str, Any] = {**a.row(), "silent_at_boundary": silent, "problems": []}
        if a.kind == "METADATA" and a.concept == "provenance.basis":
            # provenance is not an atom with a fate: it must travel as the provenance column of every entry
            row["problems"] += [f"{c.path_id}: entry without provenance" for c in ctxs for e in c.entries if not e.provenance.get("state")]
            rows.append(row)
            continue
        got: Dict[Any, list] = {c.path_id: [e for e in c.entries if _owns(e, a)] for c in ctxs}
        expected = [None] if not intent.sourcing_paths else [p for p in path_ids if applies_in_path(a, intent, p)]
        if a.concept == "sourcing_path":
            expected = [a.scope.split(":", 1)[1]]
        if a.concept == "role_archetype":
            expected = path_ids
        if a.concept == "reconciliation":
            from backend.experiments.compiler_contract.atoms import _short
            rec = next(r for r in intent.reconciliations if f"{r.action}: {_short(r.topic, 60)}" == a.label)
            expected = path_ids if rec.path_id is None else [rec.path_id]
        row["expected_contexts"] = expected
        row["reached_contexts"] = [k for k, v in got.items() if v]
        if sorted(map(str, row["reached_contexts"])) != sorted(map(str, expected)):
            row["problems"].append(f"reached {row['reached_contexts']}, expected {expected}")
        for k, es in got.items():
            for e in es:
                if e.kind not in _FATE_KINDS.get(e.fate, set()) and e.kind != PATH:
                    row["problems"].append(f"{k}: fate {e.fate} landed as {e.kind}")
                if not e.provenance.get("state"):
                    row["problems"].append(f"{k}: no provenance")
        if silent:
            row["problems"].append("no downstream context depends on this atom")
        row["fates"] = sorted({e.fate for es in got.values() for e in es})
        row["kinds"] = sorted({e.kind for es in got.values() for e in es})
        rows.append(row)
    # an atom stated in one path must never appear in another path's context
    leaks = [f"{c.path_id}: {e.atom_id}" for c in ctxs for e in c.entries if e.scope.startswith("path:") and c.path_id and e.scope != f"path:{c.path_id}"]
    return {"rows": rows, "plan": plan, "contexts": ctxs, "leaks": leaks}


def hard_filter_provenance(plan, intent) -> Dict[str, Any]:
    """Every provider-enforced atom's provenance, in the plan as compiled (with sources)."""
    ok_states = HARD_OK_STATES | ({"unrecorded"} if plan.provenance_mode == "legacy" else set())
    records = list(plan.atom_audit) + [a for p in plan.paths for a in p.atom_audit]
    enforced = [a for a in records if a.fate in ("ENFORCED", "NORMALIZED")]
    bad = sorted({f"{a.atom_id}: {a.provenance['state']}" for a in enforced if a.provenance["state"] not in ok_states})
    by_concept: Dict[str, Counter] = defaultdict(Counter)
    blocked: Dict[str, Counter] = defaultdict(Counter)
    for a in {x.atom_id: x for x in records}.values():
        if a.fate in ("ENFORCED", "NORMALIZED"):
            by_concept[a.concept][a.provenance["state"] + ("*" if a.provenance.get("classified") else "")] += 1
        elif a.provenance["state"] in ("model_only", "absent", "comparison", "unverified_quote"):
            blocked[a.concept][a.provenance["state"]] += 1
    return {"violations": bad, "enforced_by_concept": {k: dict(v) for k, v in by_concept.items()}, "blocked_by_concept": {k: dict(v) for k, v in blocked.items()}}


def run() -> Dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    summary: Dict[str, Any] = {"compiler_version": COMPILER_VERSION, "contract_version": CONTRACT_VERSION, "runs": {}}
    for (role, n), it in loader.load_all().items():
        res = verify_intent(it, loader.sources_for(role))
        plan, ctxs = res["plan"], res["contexts"]
        prov = hard_filter_provenance(plan, it)
        record = {
            "role": role, "run": n, "atoms": res["rows"], "leaks": res["leaks"], "hard_filter_provenance": prov,
            "contexts": [{"path_id": c.path_id, "strategy": c.strategy, "entries": len(c.entries), "kinds": dict(Counter(e.kind for e in c.entries)),
                          "provider_leaves": [list(x) for x in sorted(leaves(c.provider_plan))],
                          "judge_signals": {k: len(v) for k, v in to_judge_signals(c).items()},
                          "legacy_gaps": dict(Counter(g["gap"] for g in legacy_consumer_gaps(c)))} for c in ctxs],
            "downstream_contexts": [c.to_dict() for c in ctxs],
        }
        (OUT / f"{role}_run{n}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        summary["runs"][f"{role}/{n}"] = {
            "atoms": len(res["rows"]), "silent_at_boundary": sum(r["silent_at_boundary"] for r in res["rows"]),
            "problems": sum(len(r["problems"]) for r in res["rows"]), "leaks": len(res["leaks"]), "hard_filter_violations": len(prov["violations"]),
            "contexts": len(ctxs),
        }
    (OUT.parent / "runtime_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


if __name__ == "__main__":
    s = run()
    tot: Counter = Counter()
    for v in s["runs"].values():
        for k in ("atoms", "silent_at_boundary", "problems", "leaks", "hard_filter_violations"):
            tot[k] += v[k]
    print(dict(tot))
