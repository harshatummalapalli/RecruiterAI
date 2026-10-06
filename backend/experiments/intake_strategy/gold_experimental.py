"""Gold evaluator for the EXPERIMENTAL representation (EXPERIMENT ONLY; never put in a prompt).

Same assertion ids as `gold_assertions` where the question is the same, so the baseline and experimental tables line up,
plus new ids for the items the experimental shape makes askable. `gold_assertions` (the baseline evaluator) is untouched
so baseline numbers stay reproducible.

Paths are found by STRATEGY (domain_led vs capability_led/hybrid), never by the id or label the model chose, and a
requirement is judged on its EFFECTIVE value for a path (global + the path's overrides), so a model may put Power Query,
6+ years or Lead either globally or on Path B and be judged on what each path actually means.

LOCKED RECRUITER DECISIONS (owner, after the hardening pass; this is the ground truth, not something the model is tuned to):
    Path A (domain-led):  Lead OR Senior (the brief says "Lead / Senior Data Analyst identity"); domain PREFERRED, not required;
                          Power Query not required; India, remote allowed.
    Path B (capability):  Lead; 6+ years; SQL and Python hands-on; Power Query working knowledge; Hyderabad OR Pune; domain not required.
    Global:               6+ years is NOT global and NOT on Path A. "Lead" means people OR technical leadership; a JD responsibility
                          to lead/mentor is context, never an implicit direct-reports requirement. The security-operations negative
                          is about work identity; the security-firm statement is subordinate to it, never an employer-industry rule.

Failure classes: EXTRACTION (the schema could say it, the model did not), RECONCILIATION (JD and brief merged or
prioritised wrongly), VALIDATION (a provenance claim is not supported). REPRESENTATION never applies here: whether the
schema can hold a concept is `experimental_schema.schema_concepts()`, decided from the schema alone.

Thresholds for provenance are stated in `provenance_status` and are this experiment's choice, not a standard.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from backend.experiments.intake_strategy.experimental_schema import (
    ExperimentalHiringIntent,
    SourcingPath,
    effective_view,
    schema_concepts,
)
from backend.experiments.intake_strategy.gold_assertions import (
    EXTRACTION,
    FAIL,
    HARD_SECOPS,
    PARTIAL,
    PASS,
    PEOPLE_LEADERSHIP,
    POSITIVE_DOMAIN,
    POWER_QUERY,
    RECONCILIATION,
    VALIDATION,
    AssertionResult,
)
from backend.experiments.intake_strategy.validators import ERROR_CODES, iter_atoms, validate

_DENIES = re.compile(r"\b(not|no|never|without|rather than|instead of|other than|excluding|except|nor)\b|n't\b", re.I)
COUNTRIES = {"india", "united states", "usa", "uk", "united kingdom"}
_JD_ITEMS: List[Tuple[str, "re.Pattern[str]"]] = [
    ("Relativity", re.compile(r"relativity", re.I)),
    ("Canopy", re.compile(r"canopy", re.I)),
    ("review/QA/compliance/audit experience", re.compile(r"(quality assurance|\bqa\b|compliance|audit|review)", re.I)),
    ("data privacy / regulatory / security frameworks", re.compile(r"(data privacy|regulatory|security framework)", re.I)),
]
_DEGREES = ("Cybersecurity", "Information Technology", "Computer Science", "Information Systems", "Data Analytics")


def _heads(loc) -> List[str]:
    """Every place a location names, countries and cities alike (kept for the stability summary)."""
    return sorted({*(c.strip().lower() for c in (loc.countries if loc else [])), *(e.split(",")[0].strip().lower() for e in (loc.entries if loc else []))})


def _typed(loc) -> Tuple[List[str], List[str]]:
    """(country-wide areas, places below country level), read ONLY from the typed fields."""
    if loc is None:
        return [], []
    return sorted(c.strip().lower() for c in loc.countries), sorted(e.split(",")[0].strip().lower() for e in loc.entries)


def _all_locations(intent: ExperimentalHiringIntent):
    if intent.location:
        yield "location", intent.location, None
    for p in intent.sourcing_paths:
        if p.location:
            yield f"paths[{p.id}].location", p.location, p.id


def find_paths(intent: ExperimentalHiringIntent) -> Tuple[Optional[SourcingPath], Optional[SourcingPath]]:
    a = next((p for p in intent.sourcing_paths if p.strategy == "domain_led"), None)
    b = next((p for p in intent.sourcing_paths if p is not a and p.strategy in ("capability_led", "hybrid")), None)
    return a, b


def _skill(view: Dict[str, Any], pattern: "re.Pattern[str]") -> List[Any]:
    return [s for s in view["skills"] if pattern.search(s.name)]


def _fmt_skill(items: List[Any]) -> str:
    return "; ".join(f"{s.name!r}/{s.strength}/{s.proficiency}" for s in items) or "absent"


def provenance_status(report: Dict[str, Any]) -> Tuple[str, Optional[str], str]:
    """FAIL: a constraint-bearing atom has no basis, or over 25% of atoms with a basis are unsupported/misattributed.
    PARTIAL: any unsupported / misattributed / inferred-hard / unverified-approved claim, or any atom without a basis.
    PASS: every atom carries a basis and every claim is verified or lexically supported."""
    rows = report["atoms"]
    with_basis = [r for r in rows if r["status"] != "missing"]
    missing = [r for r in rows if r["status"] == "missing"]
    missing_hard = [r for r in missing if r["constraint"] or r["kind"] in ("skill", "domain", "seniority", "experience", "location", "path")]
    bad = [r for r in with_basis if r["status"] in ("unsupported", "misattributed")]
    counts = report["status_counts"]
    summary = f"{len(rows)} atoms; status={counts}; missing_basis={len(missing)} (constraint-bearing {len(missing_hard)}); unsupported/misattributed={len(bad)}"
    if missing_hard or (with_basis and len(bad) / len(with_basis) > 0.25):
        return FAIL, VALIDATION, summary
    codes = {d["code"] for d in report["diagnostics"]}
    if bad or missing or codes & {"inferred_hard_constraint", "approved_knowledge_unverified", "quote_not_found"}:
        return PARTIAL, VALIDATION, summary
    return PASS, None, summary


def evaluate_critical(intent: ExperimentalHiringIntent, jd: str, brief: str) -> List[AssertionResult]:
    out: List[AssertionResult] = []
    report = validate(intent, jd, brief)

    def add(id_: str, title: str, status: str, cls: Optional[str], evidence: str) -> None:
        out.append(AssertionResult(id_, title, status, None if status == PASS else cls, evidence))

    path_a, path_b = find_paths(intent)
    views = {p.id: effective_view(intent, p.id) for p in intent.sourcing_paths}
    va = views.get(path_a.id) if path_a else None
    vb = views.get(path_b.id) if path_b else None
    strategies = [p.strategy for p in intent.sourcing_paths]

    # 1-4 path structure
    if len(intent.sourcing_paths) == 2 and path_a and path_b:
        add("two_paths_preserved", "Two sourcing paths preserved", PASS, None, f"strategies={strategies}")
    elif len(intent.sourcing_paths) > 2:
        add("two_paths_preserved", "Two sourcing paths preserved", PARTIAL, EXTRACTION, f"{len(strategies)} paths: {strategies} (an extra path was invented or one was split)")
    elif len(intent.sourcing_paths) == 2:
        add("two_paths_preserved", "Two sourcing paths preserved", PARTIAL, EXTRACTION, f"two paths but not one domain_led + one capability_led/hybrid: {strategies}")
    else:
        add("two_paths_preserved", "Two sourcing paths preserved", FAIL, EXTRACTION, f"{len(strategies)} path(s): {strategies}")

    domain_a = [d for d in (va["domain"] if va else []) if POSITIVE_DOMAIN.search(d.name) and d.strength in ("required", "preferred")]
    if path_a and domain_a:
        add("path_a_domain_led", "Path A is domain-led", PASS, None, f"strategy=domain_led; domain={[(d.name, d.strength) for d in domain_a]}")
    elif path_a:
        add("path_a_domain_led", "Path A is domain-led", PARTIAL, EXTRACTION, "strategy=domain_led but no required/preferred cyber-incident-review / data-breach domain on the path")
    else:
        add("path_a_domain_led", "Path A is domain-led", FAIL, EXTRACTION, f"no domain_led path: {strategies}")
    add("path_b_capability_led", "Path B is capability-led / hybrid", PASS if path_b else FAIL, EXTRACTION, f"strategies={strategies}")

    a_loc, b_loc = (va["location"] if va else None), (vb["location"] if vb else None)
    (a_countries, a_cities), (b_countries, b_cities) = _typed(a_loc), _typed(b_loc)
    detail = f"A: countries={a_countries} cities={a_cities} remote={a_loc.remote if a_loc else None} | B: countries={b_countries} cities={b_cities} remote={b_loc.remote if b_loc else None}"
    if a_countries == ["india"] and not a_cities and b_cities == ["hyderabad", "pune"] and not b_countries:
        add("path_geography_differs", "Path A geography differs from Path B (typed)", PASS, None, detail)
    elif not (a_loc and b_loc):
        add("path_geography_differs", "Path A geography differs from Path B (typed)", FAIL, EXTRACTION, f"a path has no effective location. {detail}")
    elif (a_countries, a_cities) != (b_countries, b_cities):
        add("path_geography_differs", "Path A geography differs from Path B (typed)", PARTIAL, EXTRACTION, f"differs but is not typed country India / cities Hyderabad+Pune. {detail}")
    else:
        add("path_geography_differs", "Path A geography differs from Path B (typed)", FAIL, EXTRACTION, f"same geography on both paths. {detail}")

    # 5-6 Power Query
    pq_a = _skill(va, POWER_QUERY) if va else []
    if va is None:
        add("pq_not_mandatory_path_a", "Power Query not mandatory on Path A", FAIL, EXTRACTION, "no Path A")
    elif any(s.strength == "required" for s in pq_a):
        add("pq_not_mandatory_path_a", "Power Query not mandatory on Path A", FAIL, RECONCILIATION, f"Path A still requires it: {_fmt_skill(pq_a)}")
    else:
        add("pq_not_mandatory_path_a", "Power Query not mandatory on Path A", PASS, None, f"Path A effective: {_fmt_skill(pq_a)}")
    pq_b = _skill(vb, POWER_QUERY) if vb else []
    req_b = [s for s in pq_b if s.strength == "required"]
    if req_b and req_b[0].proficiency == "working_knowledge":
        add("pq_working_knowledge_path_b", "Power Query is working knowledge on Path B", PASS, None, f"Path B effective: {_fmt_skill(pq_b)}")
    elif req_b and req_b[0].proficiency is None:
        add("pq_working_knowledge_path_b", "Power Query is working knowledge on Path B", PARTIAL, EXTRACTION, f"required but no proficiency: {_fmt_skill(pq_b)}")
    else:
        add("pq_working_knowledge_path_b", "Power Query is working knowledge on Path B", FAIL, EXTRACTION, f"Path B effective: {_fmt_skill(pq_b)} (must be required + working_knowledge)")

    # 7-8 hands-on SQL / Python (both paths: the brief and the JD state them for the role as a whole)
    for tool, id_ in (("SQL", "sql_hands_on"), ("Python", "python_hands_on")):
        pat = re.compile(rf"\b{tool}\b", re.I)
        b_hit = _skill(vb, pat) if vb else []
        a_hit = _skill(va, pat) if va else []
        ok = lambda hits: bool(hits) and hits[0].strength == "required" and hits[0].proficiency == "hands_on"  # noqa: E731
        detail = f"B={_fmt_skill(b_hit)} A={_fmt_skill(a_hit)}"
        if ok(b_hit) and ok(a_hit):
            add(id_, f"{tool} is hands-on", PASS, None, detail)
        elif b_hit and b_hit[0].strength == "required":
            add(id_, f"{tool} is hands-on", PARTIAL, EXTRACTION, f"required on B but depth/strength is wrong or missing on one path: {detail}")
        else:
            add(id_, f"{tool} is hands-on", FAIL, EXTRACTION, detail)

    # 9-10 Path B experience / level
    b_exp = vb["experience"] if vb else None
    if b_exp and b_exp.minimum_years == 6 and b_exp.strength == "required":
        a_exp = va["experience"] if va else None
        add("path_b_min_6_years", "Path B requires 6+ years", PASS, None,
            f"Path B effective: 6+ required. Path A effective: {a_exp.minimum_years if a_exp else None} (brief does not say whether A inherits it)")
    else:
        add("path_b_min_6_years", "Path B requires 6+ years", FAIL, EXTRACTION, f"Path B effective experience={b_exp.model_dump(exclude={'basis'}) if b_exp else None}")
    b_sen = vb["seniority"] if vb else None
    if b_sen and "lead" in b_sen.value.lower() and b_sen.strength == "required":
        add("path_b_lead_requirement", "Path B requires Lead level", PASS, None, f"Path B effective: {b_sen.value}/{b_sen.strength}")
    elif b_sen and "lead" in b_sen.value.lower():
        add("path_b_lead_requirement", "Path B requires Lead level", PARTIAL, EXTRACTION, f"Lead present but {b_sen.strength}, not required")
    else:
        add("path_b_lead_requirement", "Path B requires Lead level", FAIL, EXTRACTION, f"Path B effective seniority={b_sen.value if b_sen else None}")

    # 11-12 domain vs security operations; semantic hard negative
    atoms = list(iter_atoms(intent))
    # A required/preferred atom that NAMES security-operations vocabulary only to deny it ("... rather than cybersecurity
    # operations", "security monitoring alone is not equivalent") is a faithful narrowing, not a promotion. Added after the
    # first v3 run, where this check misread two such atoms; the before/after counts are reported in RESULTS_HARDENING.md.
    promoted = [a for a in atoms if a["kind"] in ("skill", "skill_any_of", "evidence_signal", "domain", "path")
                and a["strength"] in ("required", "preferred") and HARD_SECOPS.search(a["text"]) and not _DENIES.search(a["text"])]
    secops_neg = [x for x in intent.semantic_exclusions if HARD_SECOPS.search(" ".join([x.concept, *x.includes]))]
    if promoted:
        add("cyber_review_not_secops", "Cyber incident review kept distinct from cybersecurity/SOC", FAIL, RECONCILIATION,
            f"security-operations vocabulary is still a positive requirement/preference: {[(a['text'], a['strength']) for a in promoted]}")
    elif not domain_a:
        add("cyber_review_not_secops", "Cyber incident review kept distinct from cybersecurity/SOC", FAIL, EXTRACTION, "no required/preferred cyber-incident-review domain on Path A")
    elif not secops_neg:
        add("cyber_review_not_secops", "Cyber incident review kept distinct from cybersecurity/SOC", PARTIAL, EXTRACTION, "domain captured and no SecOps promoted, but no semantic negative states the distinction")
    else:
        add("cyber_review_not_secops", "Cyber incident review kept distinct from cybersecurity/SOC", PASS, None,
            f"domain={[d.name for d in domain_a]}; negative={[x.concept for x in secops_neg]}; no security-operations atom promoted")
    if secops_neg:
        add("hard_negative_secops_preserved", "Security-operations hard negative preserved", PASS, None, f"semantic_exclusions={[(x.concept, x.includes) for x in secops_neg]}")
    else:
        add("hard_negative_secops_preserved", "Security-operations hard negative preserved", FAIL, EXTRACTION, f"semantic_exclusions={[x.concept for x in intent.semantic_exclusions]}")

    # 13 leadership
    b_modes = set(vb["seniority"].leadership) if vb and vb["seniority"] else set()
    people_only = [a for a in atoms if a["strength"] == "required" and a["kind"] in ("skill", "evidence_signal")
                   and PEOPLE_LEADERSHIP.search(a["text"]) and "technical" not in a["text"].lower()]
    if not {"people", "technical"} <= b_modes:
        add("lead_people_or_technical", "'Lead' supports people OR technical leadership", FAIL, EXTRACTION, f"Path B effective seniority.leadership={sorted(b_modes)}")
    elif people_only:
        add("lead_people_or_technical", "'Lead' supports people OR technical leadership", PARTIAL, RECONCILIATION,
            f"leadership lists both, but a people-only requirement still stands: {[a['text'] for a in people_only]}")
    else:
        add("lead_people_or_technical", "'Lead' supports people OR technical leadership", PASS, None, f"leadership={sorted(b_modes)}; no people-only requirement remains")

    # 14-15 no invented radius / company filter (new: also company exclusions)
    radii = [x for x in ([intent.location] + [p.location for p in intent.sourcing_paths]) if x and x.radius]
    add("no_invented_radius", "No radius invented", FAIL if radii else PASS, EXTRACTION, f"radius on {len(radii)} location(s)")
    req_companies = [c.name for c in intent.companies if c.strength == "required" and c.relationship in ("current", "any")]
    scale = bool(intent.company_scale and intent.company_scale.strength == "required")
    add("no_invented_company_filter", "No current-company hard filter invented", FAIL if (req_companies or scale) else PASS, EXTRACTION, f"required companies={req_companies} scale={scale}")
    company_x = [x for x in intent.exclusions if "company" in x.kind]
    add("no_invented_company_exclusion", "No company exclusion invented (no source names a company)", FAIL if company_x else PASS, EXTRACTION,
        f"company exclusions={[(x.kind, x.value) for x in company_x]}")

    # 16 provenance
    status, cls, summary = provenance_status(report)
    add("provenance_preserved", "Explicit vs inferred provenance preserved and verified", status, cls, summary)

    # new: path-B domain not required; country-level geography; reconciliation visible; JD not silently discarded
    b_domain_required = [a for a in atoms if a["scope"] in (None, path_b.id if path_b else None) and a["strength"] == "required"
                         and a["kind"] in ("skill", "domain", "evidence_signal") and POSITIVE_DOMAIN.search(a["text"])]
    if vb is None:
        add("path_b_domain_not_required", "Path B does not require the cyber-incident domain", FAIL, EXTRACTION, "no Path B")
    else:
        add("path_b_domain_not_required", "Path B does not require the cyber-incident domain", FAIL if b_domain_required else PASS, RECONCILIATION,
            f"required domain atoms applying to B: {[(a['ref'], a['text']) for a in b_domain_required]}")
    every_entry = [e.split(",")[0].strip().lower() for _, loc, _ in _all_locations(intent) for e in loc.entries]
    if "india" in a_countries and "india" not in every_entry:
        add("intent_country_level_geography", "India is a typed country, never a city entry", PASS, None, f"A countries={a_countries}; no entry named india")
    else:
        add("intent_country_level_geography", "India is a typed country, never a city entry", FAIL, EXTRACTION if "india" not in every_entry else EXTRACTION,
            f"A countries={a_countries}; india appears in a places-below-country entry: {'india' in every_entry}")
    a_remote, b_remote = (a_loc.remote if a_loc else None), (b_loc.remote if b_loc else None)
    if a_remote == "allowed" and b_remote != "allowed":
        add("remote_typed", "Remote is a typed fact: allowed on Path A, not asserted for Path B", PASS, None, f"A.remote={a_remote} B.remote={b_remote}")
    else:
        add("remote_typed", "Remote is a typed fact: allowed on Path A, not asserted for Path B", FAIL, EXTRACTION, f"A.remote={a_remote} B.remote={b_remote}")

    # Path B's requirements must not be applied to Path A (judged on the EFFECTIVE value, typed fields only)
    a_exp = va["experience"] if va else None
    a_exp_required = bool(a_exp and a_exp.strength == "required" and a_exp.minimum_years)
    add("path_b_requirements_not_in_path_a", "Path B's 6+ years is not applied to Path A", FAIL if a_exp_required else PASS, EXTRACTION,
        f"Path A effective experience={(a_exp.minimum_years, a_exp.strength) if a_exp else None}" + (" (inherited from the global intent)" if a_exp_required and path_a and path_a.experience is None else ""))

    # Locked: Path A's domain is PREFERRED (the brief says "Ideal"), never required; and 6+ years is not a global requirement
    dom_a_pos = [d for d in (va["domain"] if va else []) if POSITIVE_DOMAIN.search(d.name)]
    if va is None:
        add("path_a_domain_preferred", "Path A domain is preferred, not required (locked)", FAIL, EXTRACTION, "no Path A")
    elif any(d.strength == "required" for d in dom_a_pos):
        add("path_a_domain_preferred", "Path A domain is preferred, not required (locked)", FAIL, EXTRACTION,
            f"Path A effective domain is stronger than the ground truth: {[(d.name[:60], d.strength) for d in dom_a_pos]}")
    elif not any(d.strength == "preferred" for d in dom_a_pos):
        add("path_a_domain_preferred", "Path A domain is preferred, not required (locked)", FAIL, EXTRACTION, f"no preferred domain on Path A: {[(d.name[:60], d.strength) for d in dom_a_pos]}")
    else:
        add("path_a_domain_preferred", "Path A domain is preferred, not required (locked)", PASS, None, f"{[(d.name[:60], d.strength) for d in dom_a_pos]}")
    add("experience_not_global", "6+ years is not a global requirement (locked)", FAIL if intent.experience else PASS, EXTRACTION,
        f"global experience={(intent.experience.minimum_years, intent.experience.strength) if intent.experience else None}")

    # Seniority levels: only what the source states, for the path it states it for
    def levels(view):
        sen = view["seniority"] if view else None
        return [] if sen is None else [x.strip().lower() for x in [sen.value, *sen.alternatives]]
    la, lb = levels(va), levels(vb)
    all_levels = {x for x in la + lb}
    if lb != ["lead"]:
        add("seniority_levels_source_supported", "Levels are source-supported: Path A Lead or Senior; Path B Lead only", FAIL, EXTRACTION,
            f"Path B levels={lb} (the source states only Lead for Path B); Path A levels={la}")
    elif set(la) == {"lead", "senior"}:
        add("seniority_levels_source_supported", "Levels are source-supported: Path A Lead or Senior; Path B Lead only", PASS, None,
            f"Path A levels={la} (the brief states Lead / Senior for Path A only); Path B levels={lb}")
    elif la == ["lead"]:
        add("seniority_levels_source_supported", "Levels are source-supported: Path A Lead or Senior; Path B Lead only", PARTIAL, EXTRACTION,
            f"Path A levels={la}: drops Senior, which the brief states for Path A (locked decision: Lead OR Senior)")
    else:
        add("seniority_levels_source_supported", "Levels are source-supported: Path A Lead or Senior; Path B Lead only", FAIL, EXTRACTION,
            f"Path A levels={la} (must be Lead and Senior); Path B levels={lb}")

    # Security-firm statement: kept, semantic, qualified as the recruiter qualified it, never a company filter
    firm = [x for x in intent.semantic_exclusions if re.search(r"security (firm|compan)", " ".join([x.concept, *x.includes]), re.I)]
    firm_text = " ".join(" ".join([x.concept, *x.includes]) for x in firm)
    if not firm:
        add("security_firm_exclusion_semantic", "Recruiter's security-firm exclusion kept as a qualified semantic negative", FAIL, EXTRACTION, "no semantic exclusion carries the recruiter's security-firm statement")
    elif not re.search(r"\b(analyst|sql|python)\b", firm_text, re.I):
        add("security_firm_exclusion_semantic", "Recruiter's security-firm exclusion kept as a qualified semantic negative", PARTIAL, EXTRACTION,
            f"generalised into a blanket exclusion (the analyst / SQL / Python qualifier is gone): {firm_text!r}")
    elif re.search(r"\bcurrent", firm_text, re.I) and not re.search(r"\bcurrent", brief, re.I):
        add("security_firm_exclusion_semantic", "Recruiter's security-firm exclusion kept as a qualified semantic negative", PARTIAL, EXTRACTION,
            f"adds a temporal qualifier the brief does not state: {firm_text!r}")
    elif not secops_neg:
        add("security_firm_exclusion_semantic", "Recruiter's security-firm exclusion kept as a qualified semantic negative", PARTIAL, EXTRACTION,
            f"the firm statement stands without the work-identity negative it is subordinate to: {firm_text!r}")
    else:
        add("security_firm_exclusion_semantic", "Recruiter's security-firm exclusion kept as a qualified semantic negative", PASS, None,
            f"{firm_text!r} (beside the work-identity negative {[x.concept for x in secops_neg]})")

    # Generic deterministic validators (no Role 1 knowledge): any ERROR is a failure
    errors = {c: n for c, n in report["errors"].items()}
    add("generic_validators_clean", "Generic validators: no leakage, conflict, unsupported level, country/city or place error", FAIL if errors else PASS, VALIDATION,
        f"errors={errors}" if errors else "none of the six error validators fired")
    located = [p.id for p in intent.sourcing_paths if report.get("paths_located", {}).get(p.id)]
    if len(intent.sourcing_paths) >= 2 and len(located) < len(intent.sourcing_paths):
        add("path_leakage_checkable", "Every path is located in the sources, so the leakage check could run", PARTIAL, VALIDATION,
            f"located={located} of {[p.id for p in intent.sourcing_paths]}: a path id that is not the source's own name cannot be checked")
    else:
        add("path_leakage_checkable", "Every path is located in the sources, so the leakage check could run", PASS, None, f"located={located}")

    recs = intent.reconciliations
    rr = report["reconciliations"]
    seen = {
        "security_ops_item": any(r.action in ("narrowed", "waived", "contradicted") and
                                 HARD_SECOPS.search(" ".join(filter(None, [r.topic, r.jd_quote, r.result]))) for r in recs),
        "power_query_waived_on_A": any(r.action in ("waived", "narrowed") and POWER_QUERY.search(r.topic) and path_a is not None and r.path_id == path_a.id for r in recs),
        "lead_leadership_widened": any(r.action in ("narrowed", "waived", "contradicted") and re.search(r"lead|people", r.topic, re.I) for r in recs),
    }
    quote_issues = [x["ref"] for x in rr if not (x["jd_quote_verified"] and x["brief_quote_verified"])]
    waiver_codes = [d for d in report["diagnostics"] if d["code"] == "reconciliation_conflict"]
    if all(seen.values()) and not quote_issues and not waiver_codes:
        add("reconciliation_visible", "JD-vs-brief reconciliations explicit and verified", PASS, None, f"{seen}; {len(recs)} reconciliation(s)")
    elif any(seen.values()):
        add("reconciliation_visible", "JD-vs-brief reconciliations explicit and verified", PARTIAL, RECONCILIATION,
            f"{seen}; unverified quotes={quote_issues}; unapplied={[d['code'] for d in waiver_codes]}")
    else:
        add("reconciliation_visible", "JD-vs-brief reconciliations explicit and verified", FAIL, RECONCILIATION, f"none of the expected reconciliations recorded; {len(recs)} recorded")

    blob = " | ".join([a["text"] for a in atoms] + [f"{r.topic} {r.result}" for r in recs])
    kept = {name: bool(pat.search(blob)) for name, pat in _JD_ITEMS}
    streams = {s.lower() for s in (intent.education.streams if intent.education else [])}
    degrees = {d: d.lower() in streams for d in _DEGREES}
    lost = [k for k, v in {**kept, **degrees}.items() if not v]
    add("jd_not_silently_discarded", "Formal JD items not silently discarded", PASS if not lost else (PARTIAL if len(lost) < 5 else FAIL), RECONCILIATION,
        f"missing from every atom and reconciliation: {lost}" if lost else "all retained somewhere")
    return out


def evaluate(intent: ExperimentalHiringIntent, jd: str, brief: str) -> Dict[str, Any]:
    return {
        "schema_concepts": schema_concepts(),
        "critical": [r.to_dict() for r in evaluate_critical(intent, jd, brief)],
        "validation": validate(intent, jd, brief),
    }
