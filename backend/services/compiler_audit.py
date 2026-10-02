"""Phase 4 — routing + execution-provenance (wiring + traceability only).

Two narrow jobs, no behavior change, no CrustData, no live retrieval:

1. judge_checklist(plan): the semantic requirements the compiler routed to
   downstream verification, in the (tier, signal_text) shape RequirementJudge
   already consumes. The judge still decides whether a candidate satisfies them;
   this only says WHAT needs verifying. The texts are recruiter-meaning
   ("product vision", "previous Java experience") — never provider syntax.

2. build_audit_record(...): the execution-provenance record for a search —
   intent/plan/version hashes + the compiled plan + requirements grouped by how
   they are enforced + warnings. Lets "why did these candidates come back?" be
   answered from the exact intent + compiler/capability/taxonomy versions +
   compiled plan that produced the search.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.models.structured_intent import StructuredHiringIntent
from backend.services import crustdata_capabilities as cap
from backend.services import role_family_taxonomy as tax
from backend.services.search_compiler import COMPILER_VERSION, CompiledPlan, canonicalize

# compiler audit route -> execution category
_ROUTE_CATEGORY = {
    "provider_hard_filter": "provider_enforced",
    "admission_level_fit": "admission_enforced",
    "downstream_evidence": "downstream_verified",
    "context_or_evidence": "context_only",
    "disclose": "unverifiable",
}

# recruiter-intent strength -> judge tier (judge already groups core/supporting/differentiator)
_STRENGTH_TIER = {"required": "core", "preferred": "supporting", "context": "differentiator"}

_PREFIXES = ("evidence:", "skill:", "skill_any_of:", "company:")


def _semantic_name(source: str) -> str:
    for p in _PREFIXES:
        if source.startswith(p):
            return source[len(p):]
    return source


def judge_checklist(plan: CompiledPlan) -> List[Tuple[str, str]]:
    """(tier, signal_text) pairs for everything routed to downstream verification.
    Matches RequirementJudge's existing tiered input; texts are semantic only."""
    out: List[Tuple[str, str]] = []
    for c in plan.audit:
        if c.route == "downstream_evidence":
            out.append((_STRENGTH_TIER.get(c.strength, "differentiator"), _semantic_name(c.source)))
    return out


def intent_hash(intent: StructuredHiringIntent) -> str:
    payload = json.dumps(intent.model_dump(exclude_none=True), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def plan_hash(plan: CompiledPlan) -> str:
    payload = repr(canonicalize(plan.filter_tree))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _requirements_by_category(plan: CompiledPlan) -> Dict[str, List[str]]:
    buckets: Dict[str, List[str]] = {v: [] for v in dict.fromkeys(_ROUTE_CATEGORY.values())}
    for c in plan.audit:
        category = _ROUTE_CATEGORY.get(c.route, "unverifiable")
        buckets[category].append(c.source)
    return buckets


def build_audit_record(
    intent: StructuredHiringIntent,
    plan: CompiledPlan,
    search_id: Optional[str] = None,
    confirmation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Deterministic execution-provenance record. Same intent + versions ->
    identical record (including hashes)."""
    return {
        "search_id": search_id,
        "confirmation_id": confirmation_id,
        "intent_hash": intent_hash(intent),
        "plan_hash": plan_hash(plan),
        "compiler_version": COMPILER_VERSION,
        "capability_map_version": cap.CAPABILITY_MAP_VERSION,
        "taxonomy_version": tax.TAXONOMY_VERSION,
        "retrieval_title_family": list(plan.retrieval_title_family),
        "compiled_provider_plan": plan.filter_tree,
        "requirements": _requirements_by_category(plan),
        "downstream_checklist": [{"tier": t, "requirement": s} for t, s in judge_checklist(plan)],
        "warnings": list(plan.warnings),
    }


def persist_audit(record: Dict[str, Any], out_dir: str) -> str:
    """Write the audit record as JSON. Shadow-only helper; not wired into the
    live pipeline. Returns the path written."""
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    name = record.get("search_id") or record.get("plan_hash") or "audit"
    path = d / f"{name}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)
