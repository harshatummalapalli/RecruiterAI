"""Offline compiler-contract experiment driver. NO model, NO network, NO provider. Reads frozen intents; calls the UNCHANGED compiler.

    python -m backend.experiments.compiler_contract.run_contract baseline    # capture compiled plans + audit records
    python -m backend.experiments.compiler_contract.run_contract analyse     # fate matrix, silent-drop audit, checks, probes
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set

from backend.experiments.compiler_contract import checks, contract, fate, loader, paths, probes, signature as S
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent
from backend.services import compiler_audit, crustdata_capabilities as cap, role_family_taxonomy as tax
from backend.experiments.compiler_contract.legacy_compiler_v1 import COMPILER_VERSION, compile_intent  # BEFORE harness: legacy compiler v1

OUT = Path(__file__).resolve().parent / "results"
REPO = Path(__file__).resolve().parents[3]
PINNED = ["backend/services/search_compiler.py", "backend/services/compiler_audit.py", "backend/services/crustdata_capabilities.py",
          "backend/services/role_family_taxonomy.py", "backend/models/structured_intent.py", "backend/knowledge/seniority.json"]


def file_hashes() -> Dict[str, str]:
    return {p: hashlib.sha256((REPO / p).read_bytes()).hexdigest() for p in PINNED}


def present_paths(value: Any, prefix: str = "") -> Set[str]:
    """Schema-style paths whose value is actually present (not None / empty) in an intent dict."""
    out: Set[str] = set()
    if isinstance(value, dict):
        for k, v in value.items():
            p = f"{prefix}.{k}" if prefix else k
            if v not in (None, [], "", {}):
                out.add(p)
                out |= present_paths(v, p)
    elif isinstance(value, list):
        for v in value:
            if isinstance(v, (dict, list)):
                out |= present_paths(v, prefix + "[]")
    return out


def baseline() -> Dict[str, Any]:
    (OUT / "baseline").mkdir(parents=True, exist_ok=True)
    manifest: Dict[str, Any] = {
        "compiler_version": COMPILER_VERSION, "capability_map_version": cap.CAPABILITY_MAP_VERSION, "taxonomy_version": tax.TAXONOMY_VERSION,
        "compiler_side_file_sha256": file_hashes(), "source_run_file_sha256": loader.source_hashes(),
        "relationship_omission_in_raw_model_output": loader.relationship_omission_in_raw_output(),
        "note": "compiled with the UNCHANGED compiler; no model, no provider, no network",
    }
    union_read: Set[str] = set()
    for (role, n), it in loader.load_all().items():
        plan = compile_intent(it)
        rs = S.read_set(it)
        union_read |= rs
        present = present_paths(it.model_dump())
        unread = sorted(p for p in present if p not in rs and not any(r.startswith(p + ".") or r.startswith(p + "[]") for r in rs))
        rec = {"role": role, "run": n, **fate.plan_record(plan),
               "audit_record": compiler_audit.build_audit_record(it, plan, search_id=f"{role}-run{n}"),
               "fields_read_by_compiler": sorted(rs), "fields_present_but_never_read": unread}
        (OUT / "baseline" / f"{role}_run{n}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest["fields_read_by_compiler_union"] = sorted(union_read)
    (OUT / "baseline_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def analyse() -> Dict[str, Any]:
    intents = loader.load_all()
    runs: Dict[str, Any] = {}
    for (role, n), it in intents.items():
        res = fate.analyse(it)
        pc = paths.compare(it)
        if role == "R1":
            ck = checks.role1(it, res["atoms"], pc)
        elif role == "R2":
            ov = probes.role2_overlay(n)
            ovres = fate.analyse(ov["intent"])
            ck = checks.role2(it, res["atoms"], res["plan"], {"atoms": ovres["atoms"], "plan": ovres["plan"]})
        else:
            ck = checks.role3(it, res["atoms"], res["plan"])
        for a in res["atoms"]:
            exp, why = contract.expected(a)
            a["expected_fates"] = sorted(exp)
            a["expected_why"] = why
            a["matches_expected"] = contract.matches(a["fate"], exp)
            a["gap_type"] = contract.gap_type(a, a["fate"], exp)
            a["concept_key"] = contract.concept_key(a)
        runs[f"{role}/{n}"] = {"atoms": res["atoms"], "paths": pc, "checks": ck, "hard_leaf_count": len(res["plan"]["leaves"]),
                               "plan_leaves": res["plan"]["leaves"]}
    out = {
        "runs": runs,
        "probes": {
            "strength_relationship_sweep": probes.strength_relationship_sweep(),
            "relationship_omission": probes.relationship_omission(),
            "seniority": probes.seniority_probes(),
            "titles": probes.title_probes(),
            "location": probes.location_probes(),
            "exclusions": probes.exclusion_probes(),
            "descriptive_terms": probes.descriptive_term_probe(),
            "capability_notes": probes.capability_notes(),
            "omission_exposure": probes.omission_exposure(),
            "hash_sensitivity": probes.hash_sensitivity(),
            "checklist_sample_R3": probes.checklist_sample("R3", 1),
        },
    }
    (OUT / "contract_analysis.json").write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return out


def main(argv: List[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("baseline", "analyse"):
        print(__doc__)
        return 2
    (baseline if argv[0] == "baseline" else analyse)()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
