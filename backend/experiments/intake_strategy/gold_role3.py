"""Gold evaluator for ROLE 3 (JD-only; EXPERIMENT ONLY; never put in a prompt).

Encodes `ROLE3_GROUND_TRUTH.md` (committed BEFORE any model run). Role 3 has no recruiter brief, so the validators are called with an empty
brief, no reconciliation is expected, and any claim of a `recruiter_brief` source is a fabricated provenance.

This role tests RESTRAINT: one path, one geography, one exclusion, explicit preferences. A schema that succeeds only by populating many
optional structures is not an acceptable general representation, so over-application is evaluated as hard as fidelity. The frozen
`validators_cross_role.validate_cross_role` is used unchanged, and its ERROR codes count as VALIDATION failures.

Classes: EXTRACTION (the schema could say the right thing and the model did not, including over-application), RECONCILIATION (a source
conflict mishandled; none exists here), PROVENANCE (a claimed source is fabricated, unsupported or inferred-but-required), VALIDATION (a
frozen generic validator fired), REPRESENTATION (the schema cannot say it, decided from the schema; none is predicted), TAXONOMY.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent
from backend.experiments.intake_strategy.gold_assertions import EXTRACTION, FAIL, PARTIAL, PASS, VALIDATION, AssertionResult
from backend.experiments.intake_strategy.gold_experimental import provenance_status
from backend.experiments.intake_strategy.gold_role2 import claims
from backend.experiments.intake_strategy.validators_cross_role import validate_cross_role

PROVENANCE = "PROVENANCE"
I = re.IGNORECASE
NO_BRIEF = ""

COMPANIES = {"unilever": r"unilever", "procter_gamble": r"procter|\bp&g\b", "pepsico": r"pepsi", "nestle": r"nestl", "coca_cola": r"coca[- ]?cola", "mondelez": r"mondelez"}
_CORE = {  # stated qualifications that must be present and `required`
    "financial_planning": r"financial planning|\bfp&a\b.*planning|\bplanning\b", "budgeting": r"budget", "forecasting": r"forecast", "variance_analysis": r"variance",
    "financial_modeling": r"financial model|modell?ing", "excel": r"\bexcel\b", "power_bi": r"power ?bi", "presenting": r"\bpresent",
    "business_partnering": r"business partner|\bpartnering\b", "communication": r"communicat", "erp": r"\berp\b|enterprise resource",
    "fpa_ownership": r"meaningful.*(fp&a|business[- ]finance)|(fp&a|business[- ]finance).*ownership",
}
_PROF_QUAL = re.compile(r"\bCA\b|\bCMA\b|\bACCA\b|\bMBA\b", re.I)
_ENV = re.compile(r"multinational|complex enterprise|large[, ]+(?:and )?complex|enterprise environment", I)
_COMM_LEADERSHIP = re.compile(r"commercial.{0,40}(operations|business[- ]unit)|business[- ]unit leadership", I)
_RESPONSIBILITY_ONLY = {  # responsibilities the JD does not also state as qualifications
    "management reporting packs": re.compile(r"management report|reporting packs?|monthly and quarterly", I),
    "process automation / standardisation": re.compile(r"automation|standardi[sz]", I),
    "cross-functional work": re.compile(r"cross[- ]functional", I),
    "ad hoc / strategic projects": re.compile(r"ad[- ]hoc|strategic projects", I),
}
_INVENTED_TITLE = re.compile(r"director|\bvp\b|vice president|head of|controller|analyst|accountant|auditor|treasur|\bcfo\b|chief|associate|\blead\b|business partner|consultant|specialist", I)
_ALLOWED_TITLE = re.compile(r"fp&a|fpa|financial planning|business finance|commercial finance|finance|manager", I)
_INVENTED_LEVEL = re.compile(r"director|\bvp\b|vice|head|staff|principal|\blead\b|associate|executive|chief|junior|\bmid\b", I)


def _find(cl: List[Dict[str, Any]], rx: str) -> List[Dict[str, Any]]:
    pat = re.compile(rx, I)
    return [c for c in cl if pat.search(c["text"])]


def evaluate_critical(intent: ExperimentalHiringIntent, jd: str) -> List[AssertionResult]:
    out: List[AssertionResult] = []
    report = validate_cross_role(intent, jd, NO_BRIEF)
    cl = claims(intent)
    sen, loc, exp, edu = intent.seniority, intent.location, intent.experience, intent.education
    fam = " | ".join(intent.role_family)

    def add(id_: str, title: str, status: str, cls: Optional[str], evidence: str) -> None:
        out.append(AssertionResult(id_, title, status, None if status == PASS else cls, evidence))

    # ------------------------------------------------------------------ fidelity
    bad_titles = [f for f in intent.role_family if _INVENTED_TITLE.search(f) or not _ALLOWED_TITLE.search(f)]
    add("role_family_discipline", "Role family uses only the JD's function / title words; no adjacent or invented title",
        PASS if not bad_titles else FAIL, EXTRACTION, f"role_family={intent.role_family}" + (f"; invented/adjacent: {bad_titles}" if bad_titles else ""))

    if sen is None:
        add("seniority_senior_manager", "Seniority is Senior Manager (the title), nothing stronger", PARTIAL, EXTRACTION, "the typed level was dropped")
    elif _INVENTED_LEVEL.search(sen.value) or sen.alternatives or sen.leadership:
        add("seniority_senior_manager", "Seniority is Senior Manager (the title), nothing stronger", FAIL, EXTRACTION,
            f"value={sen.value!r} alternatives={sen.alternatives} leadership={sen.leadership}")
    elif "senior manager" in sen.value.lower() or (sen.value.strip().lower() == "senior" and "manager" in fam.lower()):
        add("seniority_senior_manager", "Seniority is Senior Manager (the title), nothing stronger", PASS if sen.strength in ("required", "preferred") else PARTIAL, EXTRACTION,
            f"{sen.value}/{sen.strength}; family={fam}")
    else:
        add("seniority_senior_manager", "Seniority is Senior Manager (the title), nothing stronger", PARTIAL, EXTRACTION, f"value={sen.value!r}: part of 'Senior Manager' is lost")

    if exp and exp.minimum_years == 8 and exp.maximum_years == 12 and exp.strength == "required":
        add("experience_8_to_12", "Experience is the range 8-12 years, required", PASS, None, "8-12 required")
    elif exp and exp.minimum_years == 8 and exp.maximum_years is None:
        add("experience_8_to_12", "Experience is the range 8-12 years, required", PARTIAL, EXTRACTION, "'8+' only: the stated maximum 12 was dropped")
    else:
        add("experience_8_to_12", "Experience is the range 8-12 years, required", FAIL, EXTRACTION, f"experience={exp.model_dump(exclude={'basis'}) if exp else None}")

    if edu is None:
        add("education_bachelor_required", "Bachelor's in Finance / Accounting / Economics / Business / related, required, not merged with the professional qualification", FAIL, EXTRACTION, "no education")
    else:
        deg, streams = " ".join(edu.degrees).lower(), " ".join(edu.streams).lower()
        merged = bool(_PROF_QUAL.search(" ".join(edu.degrees + edu.streams)))
        complete = "bachelor" in deg and all(k in streams for k in ("finance", "accounting", "economics", "business"))
        if edu.strength != "required" or merged or "bachelor" not in deg:
            add("education_bachelor_required", "Bachelor's in Finance / Accounting / Economics / Business / related, required, not merged with the professional qualification", FAIL, EXTRACTION,
                f"strength={edu.strength} merged_with_professional_qualification={merged} degrees={edu.degrees}")
        else:
            add("education_bachelor_required", "Bachelor's in Finance / Accounting / Economics / Business / related, required, not merged with the professional qualification",
                PASS if complete else PARTIAL, EXTRACTION, f"{edu.degrees} {edu.streams}")

    heads = [e.split(",")[0].strip().lower() for e in (loc.entries if loc else [])]
    if loc is None or heads != ["hyderabad"]:
        add("geography_hyderabad_single", "One geography: the city Hyderabad; no country area, radius or second place", FAIL, EXTRACTION, f"entries={heads} countries={loc.countries if loc else None}")
    elif loc.countries or loc.radius or intent.sourcing_paths:
        add("geography_hyderabad_single", "One geography: the city Hyderabad; no country area, radius or second place", FAIL, EXTRACTION, f"countries={loc.countries} radius={loc.radius} paths={len(intent.sourcing_paths)}")
    else:
        add("geography_hyderabad_single", "One geography: the city Hyderabad; no country area, radius or second place", PASS if loc.strength == "required" else PARTIAL, EXTRACTION, f"{loc.entries}/{loc.strength}")

    hybrid_text = bool(_find(cl, r"\bhybrid\b"))
    if loc and loc.remote == "allowed":
        add("work_mode_hybrid_typed", "Work mode is hybrid, typed; not remote, not on-site", FAIL, EXTRACTION, "remote=allowed invents remote acceptance")
    elif loc and loc.work_mode == "hybrid":
        add("work_mode_hybrid_typed", "Work mode is hybrid, typed; not remote, not on-site", PASS if loc.remote is None else PARTIAL, EXTRACTION,
            f"work_mode=hybrid remote={loc.remote}" + ("" if loc.remote is None else " (remote is not stated by the JD; an unneeded inference now that work_mode exists)"))
    elif loc and loc.work_mode in ("remote", "onsite"):
        add("work_mode_hybrid_typed", "Work mode is hybrid, typed; not remote, not on-site", FAIL, EXTRACTION, f"work_mode={loc.work_mode!r}")
    else:
        add("work_mode_hybrid_typed", "Work mode is hybrid, typed; not remote, not on-site", PARTIAL if hybrid_text else FAIL, EXTRACTION,
            f"work_mode is None; 'hybrid' in text={hybrid_text} (the typed field exists and was not used)")

    missing = [k for k, rx in _CORE.items() if not _find(cl, rx)]
    add("core_requirements_present", "Stated qualifications present (planning, budgeting, forecasting, variance, modeling, Excel, Power BI, presenting, partnering, communication, ERP, FP&A ownership)",
        PASS if not missing else (PARTIAL if len(missing) <= 2 else FAIL), EXTRACTION, f"missing {missing}" if missing else "all present")
    weakened = [k for k, rx in _CORE.items() if _find(cl, rx) and not any(c["strength"] == "required" for c in _find(cl, rx))]
    add("core_requirements_required", "Stated qualifications are not weakened to preferred/context", PASS if not weakened else (PARTIAL if len(weakened) <= 2 else FAIL), EXTRACTION,
        f"only preferred/context: {weakened}" if weakened else "none weakened")

    # ------------------------------------------------------------------ proficiency (depth only where the JD states it)
    excel = [s for s in intent.skills if re.search(r"\bexcel\b", s.name, I)]
    if not excel:
        add("excel_advanced", "Microsoft Excel is advanced proficiency", FAIL, EXTRACTION, "no Excel skill atom")
    elif any(s.proficiency == "advanced" for s in excel):
        add("excel_advanced", "Microsoft Excel is advanced proficiency", PASS if any(s.strength == "required" for s in excel) else PARTIAL, EXTRACTION, f"{[(s.name, s.proficiency, s.strength) for s in excel]}")
    elif any(s.proficiency is None or s.proficiency == "hands_on" for s in excel):
        add("excel_advanced", "Microsoft Excel is advanced proficiency", PARTIAL, EXTRACTION, f"the stated depth is lost or understated: {[(s.name, s.proficiency) for s in excel]}")
    else:
        add("excel_advanced", "Microsoft Excel is advanced proficiency", FAIL, EXTRACTION, f"{[(s.name, s.proficiency) for s in excel]}")

    pbi = [s for s in intent.skills if re.search(r"power ?bi", s.name, I)]
    pbi_group = [g for g in intent.skill_any_of if any(re.search(r"power ?bi", o, I) for o in g.any_of)]
    if any(s.proficiency in ("hands_on", "advanced") for s in pbi):
        add("power_bi_working_knowledge", "Power BI (or a similar BI/reporting platform) is working knowledge", FAIL, EXTRACTION, f"promoted: {[(s.name, s.proficiency) for s in pbi]}")
    elif any(s.proficiency == "working_knowledge" for s in pbi):
        keeps_alt = any(re.search(r"similar|business intelligence|reporting platform|\bbi\b.*\bor\b|\bor\b", s.name, I) for s in pbi if s.proficiency == "working_knowledge")
        add("power_bi_working_knowledge", "Power BI (or a similar BI/reporting platform) is working knowledge", PASS if keeps_alt else PARTIAL, EXTRACTION,
            f"{[(s.name, s.proficiency, s.strength) for s in pbi]}" + ("" if keeps_alt else "; 'or a similar platform' was dropped"))
    elif pbi or pbi_group:
        add("power_bi_working_knowledge", "Power BI (or a similar BI/reporting platform) is working knowledge", PARTIAL, EXTRACTION,
            "depth lost: " + ("an OR group carries no proficiency (the lossless form is one atom whose name carries 'or similar')" if pbi_group and not pbi else f"{[(s.name, s.proficiency) for s in pbi]}"))
    else:
        add("power_bi_working_knowledge", "Power BI (or a similar BI/reporting platform) is working knowledge", FAIL, EXTRACTION, "no Power BI atom")

    allowed = [(re.compile(r"\bexcel\b", I), {"advanced"}), (re.compile(r"power ?bi", I), {"working_knowledge"})]
    invented = [(s.name, s.proficiency) for s in intent.skills if s.proficiency and not any(rx.search(s.name) and s.proficiency in ok for rx, ok in allowed)]
    add("no_invented_proficiency", "Proficiency only on Excel (advanced) and Power BI (working knowledge); finance skills never promoted", PASS if not invented else FAIL, EXTRACTION,
        f"{invented}" if invented else "none")

    # ------------------------------------------------------------------ examples and OR groups
    sap_oracle = [s for s in intent.skills if re.match(r"\s*(sap|oracle)\b", s.name, I) and s.strength == "required"]
    erp = _find([c for c in cl if c["kind"] in ("skill", "any_of", "signal")], r"\berp\b|enterprise resource")
    if len(sap_oracle) >= 2:
        add("erp_examples_not_and", "ERP experience required; SAP / Oracle are examples, not two required skills", FAIL, EXTRACTION, f"examples promoted to an AND: {[s.name for s in sap_oracle]}")
    elif len(sap_oracle) == 1 or not erp:
        add("erp_examples_not_and", "ERP experience required; SAP / Oracle are examples, not two required skills", PARTIAL, EXTRACTION, f"sap/oracle required singly={[s.name for s in sap_oracle]} erp present={bool(erp)}")
    else:
        add("erp_examples_not_and", "ERP experience required; SAP / Oracle are examples, not two required skills", PASS, None, "ERP kept as one requirement")

    pq = [c for c in cl if c["kind"] in ("skill", "any_of", "signal", "domain") and _PROF_QUAL.search(c["text"])]
    if not pq:
        add("professional_qualification_preferred", "Professional qualification (CA / CMA / ACCA / MBA Finance) kept as a PREFERENCE", PARTIAL, EXTRACTION, "absent")
    elif any(c["strength"] == "required" for c in pq):
        add("professional_qualification_preferred", "Professional qualification (CA / CMA / ACCA / MBA Finance) kept as a PREFERENCE", FAIL, EXTRACTION, f"hardened to required: {[c['text'][:60] for c in pq if c['strength'] == 'required']}")
    else:
        add("professional_qualification_preferred", "Professional qualification (CA / CMA / ACCA / MBA Finance) kept as a PREFERENCE", PASS, None, f"{[(c['kind'], c['strength']) for c in pq]}")

    # ------------------------------------------------------------------ company / background preferences
    names_in_companies = {k for k, rx in COMPANIES.items() if any(re.search(rx, c.name, I) for c in intent.companies)}
    names_anywhere = {k for k, rx in COMPANIES.items() if k in names_in_companies or _find(cl, rx)}
    company_claims_required = [c.name for c in intent.companies if c.strength == "required"] + [c["text"][:50] for c in cl if c["strength"] == "required" and any(re.search(rx, c["text"], I) for rx in COMPANIES.values())]
    rel_bad = [(c.name, c.relationship) for c in intent.companies if c.relationship != "any"]
    if company_claims_required or intent.company_scale or any(c.relationship == "current" for c in intent.companies):
        add("company_preference_kept_as_preference", "Named companies kept as PREFERRED, relationship any; never required, current, or a scale filter", FAIL, EXTRACTION,
            f"required={company_claims_required} company_scale={intent.company_scale is not None} relationships={rel_bad}")
    elif len(names_in_companies) >= 5 and all(c.strength == "preferred" for c in intent.companies) and not rel_bad:
        add("company_preference_kept_as_preference", "Named companies kept as PREFERRED, relationship any; never required, current, or a scale filter", PASS, None, f"{sorted(names_in_companies)}")
    elif rel_bad or len(names_in_companies) >= 5:
        add("company_preference_kept_as_preference", "Named companies kept as PREFERRED, relationship any; never required, current, or a scale filter", PARTIAL, EXTRACTION,
            f"past/other relationship invented: {rel_bad}" if rel_bad else f"strengths={[c.strength for c in intent.companies]}")
    else:
        add("company_preference_kept_as_preference", "Named companies kept as PREFERRED, relationship any; never required, current, or a scale filter", PARTIAL, EXTRACTION,
            f"only {len(names_in_companies)} of 6 as companies; named anywhere: {sorted(names_anywhere)}")

    env = _find([c for c in cl if c["kind"] in ("signal", "domain", "skill")], _ENV.pattern)
    lead = [c for c in cl if c["kind"] in ("signal", "domain", "skill") and _COMM_LEADERSHIP.search(c["text"])]
    hard_env = [c["text"][:60] for c in env + lead if c["strength"] == "required"]
    if hard_env:
        add("background_preferences_preferred", "Large-enterprise and business-leadership-support backgrounds kept as preferences", FAIL, EXTRACTION, f"hardened to required: {hard_env}")
    elif env and lead:
        add("background_preferences_preferred", "Large-enterprise and business-leadership-support backgrounds kept as preferences", PASS, None, "both present as preferred/context")
    else:
        add("background_preferences_preferred", "Large-enterprise and business-leadership-support backgrounds kept as preferences", PARTIAL, EXTRACTION, f"environment={bool(env)} leadership-support={bool(lead)}")

    # ------------------------------------------------------------------ the one semantic exclusion
    sem = [x for x in intent.semantic_exclusions if re.search(r"audit|\btax\b|bookkeeping|transaction", " ".join([x.concept, *x.includes]), I)]
    if not sem:
        add("semantic_exclusion_faithful", "The audit / tax / bookkeeping / transaction-processing exclusion kept with its qualifier", FAIL, EXTRACTION, f"semantic_exclusions={[x.concept for x in intent.semantic_exclusions]}")
    else:
        text = " ".join([sem[0].concept, *sem[0].includes])
        terms = [t for t in ("audit", "tax", "bookkeeping", "transaction") if re.search(t, text, I)]
        qualified = bool(re.search(r"exclusive|\bonly\b", text, I)) and bool(re.search(r"without|lack|absence|no substantive|not (?:also )?have", text, I)) and bool(re.search(r"fp&a|business[- ]finance|substantive", text, I))
        if qualified and len(terms) == 4:
            add("semantic_exclusion_faithful", "The audit / tax / bookkeeping / transaction-processing exclusion kept with its qualifier", PASS, None, f"{text[:200]!r}")
        else:
            add("semantic_exclusion_faithful", "The audit / tax / bookkeeping / transaction-processing exclusion kept with its qualifier", PARTIAL, EXTRACTION,
                f"terms kept={terms}; qualifier ('exclusively ... without substantive FP&A') kept={qualified}: {text[:160]!r}")

    # ------------------------------------------------------------------ over-application (every one is a FAIL)
    add("no_sourcing_path_or_reconciliation", "No sourcing path, path-scoped structure or reconciliation (one strategy, no brief)",
        PASS if not (intent.sourcing_paths or intent.reconciliations) else FAIL, EXTRACTION, f"paths={[p.id for p in intent.sourcing_paths]} reconciliations={[r.topic for r in intent.reconciliations]}")
    extra_excl = [(x.kind, x.value) for x in intent.exclusions] + [("semantic", x.concept[:70]) for x in intent.semantic_exclusions[1:]]
    add("no_invented_exclusion", "No exclusion beyond the one stated (no company / title / industry exclusion, no second negative)", PASS if not extra_excl else FAIL, EXTRACTION, f"{extra_excl}")
    structure = []
    if sen and sen.leadership:
        structure.append(f"leadership={sen.leadership}")
    if sen and sen.alternatives:
        structure.append(f"seniority.alternatives={sen.alternatives}")
    if loc and loc.countries:
        structure.append(f"countries={loc.countries}")
    if loc and loc.remote == "allowed":
        structure.append("remote=allowed")
    dom_hard = [(d.name[:40], d.strength) for d in intent.domain if d.strength == "required"]
    if dom_hard:
        structure.append(f"domain required {dom_hard}")
    add("no_role_shape_structure", "No Role 1 / Role 2 structure the JD does not call for (leadership, alternatives, countries, remote, a required domain)",
        PASS if not structure else FAIL, EXTRACTION, "; ".join(structure) or "none")
    unsup = [(c.name, c.relationship) for c in intent.companies if c.relationship == "current"]
    rel = [(s.name[:40], s.relationship) for s in intent.skills if s.relationship != "any"] + [(" or ".join(g.any_of)[:40], g.relationship) for g in intent.skill_any_of if g.relationship != "any"]
    add("no_unsupported_temporal_relationship", "Every relationship is `any`: the JD states no current or past application", PASS if not (rel or unsup) else FAIL, EXTRACTION,
        f"non-any relationships: {rel + unsup}" if (rel or unsup) else "all any")
    hardened_resp = [k for k, rx in _RESPONSIBILITY_ONLY.items() if any(rx.search(c["text"]) and c["strength"] == "required" for c in cl)]
    resp_validator = report["cross_role_errors"].get("responsibility_only_required", 0)
    add("no_responsibility_hardening", "Responsibility-only statements are not required (reporting packs, automation, cross-functional work, ad hoc projects)",
        PASS if not (hardened_resp or resp_validator) else FAIL, EXTRACTION, f"required responsibility-only items={hardened_resp}; frozen validator responsibility_only_required={resp_validator}")
    pref_hard = [c["text"][:50] for c in pq + env + lead if c["strength"] == "required"] + company_claims_required
    add("no_preference_hardened", "No preference (qualification, environment, companies, leadership support) hardened into a requirement", PASS if not pref_hard else FAIL, EXTRACTION, f"{pref_hard}" if pref_hard else "none")

    # ------------------------------------------------------------------ provenance and validators
    from_brief = [a["ref"] for a in report["atoms"] if "recruiter_brief" in (a["claimed"] or [])]
    add("no_fabricated_brief_source", "No atom cites a recruiter brief (there is none)", PASS if not from_brief else FAIL, PROVENANCE, f"atoms citing recruiter_brief: {from_brief}" if from_brief else "none")
    status, cls, summary = provenance_status(report)
    add("provenance_preserved", "Every atom carries a verified JD basis; nothing required is inferred", status, PROVENANCE if cls else None, summary)
    errors = report["errors"]
    add("generic_validators_clean", "Frozen generic validators (base + cross-role): no ERROR", PASS if not errors else FAIL, VALIDATION, f"errors={errors}" if errors else "none fired")
    return out


def evaluate(intent: ExperimentalHiringIntent, jd: str) -> Dict[str, Any]:
    return {"critical": [r.to_dict() for r in evaluate_critical(intent, jd)], "validation": validate_cross_role(intent, jd, NO_BRIEF)}
