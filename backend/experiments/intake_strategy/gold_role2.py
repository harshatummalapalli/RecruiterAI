"""Gold evaluator for ROLE 2 cross-role validation (EXPERIMENT ONLY; never put in a prompt).

Encodes `ROLE2_GROUND_TRUTH.md`, which was written and committed BEFORE any model run. Nothing here depends on a model output.
Role 1's evaluator (`gold_experimental`) and prompt are untouched and are only reused where they are role-neutral (provenance
status, the frozen validators, the assertion record type).

The question this module answers is representation DISCIPLINE, not field utilisation: a smaller correct intent beats a richly
populated invented one. Every non-PASS carries one primary class:

    EXTRACTION       the current schema could say the correct thing and the model did not (includes over-application)
    REPRESENTATION   the current schema cannot say the correct thing; decided from the schema, never from the model
    RECONCILIATION   JD and brief merged or prioritised wrongly
    PROVENANCE       an atom's claimed source is missing, unsupported, misattributed, or inferred-but-required
    VALIDATION       a generic deterministic validator fired
    TAXONOMY         approved knowledge is insufficient (reported where it applies; the schema was not the cause)

Two meanings are NOT representable by the current schema and are recorded as REPRESENTATION by schema introspection
(`schema_gaps`): "advanced proficiency" (the proficiency enum stops at hands_on) and a "Hybrid" working basis (the `remote`
enum has allowed / not_allowed only). Their assertions can therefore never be PASS; the status says whether the model coped
with the nearest representation, or lost the fact (EXTRACTION), or invented something (EXTRACTION).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from backend.experiments.intake_strategy.experimental_schema import (
    PROFICIENCIES,
    REMOTE_VALUES,
    ExperimentalHiringIntent,
)
from backend.experiments.intake_strategy.gold_assertions import (
    EXTRACTION,
    FAIL,
    PARTIAL,
    PASS,
    RECONCILIATION,
    REPRESENTATION,
    VALIDATION,
    AssertionResult,
)
from backend.experiments.intake_strategy.gold_experimental import provenance_status
from backend.experiments.intake_strategy.validators import validate

PROVENANCE = "PROVENANCE"
I = re.IGNORECASE

# (key, pattern): a stated JD / brief fact, found anywhere in the intent's claim-bearing text
_ITEMS: Dict[str, "re.Pattern[str]"] = {
    "python": re.compile(r"\bpython\b", I), "java": re.compile(r"\bjava\b(?!\s*script)", I),
    "genai": re.compile(r"generative ai|\bgenai\b|\bgen ai\b", I),
    "llm": re.compile(r"\bllms?\b|large language model", I), "rag": re.compile(r"\brag\b|retrieval[- ]augmented", I),
    "agentic": re.compile(r"agentic", I), "prompt": re.compile(r"prompt engineering", I),
    "mcp": re.compile(r"\bmcp\b|model context protocol", I), "a2a": re.compile(r"\ba2a\b|agent[- ]to[- ]agent", I),
    "tensorflow": re.compile(r"tensorflow", I), "pytorch": re.compile(r"pytorch", I), "sklearn": re.compile(r"scikit", I),
    "azure": re.compile(r"\bazure\b(?!\s*devops)", I), "aws": re.compile(r"\baws\b|amazon web services", I),
    "devops": re.compile(r"ci/cd|ci-cd|\bcicd\b|continuous integration|terraform|github actions|containeri[sz]ed|docker|kubernetes|\baks\b|\beks\b|devops tools|devops practices", I),
    "react": re.compile(r"\breact\b", I), "bootstrap": re.compile(r"bootstrap", I),
    "snowflake": re.compile(r"snowflake", I), "databricks": re.compile(r"databricks", I),
    "data_integration": re.compile(r"data integration|integrat\w* (of )?data", I), "etl": re.compile(r"\betl\b", I),
    "data_quality": re.compile(r"data quality", I), "data_discovery": re.compile(r"data discovery", I),
    "data_management": re.compile(r"data management", I),
    "apis": re.compile(r"third[- ]party|enterprise apis?|integrating .{0,30}apis?|api integration", I),
    "azure_devops": re.compile(r"azure devops", I), "jira": re.compile(r"\bjira\b", I),
    "metadata": re.compile(r"metadata|data governance", I),
}
# facts the JD states as plain requirements: a `preferred`-only atom is a weakened requirement
_MUST_BE_REQUIRED = ("python", "java", "genai", "llm", "rag", "agentic", "prompt", "mcp", "a2a", "devops", "react", "bootstrap",
                     "snowflake", "databricks", "data_integration", "etl", "data_quality", "data_discovery", "data_management", "apis")
_SOFT = {
    "analytical": re.compile(r"analytical|problem[- ]solving|troubleshoot", I),
    "communication": re.compile(r"communicat|stakeholder management", I),
    "hands_on_engineering": re.compile(r"hands-on|enterprise[- ]scale", I),
    "solution_design": re.compile(r"solution design|architecture review|system design|design\w* (technical )?solutions", I),
}
# post-run correction: the "poc" pattern originally missed the plural "proofs of concept" that all five real runs used
_BRIEF = {
    "ic": re.compile(r"\bIC\b|individual contributor", re.I), "client": re.compile(r"\bclients?\b", I),
    "poc": re.compile(r"\bpocs?\b|proofs?[- ]of[- ]concept", I), "existing": re.compile(r"existing (products?|teams?|features?)", I),
    "hybrid": re.compile(r"\bhybrid\b", I), "fde": re.compile(r"forward[- ]deployed", I),
}
_PEOPLE_MGMT = re.compile(r"manag\w* (a |the )?(team|people|engineers|staff)|direct reports|people management|people leadership|line management|supervis", I)
_MENTOR_LEAD = re.compile(r"technical leadership|mentor|\blead(ing)? (a )?team", I)
_DENIES = re.compile(r"\b(not|no|never|without|rather than|instead of|other than|excluding|except|nor)\b|n't\b", I)
_PROFICIENCY_ALLOWED: List[Tuple["re.Pattern[str]", set]] = [
    (re.compile(r"azure devops|\bjira\b|metadata|data governance", I), {"working_knowledge"}),
    (re.compile(r"\bpython\b|\bjava\b(?!\s*script)|generative ai|\bgenai\b", I), {"hands_on"}),
]
_HARD_LEVELS = re.compile(r"\b(lead|principal|senior|director|manager|head|vp|distinguished|architect)\b", I)


def schema_gaps() -> Dict[str, Dict[str, Any]]:
    """Meanings in the ground truth that the CURRENT schema cannot state, decided from the schema's own enums."""
    return {
        "advanced_proficiency": {"representable": "advanced" in PROFICIENCIES, "values": list(PROFICIENCIES),
                                 "source": "JD: 'Advanced proficiency in Python and Java'"},
        "hybrid_work_mode": {"representable": "hybrid" in REMOTE_VALUES, "values": list(REMOTE_VALUES),
                             "source": "brief: 'need someone who can work on a Hybrid basis'"},
    }


# ---------------------------------------------------------------------------- claim helpers


def claims(intent: ExperimentalHiringIntent) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for s in intent.skills:
        out.append({"kind": "skill", "text": s.name, "strength": s.strength, "proficiency": s.proficiency, "group": None})
    for i, g in enumerate(intent.skill_any_of):
        for option in g.any_of:
            out.append({"kind": "any_of", "text": option, "strength": g.strength, "proficiency": None, "group": i})
    for e in intent.evidence_signals:
        out.append({"kind": "signal", "text": e.name, "strength": e.strength, "proficiency": None, "group": None})
    for d in intent.domain:
        out.append({"kind": "domain", "text": d.name, "strength": d.strength, "proficiency": None, "group": None})
    if intent.education:
        out.append({"kind": "education", "text": " ".join(intent.education.degrees + intent.education.streams), "strength": intent.education.strength,
                    "proficiency": None, "group": None})
    return out


def _find(cl: List[Dict[str, Any]], rx: "re.Pattern[str]") -> List[Dict[str, Any]]:
    return [c for c in cl if rx.search(c["text"])]


def present_items(intent: ExperimentalHiringIntent) -> Dict[str, List[Dict[str, Any]]]:
    cl = [c for c in claims(intent) if c["kind"] != "education"]
    return {k: _find(cl, rx) for k, rx in _ITEMS.items()}


def _loc(intent: ExperimentalHiringIntent):
    return intent.location


# ---------------------------------------------------------------------------- evaluation


def evaluate_critical(intent: ExperimentalHiringIntent, jd: str, brief: str) -> List[AssertionResult]:
    out: List[AssertionResult] = []
    report = validate(intent, jd, brief)
    cl = claims(intent)
    items = present_items(intent)
    gaps = schema_gaps()

    def add(id_: str, title: str, status: str, cls: Optional[str], evidence: str) -> None:
        out.append(AssertionResult(id_, title, status, None if status == PASS else cls, evidence))

    # ---------------------------------------------------------------- fidelity
    exp = intent.experience
    if exp and exp.minimum_years == 12 and exp.strength == "required" and not exp.maximum_years:
        add("fidelity_experience_12", "12+ years, required, a single record", PASS, None, f"{exp.minimum_years}+/{exp.strength}")
    elif exp and exp.minimum_years == 12:
        add("fidelity_experience_12", "12+ years, required, a single record", PARTIAL, EXTRACTION, f"12 but strength={exp.strength} max={exp.maximum_years}")
    else:
        add("fidelity_experience_12", "12+ years, required, a single record", FAIL, EXTRACTION, f"experience={exp.model_dump(exclude={'basis'}) if exp else None}")

    edu = intent.education
    if edu is None:
        add("fidelity_education", "Bachelor's or Master's in CS / IT / Software Engineering / related, required", FAIL, EXTRACTION, "no education")
    else:
        deg = " ".join(edu.degrees).lower()
        streams = " ".join(edu.streams).lower()
        ok = "bachelor" in deg and "master" in deg and "computer science" in streams and "information technology" in streams and "software engineering" in streams
        extra = [s for s in edu.streams if not re.search(r"computer science|information technology|software engineering|related", s, I)]
        if ok and edu.strength == "required" and not extra:
            add("fidelity_education", "Bachelor's or Master's in CS / IT / Software Engineering / related, required", PASS, None, f"{edu.degrees} {edu.streams}")
        else:
            add("fidelity_education", "Bachelor's or Master's in CS / IT / Software Engineering / related, required", PARTIAL, EXTRACTION,
                f"complete={ok} strength={edu.strength} invented streams={extra}")

    # Python AND Java: both present, required, and not collapsed into an OR group
    py, jv = items["python"], items["java"]
    collapsed = bool({c["group"] for c in py if c["kind"] == "any_of"} & {c["group"] for c in jv if c["kind"] == "any_of"})
    if not py or not jv:
        add("fidelity_python_and_java", "Python AND Java, both required", FAIL, EXTRACTION, f"python={bool(py)} java={bool(jv)}")
    elif collapsed:
        add("fidelity_python_and_java", "Python AND Java, both required", FAIL, EXTRACTION, "Python and Java placed in one OR group (the JD requires both)")
    elif not (any(c["strength"] == "required" for c in py) and any(c["strength"] == "required" for c in jv)):
        add("fidelity_python_and_java", "Python AND Java, both required", PARTIAL, EXTRACTION, "present but not required")
    else:
        add("fidelity_python_and_java", "Python AND Java, both required", PASS, None, "both present and required")

    def coverage(id_: str, title: str, keys: Tuple[str, ...], tolerance: int) -> None:
        missing = [k for k in keys if not items[k]]
        if not missing:
            add(id_, title, PASS, None, "all present")
        elif len(missing) <= tolerance:
            add(id_, title, PARTIAL, EXTRACTION, f"missing {missing}")
        else:
            add(id_, title, FAIL, EXTRACTION, f"missing {missing}")

    coverage("fidelity_genai_and_ai_concepts", "Generative AI (production) and LLM / RAG / Agentic AI / Prompt Engineering / MCP / A2A", ("genai", "llm", "rag", "agentic", "prompt", "mcp", "a2a"), 2)
    coverage("fidelity_devops_ui_data_apis", "DevOps/CI-CD, React, Bootstrap, Snowflake, Databricks, data topics, API integration",
             ("devops", "react", "bootstrap", "snowflake", "databricks", "data_integration", "etl", "data_quality", "data_discovery", "data_management", "apis"), 3)
    coverage("fidelity_familiarity_items", "Azure DevOps, Jira, metadata management / data governance present", ("azure_devops", "jira", "metadata"), 1)

    def or_group(id_: str, title: str, keys: Tuple[str, ...]) -> None:
        found = {k: items[k] for k in keys if items[k]}
        separate = [k for k, v in found.items() if any(c["kind"] == "skill" for c in v) and not any(c["kind"] == "any_of" for c in v)]
        if len(found) < len(keys):
            add(id_, title, PARTIAL if found else FAIL, EXTRACTION, f"missing {[k for k in keys if k not in found]}")
        elif len(separate) >= 2:
            add(id_, title, FAIL, EXTRACTION, f"OR group turned into separate skills (an AND): {separate}")
        else:
            add(id_, title, PASS, None, f"options kept: {sorted(found)}; kinds={sorted({c['kind'] for v in found.values() for c in v})}")

    or_group("fidelity_cloud_or", "Azure and/or AWS kept as alternatives", ("azure", "aws"))
    or_group("fidelity_ml_libraries_or", "TensorFlow / PyTorch / scikit-learn kept as alternatives", ("tensorflow", "pytorch", "sklearn"))

    soft_missing = [k for k, rx in _SOFT.items() if not _find(cl, rx)]
    add("fidelity_soft_and_engineering", "Analytical, communication, hands-on engineering, solution design retained",
        PASS if not soft_missing else (PARTIAL if len(soft_missing) <= 2 else FAIL), EXTRACTION, f"missing {soft_missing}" if soft_missing else "all present")

    brief_claims = [c for c in cl if c["kind"] in ("signal", "domain", "skill")]
    ic, client, poc, existing = (bool(_find(brief_claims, _BRIEF[k])) for k in ("ic", "client", "poc", "existing"))
    seniority_text = intent.seniority.value if intent.seniority else ""
    ic = ic or bool(_BRIEF["ic"].search(seniority_text))
    if not ic:
        add("fidelity_brief_profile", "Brief profile kept: IC engineer; client problem design; POCs; existing products/teams", FAIL, EXTRACTION, f"ic={ic} client={client} poc={poc} existing={existing}")
    elif client and poc and existing:
        add("fidelity_brief_profile", "Brief profile kept: IC engineer; client problem design; POCs; existing products/teams", PASS, None, "all present")
    else:
        add("fidelity_brief_profile", "Brief profile kept: IC engineer; client problem design; POCs; existing products/teams", PARTIAL, EXTRACTION, f"ic={ic} client={client} poc={poc} existing={existing}")

    fam = [f.strip().lower() for f in intent.role_family]
    fam_ok = {"software engineer", "solution architect"}
    extra_fam = [f for f in fam if not any(k in f for k in fam_ok)]
    got = {k for k in fam_ok if any(k in f for f in fam)}
    if extra_fam:
        add("fidelity_role_family", "Role family = Software Engineer, Solution Architect (the JD title), nothing added", FAIL, EXTRACTION, f"invented titles {extra_fam}")
    elif got == fam_ok:
        add("fidelity_role_family", "Role family = Software Engineer, Solution Architect (the JD title), nothing added", PASS, None, str(fam))
    else:
        add("fidelity_role_family", "Role family = Software Engineer, Solution Architect (the JD title), nothing added", PARTIAL, EXTRACTION, f"only {sorted(got)}")

    sen = intent.seniority
    if sen is None:
        add("seniority_staff", "Seniority is Staff (the JD title), nothing stronger", PARTIAL, EXTRACTION, "the title's level was dropped")
    elif "staff" in sen.value.lower() and not sen.alternatives and not sen.leadership:
        add("seniority_staff", "Seniority is Staff (the JD title), nothing stronger", PASS, None, f"{sen.value}/{sen.strength}")
    else:
        add("seniority_staff", "Seniority is Staff (the JD title), nothing stronger", FAIL, EXTRACTION,
            f"value={sen.value!r} alternatives={sen.alternatives} leadership={sen.leadership} (the production prompt's level vocabulary has no 'Staff'; knowledge/seniority.json has none either)")

    loc = _loc(intent)
    heads = [e.split(",")[0].strip().lower() for e in (loc.entries if loc else [])]
    if loc is None or heads != ["hyderabad"]:
        add("fidelity_geography_hyderabad", "Geography: city Hyderabad, no country area, no radius", FAIL, EXTRACTION, f"entries={heads} countries={loc.countries if loc else None}")
    elif loc.countries or loc.radius or loc.strength != "required":
        add("fidelity_geography_hyderabad", "Geography: city Hyderabad, no country area, no radius", PARTIAL, EXTRACTION,
            f"countries={loc.countries} radius={loc.radius} strength={loc.strength}")
    else:
        add("fidelity_geography_hyderabad", "Geography: city Hyderabad, no country area, no radius", PASS, None, f"{loc.entries}")

    weakened = [k for k in _MUST_BE_REQUIRED if items[k] and not any(c["strength"] == "required" for c in items[k])]
    add("strength_requirements_not_weakened", "Stated requirements are not weakened to preferred/context", PASS if not weakened else (PARTIAL if len(weakened) <= 2 else FAIL),
        EXTRACTION, f"only preferred/context: {weakened}" if weakened else "none weakened (the sources contain no preference wording)")

    # ---------------------------------------------------------------- over-application (every one is a FAIL)
    add("no_second_path", "No sourcing path / path-scoped structure invented", PASS if not (intent.sourcing_paths or any(r.path_id for r in intent.reconciliations)) else FAIL,
        EXTRACTION, f"paths={[p.id for p in intent.sourcing_paths]} path-scoped reconciliations={[r.topic for r in intent.reconciliations if r.path_id]}")

    excl = [(x.kind, x.value) for x in intent.exclusions] + [("semantic", x.concept) for x in intent.semantic_exclusions]
    add("no_invented_exclusion", "No exclusion invented (none is stated)", PASS if not excl else FAIL, EXTRACTION, f"exclusions={excl}")

    hardened = []
    if any(_BRIEF["fde"].search(f) for f in intent.role_family) or any(_BRIEF["fde"].search(c.name) for c in intent.companies):
        hardened.append("'Forward Deployed Engineer' analogy turned into a title / company")
    if sen and _BRIEF["fde"].search(sen.value):
        hardened.append("analogy used as the seniority")
    for k in ("azure_devops", "jira", "metadata"):
        if any(c["proficiency"] == "hands_on" for c in items[k]):
            hardened.append(f"'Familiarity' item {k} marked hands_on")
    add("no_preference_hardened", "No analogy or 'familiarity' wording hardened into a stronger requirement", PASS if not hardened else FAIL, EXTRACTION, "; ".join(hardened) or "none")

    used = []
    if intent.sourcing_paths:
        used.append("sourcing_paths")
    if intent.semantic_exclusions:
        used.append("semantic_exclusions")
    if sen and sen.leadership:
        used.append(f"leadership={sen.leadership}")
    if sen and sen.alternatives:
        used.append(f"seniority.alternatives={sen.alternatives}")
    if loc and loc.countries:
        used.append(f"countries={loc.countries}")
    if loc and loc.remote == "allowed":
        used.append("remote=allowed")
    dom = [(d.name[:50], d.strength) for d in intent.domain if d.strength in ("required", "preferred")]
    if dom:
        used.append(f"domain={dom}")
    add("no_role1_concepts", "No Role 1 concept used that the sources do not call for", PASS if not used else FAIL, EXTRACTION, "; ".join(used) or "none used")

    comp = [("companies", c.name) for c in intent.companies] + ([("company_scale", intent.company_scale.minimum_employees)] if intent.company_scale else []) + \
           [(x.kind, x.value) for x in intent.exclusions if "company" in x.kind]
    add("no_company_filter", "No company constraint inferred (none is stated)", PASS if not comp else FAIL, EXTRACTION, f"{comp}")

    hard_seniority = []
    if sen and _HARD_LEVELS.search(sen.value) and "staff" not in sen.value.lower():
        hard_seniority.append(f"seniority value {sen.value!r}")
    if sen and sen.leadership:
        hard_seniority.append(f"seniority.leadership {sen.leadership}")
    mgmt = [c["text"] for c in cl if c["strength"] == "required" and c["kind"] in ("signal", "skill") and _PEOPLE_MGMT.search(c["text"]) and not _DENIES.search(c["text"])]
    if mgmt:
        hard_seniority.append(f"required people-management atom {mgmt}")
    mentor = [c["text"] for c in cl if c["strength"] == "required" and c["kind"] in ("signal", "skill") and _MENTOR_LEAD.search(c["text"]) and not _DENIES.search(c["text"])]
    if hard_seniority:
        add("no_hard_seniority_from_responsibilities", "No hard seniority / people-leadership requirement inferred from responsibility language", FAIL, EXTRACTION, "; ".join(hard_seniority))
    elif mentor:
        add("no_hard_seniority_from_responsibilities", "No hard seniority / people-leadership requirement inferred from responsibility language", PARTIAL, EXTRACTION,
            f"a responsibility ('technical leadership / mentor') was hardened into a required atom (the Requirements section asks for none; the brief says IC): {mentor}")
    else:
        add("no_hard_seniority_from_responsibilities", "No hard seniority / people-leadership requirement inferred from responsibility language", PASS, None, "none")

    bad_prof = []
    for s in intent.skills:
        if s.proficiency is None:
            continue
        allowed = next((a for rx, a in _PROFICIENCY_ALLOWED if rx.search(s.name)), set())
        if s.proficiency not in allowed:
            bad_prof.append((s.name, s.proficiency, sorted(allowed) or "no depth is stated for this item"))
    add("no_invented_proficiency", "No proficiency invented (only where the source states a depth, and not contradicted)", PASS if not bad_prof else FAIL, EXTRACTION, f"{bad_prof}" if bad_prof else "none")

    # ---------------------------------------------------------------- the two schema gaps (never PASS)
    pj = [s for s in intent.skills if re.search(r"\bpython\b|\bjava\b(?!\s*script)", s.name, I)]
    advanced_in_text = any(re.search(r"advanced", c["text"], I) for c in cl)
    if any(s.proficiency == "working_knowledge" for s in pj):
        add("advanced_proficiency", "Python/Java 'advanced proficiency' (schema cannot state 'advanced')", FAIL, EXTRACTION, "working_knowledge understates 'advanced'")
    elif not pj:
        add("advanced_proficiency", "Python/Java 'advanced proficiency' (schema cannot state 'advanced')", FAIL, EXTRACTION, "Python/Java absent")
    else:
        add("advanced_proficiency", "Python/Java 'advanced proficiency' (schema cannot state 'advanced')", PARTIAL, REPRESENTATION,
            f"proficiency={[ (s.name, s.proficiency) for s in pj]}; 'advanced' in text={advanced_in_text}; the enum {gaps['advanced_proficiency']['values']} has no value for it")
    remote = loc.remote if loc else None
    hybrid_text = bool(_find(cl, _BRIEF["hybrid"])) or bool(loc and any(_BRIEF["hybrid"].search(e) for e in loc.entries))
    if remote == "allowed":
        add("hybrid_work_mode", "Hybrid working basis (schema cannot state 'hybrid')", FAIL, EXTRACTION, "remote=allowed invents full remote work (the brief says Hybrid)")
    elif remote == "not_allowed" or hybrid_text:
        add("hybrid_work_mode", "Hybrid working basis (schema cannot state 'hybrid')", PARTIAL, REPRESENTATION,
            f"coped with the nearest representation: remote={remote}, 'hybrid' in text={hybrid_text}; the enum {gaps['hybrid_work_mode']['values']} has no hybrid")
    else:
        add("hybrid_work_mode", "Hybrid working basis (schema cannot state 'hybrid')", FAIL, EXTRACTION, "the Hybrid fact was lost entirely")

    # ---------------------------------------------------------------- reconciliation, provenance, validators
    tech = [rx for k, rx in _ITEMS.items()]
    invented = [(r.topic, r.action) for r in intent.reconciliations if r.action in ("waived", "contradicted", "narrowed") and any(rx.search(r.topic) for rx in tech)]
    spurious = [r.topic for r in intent.reconciliations if r.action == "unresolved"]
    if invented:
        add("reconciliation_discipline", "No JD requirement waived/narrowed/contradicted without a brief statement; no invented conflict", FAIL, RECONCILIATION,
            f"the brief mentions no technology or qualification, yet: {invented}")
    elif spurious:
        add("reconciliation_discipline", "No JD requirement waived/narrowed/contradicted without a brief statement; no invented conflict", PARTIAL, RECONCILIATION,
            f"'unresolved' records for a conflict the sources do not contain: {spurious}")
    else:
        add("reconciliation_discipline", "No JD requirement waived/narrowed/contradicted without a brief statement; no invented conflict", PASS, None,
            f"{len(intent.reconciliations)} record(s): {[(r.topic, r.action) for r in intent.reconciliations]}")

    status, cls, summary = provenance_status(report)
    add("provenance_preserved", "Every atom carries a verified basis; nothing required is inferred", status, PROVENANCE if cls else None, summary)
    loc_atom = next((a for a in report["atoms"] if a["kind"] == "location"), None)
    if loc_atom is None:
        add("provenance_location_from_brief", "Hyderabad is attributed to the recruiter brief (the JD has no location)", FAIL, EXTRACTION, "no location atom")
    else:
        ok = loc_atom["label"] == "added_by_brief" and loc_atom["status"] in ("verified", "lexical")
        add("provenance_location_from_brief", "Hyderabad is attributed to the recruiter brief (the JD has no location)", PASS if ok else FAIL, PROVENANCE,
            f"claimed={loc_atom['claimed']} status={loc_atom['status']} label={loc_atom['label']}")
    errors = report["errors"]
    add("generic_validators_clean", "Generic validators: no error", PASS if not errors else FAIL, VALIDATION, f"errors={errors}" if errors else "none fired")
    return out


def evaluate(intent: ExperimentalHiringIntent, jd: str, brief: str) -> Dict[str, Any]:
    return {"schema_gaps": schema_gaps(), "critical": [r.to_dict() for r in evaluate_critical(intent, jd, brief)], "validation": validate(intent, jd, brief)}
