"""Role-specific compiler-contract checks (sections 5-7 of the brief), judged CONDITIONALLY.

Each check records (a) whether the stored intent CARRIES the concept (so an extraction miss is not blamed on the compiler), (b) what the unchanged
compiler did, (c) PASS / PARTIAL / FAIL / NOT_TESTABLE, (d) the gap type. Definitions follow CONTRACT_EXPECTATIONS.md section 4."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.experiments.intake_strategy import validators_cross_role as vcr
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent

INPUTS = Path(__file__).resolve().parents[1] / "intake_strategy" / "inputs"
DROPPED = ("SILENTLY_DROPPED",)


def _a(atoms: List[Dict], concept: str, scope: Optional[str] = None, pred=None) -> List[Dict]:
    out = [a for a in atoms if a["concept"] == concept]
    if scope == "global":
        out = [a for a in out if a["scope"] == "global"]
    elif scope == "path":
        out = [a for a in out if a["scope"] != "global"]
    if pred:
        out = [a for a in out if pred(a)]
    return out


def _fates(atoms: List[Dict]) -> Dict[str, int]:
    f: Dict[str, int] = {}
    for a in atoms:
        f[a["fate"]] = f.get(a["fate"], 0) + 1
    return f


def _routed(atoms: List[Dict]) -> bool:
    return bool(atoms) and all(a["fate"] not in DROPPED for a in atoms)


def check(cid: str, role: str, text: str, carries: Optional[bool], result: str, gap: Optional[str], evidence: Any) -> Dict[str, Any]:
    if result in ("PASS", "NOT_TESTABLE"):
        gap = None  # a gap type only describes a failure
    return {"id": cid, "role": role, "check": text, "intent_carries": carries, "result": result, "gap_type": gap, "evidence": evidence}


def _has(text: str, *needles: str) -> bool:
    t = text.lower()
    return any(n in t for n in needles)


# ------------------------------------------------------------------------------------------------------------------------------
def role1(intent: ExperimentalHiringIntent, A: List[Dict], paths: Dict[str, Any]) -> List[Dict[str, Any]]:
    R = "R1"
    out: List[Dict[str, Any]] = []
    sp = _a(A, "sourcing_path")
    flat = bool(paths.get("has_paths"))
    out.append(check("R1-01", R, "Path A vs Path B structure is preserved or routed (path logic must not be flattened into one AND)",
                     len(intent.sourcing_paths) >= 2, "PASS" if _routed(sp) else "FAIL", "COMPILER LOGIC",
                     {"path_atoms": _fates(sp), "plan_mentions_any_path": paths.get("plan_mentions_any_path"),
                      "flattened": flat and not _routed(sp), "whole_plan_leaves": [l[0].split(".")[-1] + " " + l[2][:30] for l in paths.get("whole_plan_leaves", [])]}))
    geo = _a(A, "location.entry", "path") + _a(A, "location.country", "path") + _a(A, "location.remote", "path") + _a(A, "location.entry", "global")
    out.append(check("R1-02", R, "Path-specific geography is preserved or routed", bool(geo), "PASS" if _routed(geo) else "FAIL", "COMPILER LOGIC",
                     {"geography_atoms": [(a["concept"], a["scope"], a["value"], a["fate"]) for a in geo]}))
    preq = [a for a in A if a["scope"] != "global" and a["concept"] in ("skill", "experience.min", "experience.max", "seniority.value", "domain")]
    out.append(check("R1-03", R, "Path-specific requirements (skills, experience, seniority, domain inside a path) are preserved or routed",
                     bool(preq), "PASS" if _routed(preq) else "FAIL", "COMPILER LOGIC", {"path_requirement_fates": _fates(preq)}))
    pq_waiver = [r for r in intent.reconciliations if r.action == "waived" and _has(r.topic + r.result, "power query")]
    pq_path = [a for a in A if a["scope"] != "global" and a["concept"] == "skill" and _has(a["value"], "power query")]
    pq_global = _a(A, "skill", "global", lambda a: _has(a["value"], "power query"))
    out.append(check("R1-04", R, "Power Query waiver on Path A is honoured (global Power Query must not bind Path A)",
                     bool(pq_waiver or pq_path),
                     ("PASS" if (any(a["fate"] not in DROPPED for a in _a(A, "reconciliation")) or _routed(pq_path)) else "FAIL") if (pq_waiver or pq_path) else "NOT_TESTABLE", "COMPILER LOGIC",
                     {"waiver_reconciliations": len(pq_waiver), "path_level_power_query_atoms": [(a["scope"], a["strength"], a["fate"]) for a in pq_path],
                      "global_power_query_atoms": [(a["strength"], a["relationship"], a["fate"]) for a in pq_global],
                      "waiver_has_destination": any(a["fate"] not in DROPPED for a in _a(A, "reconciliation")) or _routed(pq_path)}))
    ex = _a(A, "experience.min", pred=lambda a: a["value"].startswith("6"))
    scope = ex[0]["scope"] if ex else None
    res = "NOT_TESTABLE" if not ex else ("FAIL")
    out.append(check("R1-05", R, "Path B 6+ years is enforced for Path B only (not global, not dropped)", bool(ex), res, "COMPILER LOGIC",
                     {"experience_atom_scope": scope, "fate": ex[0]["fate"] if ex else None,
                      "reading": ("dropped: the path-only value never reaches the plan" if scope and scope != "global" else
                                  "applied globally: Path A is held to Path B's floor (the intake placed it globally; the compiler has no scope)" if scope else None)}))
    sx = _a(A, "semantic_exclusion")
    sec = [a for a in sx if _has(a["value"], "secur", "soc", "cyber")]
    out.append(check("R1-06", R, "Semantic security-operations / SOC exclusion is routed (and never turned into a company or title filter)",
                     bool(sec), "PASS" if _routed(sec) else "FAIL", "COMPILER LOGIC",
                     {"exclusion_fates": _fates(sx), "negative_leaf_in_plan": False}))
    firm = [a for a in sx if _has(a["value"], "firm")]
    out.append(check("R1-07", R, "Security-firm qualifier is routed", bool(firm), ("PASS" if _routed(firm) else "FAIL") if firm else "NOT_TESTABLE", "COMPILER LOGIC",
                     {"fates": _fates(firm), "note": None if firm else "this run carried the qualifier inside the main exclusion text or not at all"}))
    lead = _a(A, "seniority.leadership")
    ev_lead = [a for a in _a(A, "evidence_signal") if _has(a["value"], "people leadership", "technical leadership")]
    typed = bool(lead)
    res = "PASS" if _routed(lead) else ("PARTIAL" if ev_lead and any(a["fate"] not in DROPPED for a in ev_lead) else "FAIL")
    out.append(check("R1-08", R, "Leadership = people OR technical is routed", typed or bool(ev_lead), res if (typed or ev_lead) else "NOT_TESTABLE", "COMPILER LOGIC",
                     {"typed_leadership_fates": _fates(lead), "restating_evidence_signal_fates": _fates(ev_lead),
                      "reading": "typed field has no destination; meaning survives only where the model ALSO wrote an evidence signal" if lead and ev_lead else None}))
    dom = _a(A, "domain")
    ev_dom = [a for a in _a(A, "evidence_signal") if _has(a["value"], "cyber incident", "data breach", "breach")]
    out.append(check("R1-09", R, "Domain preference (Cyber Incident Review / Data Breach Analysis) is routed", bool(dom),
                     "PASS" if _routed(dom) else ("PARTIAL" if ev_dom else "FAIL"), "COMPILER LOGIC",
                     {"domain_fates": _fates(dom), "restating_evidence_signal_fates": _fates(ev_dom)}))
    ctry = _a(A, "location.country")
    out.append(check("R1-10", R, "India country is routed to a country filter or audited", bool(ctry), "PASS" if _routed(ctry) else "FAIL", "COMPILER LOGIC",
                     {"fates": _fates(ctry), "scope": [a["scope"] for a in ctry]}))
    rem = _a(A, "location.remote")
    out.append(check("R1-11", R, "Remote-allowed is routed or audited", bool(rem), "PASS" if _routed(rem) else "FAIL", "COMPILER LOGIC", {"fates": _fates(rem)}))
    return out


# ------------------------------------------------------------------------------------------------------------------------------
def role2(intent: ExperimentalHiringIntent, A: List[Dict], plan: Dict[str, Any], overlay: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    R = "R2"
    out: List[Dict[str, Any]] = []
    prof = _a(A, "skill.proficiency")
    hands = [a for a in prof if a["proficiency"] == "hands_on"]
    out.append(check("R2-01", R, "Working / hands-on distinction reaches the plan or the downstream checklist", bool(prof), "PASS" if _routed(prof) else "FAIL", "COMPILER LOGIC",
                     {"proficiency_atoms": len(prof), "fates": _fates(prof), "levels": {p: sum(1 for a in prof if a["proficiency"] == p) for p in sorted({a['proficiency'] for a in prof})}}))
    if overlay:
        oprof = [a for a in overlay["atoms"] if a["concept"] == "skill.proficiency" and a["proficiency"] == "advanced"]
        out.append(check("R2-02", R, "Advanced proficiency (Python, Java) reaches the plan or the downstream checklist [SYNTHETIC OVERLAY: stored Role 2 intents pre-date `advanced`]",
                         bool(oprof), "PASS" if _routed(oprof) else "FAIL", "COMPILER LOGIC", {"fates": _fates(oprof), "values": [a["value"] for a in oprof]}))
        wm = [a for a in overlay["atoms"] if a["concept"] == "location.work_mode"]
        out.append(check("R2-03", R, "Hybrid work mode is routed or audited [SYNTHETIC OVERLAY: stored Role 2 intents pre-date `work_mode`]", bool(wm),
                         "PASS" if _routed(wm) else "FAIL", "COMPILER LOGIC", {"fates": _fates(wm)}))
        st = [a for a in overlay["atoms"] if a["concept"] == "seniority.value"]
        notes = [r["note"] for r in overlay["plan"]["audit"] if r["source"] == "seniority"]
        out.append(check("R2-05", R, "Unknown 'Staff' seniority is carried verbatim and never silently becomes another level [SYNTHETIC OVERLAY]", bool(st),
                         "PASS" if _routed(st) and notes and "value=Staff;" in notes[0] else "FAIL", None,
                         {"fate": _fates(st), "audit_note": notes[:1], "note": "downstream level reader maps Staff to the staff/lead rung (see probes); `staff` is absent from knowledge/seniority.json (TAXONOMY follow-up, unchanged)"}))
    else:
        out.append(check("R2-02", R, "Advanced proficiency", False, "NOT_TESTABLE", None, None))
    sig = [a for a in _a(A, "evidence_signal") if _has(a["value"], "individual contributor", " ic ", "ic engineer", "solution design", "client", "proofs of concept", "proof of concept", "staff")]
    out.append(check("R2-04", R, "Semantic role / work-type requirements (IC engineer, client-problem solution design, POCs, Staff-level) are routed", bool(sig),
                     "PASS" if _routed(sig) else "FAIL", "COMPILER LOGIC", {"signals": [(a["value"], a["strength"], a["fate"]) for a in sig][:8]}))
    fde = [t for t in intent.role_family if _has(t, "forward deployed")]
    leaf_titles = [l[2] for l in plan["leaves"] if l[0].endswith("current.title")]
    reached = any("forward deployed" in t.lower() for t in leaf_titles)
    out.append(check("R2-06", R, "A comparison title ('more like a Forward Deployed Engineer') must not become a hard target title", bool(fde),
                     "FAIL" if reached else "PASS", "PROVENANCE / VALIDATION",
                     {"role_family": list(intent.role_family), "title_leaves": leaf_titles,
                      "reading": "the compiler cannot tell an analogy from a target; the intake validator `title_analogy` exists but is not applied at the compiler boundary"}))
    cur = [a for a in _a(A, "skill") if a["relationship"] == "current" and a["strength"] == "required"]
    hard_cur = [a for a in cur if a["fate"] == "ENFORCED"]
    jd = (INPUTS / "role2_jd.txt").read_text(encoding="utf-8")
    brief = (INPUTS / "role2_recruiter_brief.txt").read_text(encoding="utf-8")
    unsupported = [d for d in vcr.cross_role_diagnostics(intent, jd, brief) if d.get("code") == "unsupported_current_relationship"]
    out.append(check("R2-07", R, "Relationship semantics: a required skill becomes a hard filter only where the source states current use", True,
                     "FAIL" if unsupported else "PASS", "PROVENANCE / VALIDATION",
                     {"required_skills_with_relationship_current": len(cur), "of_which_hard_filtered_by_compiler": len(hard_cur),
                      "frozen_validator_unsupported_current": len(unsupported),
                      "reading": "every `current` required skill is a provider hard filter; the compiler has no way to know the source never said 'current'"}))
    return out


# ------------------------------------------------------------------------------------------------------------------------------
def role3(intent: ExperimentalHiringIntent, A: List[Dict], plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    R = "R3"
    out: List[Dict[str, Any]] = []
    loc = _a(A, "location.entry")
    leaves = [l for l in plan["leaves"] if "location" in l[0]]
    out.append(check("R3-01", R, "Hyderabad is enforced as a location filter", bool(loc), "PASS" if loc and loc[0]["fate"] in ("ENFORCED", "NORMALIZED") else "FAIL", None,
                     {"entry": loc[0]["value"] if loc else None, "leaves": [(l[0].split('.')[-1], l[2]) for l in leaves],
                      "observation": "the state leaf comes from the model's own world knowledge (ROLE3_GROUND_TRUTH G2: INFERRED, the JD says 'Hyderabad, India'); the compiler turns that inferred state into a hard AND (PROVENANCE: basis is not read)"}))
    wm = _a(A, "location.work_mode")
    out.append(check("R3-02", R, "Hybrid work mode does not disappear", bool(wm), "PASS" if _routed(wm) else "FAIL", "COMPILER LOGIC", {"fates": _fates(wm), "value": [a["value"] for a in wm]}))
    exm = _a(A, "experience.min") + _a(A, "experience.max")
    out.append(check("R3-03", R, "8-12 years is enforced (both bounds)", bool(exm), "PASS" if len(exm) == 2 and all(a["fate"] == "ENFORCED" for a in exm) else "FAIL", None,
                     {"atoms": [(a["value"], a["fate"]) for a in exm]}))
    xl = [a for a in _a(A, "skill.proficiency") if a["proficiency"] == "advanced"]
    xs = [a for a in _a(A, "skill") if _has(a["value"], "excel")]
    out.append(check("R3-04", R, "Advanced Excel: the skill AND its depth are routed", bool(xl), "FAIL" if not _routed(xl) else "PASS", "COMPILER LOGIC",
                     {"skill_fate": _fates(xs), "proficiency_fate": _fates(xl)}))
    pb = [a for a in A if a["concept"] in ("skill_any_of", "skill") and _has(a["value"], "power bi")]
    pbe = [a for a in _a(A, "evidence_signal") if _has(a["value"], "working knowledge of power bi")]
    out.append(check("R3-05", R, "Working-knowledge Power BI: the requirement and its depth are routed", bool(pb or pbe),
                     "PARTIAL" if (_routed(pb) and not _a(A, "skill.proficiency", pred=lambda a: _has(a["value"], "power bi"))) else ("PASS" if _routed(pb) else "FAIL"), "COMPILER LOGIC",
                     {"group_fates": _fates(pb), "depth_text_evidence_signal_fates": _fates(pbe),
                      "reading": "the group is routed downstream by name only; the depth reaches the Judge only as the intake's untyped evidence-signal text"}))
    co = _a(A, "company")
    company_leaves = [l for l in plan["leaves"] if "company_name" in l[0]]
    out.append(check("R3-06", R, "Named companies stay preferences and are never hard company filters", bool(co),
                     "PASS" if co and all(a["fate"] == "PREFERENCE_CONTEXT" for a in co) and not company_leaves else "FAIL", None,
                     {"company_fates": _fates(co), "company_leaves_in_plan": len(company_leaves)}))
    sx = _a(A, "semantic_exclusion")
    out.append(check("R3-07", R, "Semantic audit / tax / bookkeeping exclusion is routed (not a company or title filter)", bool(sx), "PASS" if _routed(sx) else "FAIL", "COMPILER LOGIC",
                     {"fates": _fates(sx), "negative_leaf_in_plan": any(l[1] in ("(!)", "not_in") for l in plan["leaves"])}))
    sen = _a(A, "seniority.value")
    notes = [r["note"] for r in plan["audit"] if r["source"] == "seniority"]
    rf = [t for t in intent.role_family]
    ok = bool(sen) and sen[0]["fate"] == "VERIFIED_DOWNSTREAM" and (_has(sen[0]["value"], "manager") or any(_has(t, "manager") for t in rf))
    out.append(check("R3-08", R, "'Senior Manager' role identity is carried (level verbatim or Manager kept in the title)", bool(sen), "PASS" if ok else "FAIL", None,
                     {"seniority": sen[0]["value"] if sen else None, "role_family": rf, "audit_note": notes[:1]}))
    edu = [l for l in plan["leaves"] if l[0].startswith("education.")]
    out.append(check("R3-09", R, "Education values are provider-usable strings (observation only: the provider is not called offline)", True, "OBSERVATION", "TAXONOMY",
                     {"education_leaves": [(l[0].split(".")[-1], l[2]) for l in edu],
                      "reading": "the degree is the literal 'Bachelor’s degree' (curly apostrophe) and a stream is the literal 'Related discipline'; degree surface forms are only expanded for B.Tech/B.E/M.Tech. Whether the provider matches them cannot be known offline"}))
    return out
