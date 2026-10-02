"""Shadow-mode integration: compute what the compiler WOULD produce for a real
search and log how it diverges from the legacy plan — WITHOUT ever affecting the
live search or sending the compiled plan to CrustData.

Absolute safety contract: any failure here is logged and swallowed; the legacy
search continues normally. Controlled by SEARCH_COMPILER_SHADOW_ENABLED (default
off). Zero CrustData credits — the only incremental cost is one intake
extraction call, and only when enabled.

The log distinguishes REPRESENTATION differences (e.g. a canonical city alias —
impact: none) from ENFORCEMENT differences (e.g. a hard company filter removed —
impact: material), and tags WHY the compiler differs, so the shadow dataset is a
learning instrument, not a pile of JSON diffs.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SHADOW_DIR = Path("output/compiler_shadow")
EXTRACTION_MODEL = "gpt-6.1-sol"


def is_enabled() -> bool:
    return os.environ.get("SEARCH_COMPILER_SHADOW_ENABLED", "false").strip().lower() in ("1", "true", "yes")


def _leaves(tree: Dict[str, Any], acc: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if isinstance(tree, dict) and "op" in tree:
        for c in tree.get("conditions", []):
            _leaves(c, acc)
    elif isinstance(tree, dict):
        acc.append(tree)
    return acc


def _titles(tree: Dict[str, Any]) -> set:
    return {str(l.get("value")) for l in _leaves(tree, []) if str(l.get("field", "")).endswith("current.title") and l.get("type") == "(.)"}


def categorize_divergence(legacy_tree: Dict[str, Any], compiled_plan) -> List[Dict[str, Any]]:
    """Why the compiler differs from legacy — representation vs enforcement."""
    compiled_tree = compiled_plan.filter_tree
    legacy = _leaves(legacy_tree, [])
    compiled = _leaves(compiled_tree, [])

    def key(l):
        return (str(l.get("field")), l.get("type"), json.dumps(l.get("value"), sort_keys=True, ensure_ascii=False))

    legacy_keys = {key(l) for l in legacy}
    compiled_keys = {key(l) for l in compiled}
    removed = [l for l in legacy if key(l) not in compiled_keys]
    added = [l for l in compiled if key(l) not in legacy_keys]
    out: List[Dict[str, Any]] = []

    def add(category, kind, impact, detail):
        out.append({"category": category, "kind": kind, "impact": impact, "detail": detail})

    # representation: canonical city aliases etc.
    for n in getattr(compiled_plan, "normalizations", []) or []:
        add("provider_surface_normalization", "representation", "none",
            f"{n.get('source_value')} -> {n.get('provider_normalized_value')} ({n.get('normalization')})")

    if any(str(l.get("field", "")).endswith("current.company_name") and l.get("type") == "in" for l in removed):
        add("company_hard_filter_removed", "enforcement", "material", "legacy hard current-company filter not in compiled plan")
    if any(l.get("type") == "geo_distance" for l in removed):
        add("radius_removed", "enforcement", "material", "legacy geo radius not in compiled plan")
    if any(l.get("type") == "geo_distance" for l in added):
        add("radius_added", "enforcement", "material", "compiled added a geo radius")
    if any(str(l.get("field", "")).endswith("current.title") and l.get("type") == "(!)" for l in removed):
        add("seniority_moved_to_admission", "enforcement", "material", "legacy exec-title blocklist dropped; seniority handled at admission")

    lt, ct = _titles(legacy_tree), _titles(compiled_tree)
    if ct and ct != lt:
        add("role_family_added" if not lt else "role_family_changed", "enforcement", "material",
            f"legacy_titles={sorted(lt)} compiled_titles={sorted(ct)}")

    if any(isinstance(c, dict) and c.get("op") == "all_of" for c in compiled_tree.get("conditions", [])):
        add("education_same_entry_grouped", "enforcement", "material", "education compiled as a same-entry all_of group")

    routes = {c.route for c in compiled_plan.audit}
    if "downstream_evidence" in routes:
        add("downstream_verification_added", "enforcement", "material", "requirements routed to the judge for verification")
    if "disclose" in routes or compiled_plan.warnings:
        add("unverifiable_constraint", "enforcement", "disclosed", "; ".join(compiled_plan.warnings) or "constraint cannot be verified from provider data")
    return out


def _legacy_tree(legacy_mapped_plan) -> Dict[str, Any]:
    from backend.providers.crustdata import CrustDataProvider
    prov = CrustDataProvider()
    conds: List[Dict[str, Any]] = []
    for q in getattr(legacy_mapped_plan, "searches", []) or []:
        try:
            conds.extend(prov._build_filter_conditions(q))
        except Exception:  # pragma: no cover - defensive
            pass
    return {"op": "and", "conditions": conds}


def run_shadow(search_id: str, jd_text: str, legacy_mapped_plan, recruiter_brief: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Compute + log the compiled plan and its divergence from legacy. Returns the
    record, or None if disabled or on any failure. NEVER raises; the compiled plan
    is NEVER sent to a provider."""
    if not is_enabled():
        return None
    try:
        from backend.services.structured_intent_extractor import extract_structured_intent
        from backend.services.search_compiler import compile_intent, semantic_diff
        from backend.services import compiler_audit as audit

        si = extract_structured_intent(jd_text, recruiter_brief=recruiter_brief)
        plan = compile_intent(si)
        legacy_tree = _legacy_tree(legacy_mapped_plan)

        record = audit.build_audit_record(si, plan, search_id=search_id)
        record.update({
            "extraction_model": EXTRACTION_MODEL,
            "legacy_plan": legacy_tree,
            "semantic_diff": semantic_diff(legacy_tree, plan.filter_tree),
            "divergence": categorize_divergence(legacy_tree, plan),
            "normalizations": plan.normalizations,
            "legacy_search_result": "untouched",
            "compiled_search_result": None,  # NEVER reaches CrustData in shadow mode
        })
        SHADOW_DIR.mkdir(parents=True, exist_ok=True)
        (SHADOW_DIR / f"{search_id}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("[SHADOW] compiled-plan divergence logged | search_id=%s diffs=%s", search_id, len(record["divergence"]))
        return record
    except Exception:  # absolute isolation — never break a real search
        logger.warning("[SHADOW] compile/log failed (ignored; legacy search unaffected) | search_id=%s", search_id, exc_info=True)
        return None
