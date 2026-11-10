"""Translate new-engine objects into the dayzero.partners frontend contract.

The frontend shapes (SearchIntent, IntakeResult/RoleUnderstanding, SearchResponse)
were built for the legacy "brain", so they carry fields the new engine deliberately
dropped: candidate_archetype, role_interpretation, seniority_scope, leadership_type,
and consequence-framed questions. We map everything the engine DOES produce and leave
those legacy-only fields empty — they are the Phase-2 frontend trim targets, marked
`# brain-only -> trim` below. No intelligence is re-created here; this is pure shaping.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from recruiter.agents.briefing.query import build_nl_query
from recruiter.agents.ranking.summary import evidence_summary
from recruiter.role_model import Location, RoleModel

# Explicit exclusion phrasing in the raw notes. High precision on purpose — a
# false nudge is worse than a missed one — so it matches clear "exclude people/
# companies" language, not every "not".
_EXCLUSION_INTENT_RE = re.compile(
    r"\b(?:not from|no one from|nobody from|not at|don'?t want|do not want|"
    r"avoid candidates|exclude\b|no\s+candidates\s+from|not\s+a\s+manager|no\s+managers)\b", re.I)


def _dropped_negative_nudge(raw_input: Optional[str], model: RoleModel) -> Optional[str]:
    """Free-text exclusions are deliberately NOT turned into filters. When the notes
    clearly ask for one but nothing was excluded, say so plainly instead of dropping
    it silently (CoWork's negative-ask finding). Suppressed only by a RECRUITER-set
    company exclusion — not by default exec TITLE exclusions (every IC role has them)
    nor by the automatic hiring-company exclusion (always present as 'current: <co>')."""
    hiring = (model.hiring_company or "").strip().lower()
    recruiter_excludes = {
        c.strip().lower() for c in (*model.companies.exclude_current, *model.companies.exclude_ever)
    } - {hiring, ""}
    if recruiter_excludes:
        return None  # the recruiter set a real company exclusion — nothing was dropped
    if raw_input and _EXCLUSION_INTENT_RE.search(raw_input):
        return ("Your notes look like they ask to exclude some companies or titles. I don't turn "
                "free-text exclusions into filters automatically — add companies under Exclude "
                "companies in the boundary, or titles in Refine, so they're actually enforced.")
    return None


# --- small shape helpers -----------------------------------------------------

def _fv(value: Optional[str], evidence: Optional[str] = None, source: Optional[str] = None) -> Dict[str, Any]:
    return {"value": value, "evidence": evidence, "source": source}


def _cap_item(req) -> Dict[str, Any]:
    return {"value": req.text, "tier_signal": req.tier, "evidence": req.provenance.evidence}


def _capability_core(group) -> Dict[str, Any]:
    """Show the role-defining capability AS a core requirement. The reader tiers
    required skills into the capability group + strong_signals (not
    hard_requirements, to avoid over-filtering), which otherwise leaves the brief's
    core list empty even though the capability IS the role's required skill."""
    shown = ", ".join(group.terms[:5])
    return {"value": f"{group.label} ({shown})" if shown else group.label,
            "tier_signal": "core", "evidence": None}


def _core_capabilities(model) -> list:
    return [_capability_core(g) for g in model.capability_groups] + [_cap_item(r) for r in model.tier("core")]


def _display_core(model) -> list:
    """The brief's 'Core requirements' list, as text: the role-defining capability
    label(s), then the reader's core requirements, then any recruiter-marked hard
    requirement not already shown. Mirrors `_core_capabilities` so the brief's Core
    section and its summary count agree and are never empty when cores exist."""
    labels = [g.label for g in model.capability_groups]
    cores = [r.text for r in model.tier("core")]
    seen = set(labels) | set(cores)
    extra_hard = [r.text for r in model.hard_requirements if r.text not in seen]
    return labels + cores + extra_hard


# The ONLY thing that blocks the search (decision "ask") is the mandatory years
# clarification — and that only fires when the recruiter left years off the first
# step. Everything else, the capability included, is resolved as a stated
# ASSUMPTION (decision "tell"): the engine takes the sensible default (require the
# role-defining capability), shows the brief straight away, and states what it
# assumed as a recruiter note the recruiter can override in the requirements — no
# back-and-forth decision card before the brief is shown.
_BLOCKING_ISSUES = {"min_years"}
# Optional, INTERACTIVE refinements: rendered as answerable choice cards in the
# brief (the recruiter can act on them) but they never block Search. Everything
# else that isn't blocking stays a read-only "tell" insight.
_OFFER_ISSUES = {"capability", "specialization", "stack", "track"}


def _capability_assumption(model) -> Optional[str]:
    """State the capability assumption the engine made, so the brief says what it
    did rather than asking. Rendered as a recruiter note; the item itself also
    appears (inferred) in the Core requirements, where it can be removed to widen."""
    groups = list(model.capability_groups)
    if not groups:
        return None
    g = groups[0]
    shown = ", ".join(g.terms[:6])
    terms = f" (any of: {shown})" if shown else ""
    article = "an" if g.label[:1].lower() in "aeiou" else "a"
    return (f"I'm treating this as {article} {g.label} role and requiring evidence of it{terms}. "
            "It's enforced in the search — remove it from the core requirements above if "
            "the role is broader than that.")


def _issue(q, insight_text: Optional[str] = None) -> Dict[str, Any]:
    decision = "ask" if q.id in _BLOCKING_ISSUES else "offer" if q.id in _OFFER_ISSUES else "tell"
    return {
        "issue": q.id, "decision": decision,
        "id": q.id, "reasoning": None,
        "question": q.prompt, "options": [{"value": o, "label": o} for o in q.options],
        "consequence_if_answer_a": None, "consequence_if_answer_b": None,  # brain-only -> trim
        "insight_text": insight_text, "injected_by_backstop": False, "backstop_category": None,
    }


def _locations(loc: Location) -> List[Dict[str, Any]]:
    country = loc.countries[0] if loc.countries else None
    state = loc.states[0] if loc.states else None
    if loc.cities:
        return [{"city": c, "state": state, "country": country} for c in loc.cities]
    return [{"city": None, "state": state, "country": country}]


# --- engine -> SearchIntent --------------------------------------------------

def _search_intent(*, title, employment_type, cores, supporting, diffs, location, min_years, max_years,
                   exclude_titles, exclude_current, exclude_ever, prefer_ever, hard, nl, kw_groups) -> Dict[str, Any]:
    return {
        "role": {"title": title, "seniority": None, "employment_type": employment_type, "confidence_score": None},
        "location": location,
        "experience": {"minimum_years": min_years, "maximum_years": max_years, "confidence_score": None},
        "titles": {"include_titles": [], "exclude_titles": list(exclude_titles), "confidence_score": None},
        "skills": {"required_skills": cores, "preferred_skills": supporting, "required_weight": None,
                   "preferred_weight": None, "confidence_score": None},
        "previous_background": {"preferred_technologies": [], "preferred_companies": list(prefer_ever),
                                "confidence_score": None},
        "ai_focus": {"llm": False, "rag": False, "agentic_ai": False, "mcp": False, "semantic_kernel": False,
                     "confidence_score": None},  # brain-only -> trim
        "company_preferences": {"exclude_current_companies": list(exclude_current), "preferred_company_types": [],
                                "exclude_companies_ever": list(exclude_ever),
                                "preferred_companies_ever": list(prefer_ever), "confidence_score": None},
        "ranking": {"must_have": hard, "nice_to_have": supporting, "bonus": diffs, "confidence_score": None},
        "confidence_score": None, "natural_language_search_query": nl,
        "core_signals": cores, "supporting_signals": supporting, "differentiator_signals": diffs,
        "must_have_keywords": [], "must_have_keyword_groups": kw_groups,
    }


def to_search_intent(model: RoleModel) -> Dict[str, Any]:
    loc = model.location
    return _search_intent(
        title=model.identity, employment_type=model.employment_type,
        cores=[r.text for r in model.tier("core")], supporting=[r.text for r in model.tier("supporting")],
        diffs=[r.text for r in model.tier("differentiator")],
        location={"countries": list(loc.countries), "states": list(loc.states), "cities": list(loc.cities),
                  "work_mode": loc.work_mode, "radius_place": loc.radius_place, "radius_miles": loc.radius_miles,
                  "confidence_score": None},
        min_years=model.seniority.min_years, max_years=model.seniority.max_years,
        exclude_titles=model.exclude_titles, exclude_current=model.companies.exclude_current,
        exclude_ever=model.companies.exclude_ever, prefer_ever=model.companies.prefer_ever,
        hard=[r.text for r in model.hard_requirements], nl=build_nl_query(model),
        kw_groups=[list(g.terms) for g in model.capability_groups])


def to_search_intent_from_understanding(u) -> Dict[str, Any]:
    """Pre-boundary /parse-jd view: the JD read alone, before the recruiter's
    boundary (so location/company are empty)."""
    reqs = lambda tier: [r.text for r in u.requirements if r.tier == tier]  # noqa: E731
    return _search_intent(
        title=u.identity, employment_type=u.employment_type,
        cores=reqs("core"), supporting=reqs("supporting"), diffs=reqs("differentiator"),
        location={"countries": [], "states": [], "cities": [], "work_mode": u.work_mode_in_notes,
                  "radius_place": None, "radius_miles": None, "confidence_score": None},
        min_years=u.min_years, max_years=u.max_years,
        exclude_titles=(), exclude_current=(), exclude_ever=(), prefer_ever=(),
        hard=[], nl=None, kw_groups=[])


# --- engine -> IntakeResult (the brief) --------------------------------------

def to_intake_result(raw_input: str, model: RoleModel, questions: Sequence, status: str) -> Dict[str, Any]:
    exclusions = list(model.exclude_titles) + [f"current: {c}" for c in model.companies.exclude_current]
    role_understanding = {
        "posted_title": model.posted_title,
        "posted_title_source": model.posted_title_source,
        "primary_candidate_identity": _fv(model.identity, source="inferred"),
        "hiring_company": _fv(model.hiring_company, source="recruiter" if model.hiring_company else None),
        "candidate_archetype": _fv(None),      # brain-only -> trim
        "role_interpretation": _fv(None),      # brain-only -> trim
        "seniority_scope": _fv(None),          # brain-only -> trim
        "leadership_type": _fv(None),          # brain-only -> trim
        "core_capabilities": _core_capabilities(model),
        "supporting_capabilities": [_cap_item(r) for r in model.tier("supporting")],
        "differentiators": [_cap_item(r) for r in model.tier("differentiator")],
        "technologies_mentioned": [{"category": g.label, "items": list(g.terms)} for g in model.capability_groups],
        "domain": list(model.industries),
        "explicit_constraints": {
            "locations": _locations(model.location),
            "work_mode": model.location.work_mode,
            "experience_minimum_years": model.seniority.min_years,
            "experience_maximum_years": model.seniority.max_years,
            "employment_type": model.employment_type,
            "exclusions": exclusions,
        },
        "open_questions": [q.prompt for q in questions if q.kind != "min_years"],
    }
    cap_insight = _capability_assumption(model)
    decision = {
        "issues": [_issue(q, cap_insight if q.id == "capability" else None) for q in questions],
        "recommended_ask_count": len(list(questions)),
        "stop_reasoning": None,
        "warnings": [],
        "search_consequence_summary": None,   # brain-only -> trim
        "limitations": [*model.limitations, *( [n] if (n := _dropped_negative_nudge(raw_input, model)) else [] )],
        "final_search_intent": {
            # The brief's "Core" list: the role-defining capability leads, then the
            # reader's core requirements, then any recruiter-marked dealbreaker not
            # already shown. Without the tier("core") items a role with no inferred
            # capability showed "No core requirements" while 5 were really in play.
            "hard_requirements": _display_core(model),
            "strong_signals": [r.text for r in model.tier("supporting")],
            "preferred_differentiators": [r.text for r in model.tier("differentiator")],
            "natural_language_search_query": build_nl_query(model),
            "exclusions": list(model.exclude_titles),
            "evidence": {r.text: r.provenance.evidence for r in model.requirements if r.provenance.evidence},
        },
    }
    return {"raw_input": raw_input, "role_understanding": role_understanding,
            "decision": decision, "status": status}


def to_intake_result_reading(raw_input: str) -> Dict[str, Any]:
    """Placeholder brief while the reader (LLM) is still running on a background
    thread. status 'understanding' tells the frontend to hold the "Reading the
    role…" state and poll GET /intake/{id} until it flips to ready — the read no
    longer blocks the POST /intake/start request (no 30s held connection)."""
    empty_ru = {
        "posted_title": None, "posted_title_source": None,
        "primary_candidate_identity": _fv(None), "hiring_company": _fv(None),
        "candidate_archetype": _fv(None), "role_interpretation": _fv(None),
        "seniority_scope": _fv(None), "leadership_type": _fv(None),
        "core_capabilities": [], "supporting_capabilities": [], "differentiators": [],
        "technologies_mentioned": [], "domain": [],
        "explicit_constraints": {"locations": [], "work_mode": None,
                                 "experience_minimum_years": None, "experience_maximum_years": None,
                                 "employment_type": None, "exclusions": []},
        "open_questions": [],
    }
    decision = {"issues": [], "recommended_ask_count": 0, "stop_reasoning": None, "warnings": [],
                "search_consequence_summary": None, "limitations": [],
                "final_search_intent": {"hard_requirements": [], "strong_signals": [],
                                        "preferred_differentiators": [], "natural_language_search_query": None,
                                        "exclusions": [], "evidence": {}}}
    return {"raw_input": raw_input, "role_understanding": empty_ru, "decision": decision,
            "status": "understanding"}


def to_intake_result_pending(raw_input: str, u, questions: Sequence) -> Dict[str, Any]:
    """The not-ready brief (e.g. missing years): built from the Understanding, with
    the blocking clarification as the open issue. No model exists yet."""
    def caps(tier):
        return [{"value": r.text, "tier_signal": r.tier, "evidence": r.evidence}
                for r in u.requirements if r.tier == tier]
    role_understanding = {
        "posted_title": u.posted_title, "posted_title_source": u.posted_title_source,
        "primary_candidate_identity": _fv(u.identity, source="inferred"),
        "hiring_company": _fv(None), "candidate_archetype": _fv(None), "role_interpretation": _fv(None),
        "seniority_scope": _fv(None), "leadership_type": _fv(None),
        "core_capabilities": caps("core"), "supporting_capabilities": caps("supporting"),
        "differentiators": caps("differentiator"), "technologies_mentioned": [], "domain": [],
        "explicit_constraints": {"locations": [], "work_mode": u.work_mode_in_notes,
                                 "experience_minimum_years": u.min_years, "experience_maximum_years": u.max_years,
                                 "employment_type": u.employment_type, "exclusions": []},
        "open_questions": [q.prompt for q in questions],
    }
    decision = {"issues": [_issue(q) for q in questions], "recommended_ask_count": len(list(questions)),
                "stop_reasoning": None, "warnings": [], "search_consequence_summary": None, "limitations": [],
                "final_search_intent": {"hard_requirements": [], "strong_signals": [], "preferred_differentiators": [],
                                        "natural_language_search_query": None, "exclusions": [], "evidence": {}}}
    return {"raw_input": raw_input, "role_understanding": role_understanding,
            "decision": decision, "status": "needs_clarification"}


# --- the held pool (persisted off-wire for the adaptive loop) ----------------

def _pool_entry(record, *, judged: bool, shown: bool, rank: int,
                fit: Optional[str] = None, score: Optional[float] = None) -> Dict[str, Any]:
    raw = record.raw if isinstance(record.raw, dict) else {}
    return {
        "candidate_id": record.candidate_id or None, "name": record.name, "title": record.title,
        "company": record.company, "location": record.location, "profile_url": record.profile_url,
        "provider_score": record.provider_score,
        "final_score": score if score is not None else record.final_score,
        "fit": fit, "judged": judged, "shown": shown, "rank": rank,
        "enriched": bool(record.enriched),
        "judgments": list(record.judgments) if record.judgments else None,
        "matched_queries": list(record.matched_queries),
        # Raw provider payload kept so a reserve member can be judged / have its
        # evidence rebuilt later WITHOUT a fresh paid pull (the loop's foundation).
        "raw": raw,
    }


def pool_snapshot(ranking, *, surface_all: bool = False) -> Dict[str, Any]:
    """The full in-scope pool with per-candidate state. `judged` rows carry the
    Judge's verdicts + the prose fit (shown or not); `reserve` is the baseline-
    ranked, un-judged remainder, promoted on demand by a later phase. Persisted on
    the search record (internal, admin-only) — NOT emitted in the frontend
    SearchResponse; the caller lifts it out before storing the response snapshot."""
    show_n = len(ranking.ranked) if surface_all else len(ranking.shown)
    judged = [
        _pool_entry(rc.record, judged=rc.record.judgments is not None,
                    shown=i < show_n, rank=i, fit=rc.fit, score=rc.score)
        for i, rc in enumerate(ranking.ranked)
    ]
    reserve = [
        _pool_entry(rec, judged=False, shown=False, rank=len(judged) + i)
        for i, rec in enumerate(getattr(ranking, "reserve", ()) or ())
    ]
    return {
        "judged": judged, "reserve": reserve,
        "counts": {"judged": len(judged), "reserve": len(reserve),
                   "shown": show_n, "total": len(judged) + len(reserve)},
    }


# --- engine -> SearchResponse ------------------------------------------------

def _search_intent_dataclass(model: RoleModel):
    """A legacy SearchIntent dataclass built from the RoleModel — what the keeper
    candidate_evidence_builder needs to derive role-alignment (title relevance,
    experience floor, level fit, matched signals)."""
    from backend.models.search_intent import (
        CompanyPreferences, Experience, Location as _Loc, Role, SearchIntent, Skills, Titles,
    )
    loc = model.location
    cores = [r.text for r in model.tier("core")]
    supporting = [r.text for r in model.tier("supporting")]
    diffs = [r.text for r in model.tier("differentiator")]
    return SearchIntent(
        role=Role(title=model.identity, posted_title=model.posted_title,
                  posted_title_source=model.posted_title_source, employment_type=model.employment_type),
        location=_Loc(countries=list(loc.countries), states=list(loc.states), cities=list(loc.cities),
                      radius_miles=loc.radius_miles, radius_place=loc.radius_place, work_mode=loc.work_mode),
        experience=Experience(minimum_years=model.seniority.min_years, maximum_years=model.seniority.max_years),
        titles=Titles(exclude_titles=list(model.exclude_titles)),
        skills=Skills(required_skills=cores, preferred_skills=supporting),
        company_preferences=CompanyPreferences(exclude_current_companies=list(model.companies.exclude_current),
                                               preferred_companies_ever=list(model.companies.prefer_ever)),
        natural_language_search_query=build_nl_query(model),
        core_signals=cores, supporting_signals=supporting, differentiator_signals=diffs,
    )


def to_running_search_response(provider: str, search_id: str, *, pulled: int = 0, kept: int = 0,
                               admitted: int = 0, processed: int = 0) -> Dict[str, Any]:
    """A mid-flight SearchResponse the background search saves as it works, so each
    GET /search/{id} poll shows real movement ("Reading profiles: N of M") instead
    of a frozen running state until the whole thing finishes."""
    return {
        "provider": provider, "search_id": search_id, "candidate_count": 0,
        "candidates": [], "explanations": [], "evidence": [], "debug": None,
        "warnings": [], "status": "running", "candidate_states": {},
        "diagnostics": {"pulled": pulled, "kept": kept, "admitted": admitted, "judged": processed},
        "progress": {"admitted": admitted, "surfaced": max(admitted - processed, 0),
                     "building_context": 0, "review_ready": processed},
    }


def shape_candidate(model: RoleModel, intent, record, score: float, fit: str):
    """Shape one CandidateRecord into the (candidate, explanation, evidence) triple
    the frontend expects — the SINGLE per-candidate shaping, reused by the initial
    search response AND by the pool-first reveal so a brought-forward profile is
    built identically to one shown on the first view. An evidence build never sinks
    the card — a bad build falls back to {}."""
    from dataclasses import asdict
    from backend.models.candidate import Candidate
    from backend.services.candidate_evidence_builder import build_candidate_evidence

    raw = record.raw if isinstance(record.raw, dict) else {}
    # Surface the Judge's verified judgments so the evidence builder rebuilds the
    # green dots AND the requirement ledger from them (it reads this exact key).
    if record.judgments:
        raw["__requirement_judgments"] = list(record.judgments)
    built_evidence: Dict[str, Any] = {}
    years = None
    try:
        cand = Candidate(candidate_id=record.candidate_id or None, name=record.name, title=record.title,
                         company=record.company, location=record.location, provider_score=record.provider_score,
                         final_score=score, profile_url=record.profile_url, source="crustdata", raw_data=raw)
        # Pass the Harvest enrichment the admitted candidate was read with, so the
        # DISPLAYED record carries the full profile (About, role descriptions, skills,
        # certifications) — not just CrustData. The Judge already reads this; the card
        # used to drop it, leaving a thin record beside a rich LinkedIn profile. Pop it
        # off raw: it is a HarvestEvidence object (not JSON-serializable), so it must not
        # ride along in raw_data. A reserve reveal (no enrichment) stays CrustData-only.
        harvest_obj = raw.pop("_harvest_evidence", None)
        built = build_candidate_evidence(cand, intent, harvest_evidence=harvest_obj if getattr(harvest_obj, "success", False) else None)
        built_evidence = asdict(built)
        years = getattr(built, "derived_experience_years", None)
    except Exception:
        built_evidence = {}
    # Deterministic attributes (company kind, seniority, recency, …) read straight
    # off the CrustData payload we already have — no LLM, no credits. Surfaced on
    # the card and used by the include/exclude filters.
    attributes: Dict[str, Any] = {}
    try:
        from backend.services.candidate_attributes import attributes_dict
        cand_country = ((raw.get("basic_profile") or {}).get("location") or {}).get("country") if isinstance(raw, dict) else None
        attributes = attributes_dict(raw, candidate_country=cand_country)
    except Exception:
        attributes = {}
    candidate = {
        "candidate_id": record.candidate_id or None, "name": record.name, "title": record.title,
        "company": record.company, "location": record.location, "provider_score": record.provider_score,
        "final_score": score, "profile_url": record.profile_url, "source": "crustdata",
        "experience_years": years, "years_of_experience": years, "summary": None,
        "ai_skills": None, "raw_data": raw, "attributes": attributes,
    }
    # "Why this candidate" leads with a grounded SUMMARY, not the line-by-line
    # "Evidence: a; b; c" dump (fit) — the per-requirement detail lives in the
    # ledger. fit is kept as strong_evidence only as the no-ledger fallback.
    explanation = {
        "relevance_tier": "direct", "why_this_candidate": evidence_summary(model, record),
        "strong_evidence": [fit] if fit else [], "potential_concerns": [],
        "what_we_dont_know": [], "matched_signals": [], "seniority_alignment": None,
        "provider_fit": None, "convergence": False, "matched_queries": list(record.matched_queries),
        "final_score": score, "review_first": [], "experience_floor": None, "level_fit": None,
    }
    return candidate, explanation, built_evidence


def _record_from_pool_entry(entry: Dict[str, Any]):
    """Rebuild a CandidateRecord from a persisted pool entry so the reveal path can
    shape it exactly like a first-view candidate — no new provider pull, no re-judge
    (the Judge's verdicts are stored on the entry)."""
    from recruiter.candidates import CandidateRecord
    return CandidateRecord(
        candidate_id=entry.get("candidate_id") or "",
        name=entry.get("name"), title=entry.get("title"), company=entry.get("company"),
        location=entry.get("location"), profile_url=entry.get("profile_url"),
        provider_score=entry.get("provider_score"),
        raw=entry.get("raw") if isinstance(entry.get("raw"), dict) else {},
        matched_queries=tuple(entry.get("matched_queries") or ()),
        judgments=tuple(entry["judgments"]) if entry.get("judgments") else None,
        final_score=entry.get("final_score"),
    )


def reveal_into_record(record: Dict[str, Any], model: RoleModel) -> bool:
    """Pool-first reveal: bring the next already-read (judged) profile forward from
    the held pool into the response — no new search, no credits. Returns True if one
    was revealed, False when the free pool is exhausted (reach-wider is a separate,
    credit-gated step). Mutates `record` in place; the caller persists it."""
    diag = record.get("internal_diagnostics") or {}
    pool = diag.get("pool") or {}
    judged = pool.get("judged") or []
    response = record.get("response")
    if not isinstance(response, dict) or not judged:
        return False

    shown_ids = {c.get("candidate_id") for c in (response.get("candidates") or [])}
    # Held = read-in-depth profiles not surfaced on the first view and not already
    # brought forward. They keep the pool's final-score order (best first).
    held = [e for e in judged if not e.get("shown") and e.get("candidate_id") not in shown_ids]
    if not held:
        return False

    entry = held[0]
    intent = _search_intent_dataclass(model)
    rec = _record_from_pool_entry(entry)
    candidate, explanation, built_evidence = shape_candidate(
        model, intent, rec, entry.get("final_score") or 0.0, entry.get("fit") or "")

    response.setdefault("candidates", []).append(candidate)
    response.setdefault("explanations", []).append(explanation)
    response.setdefault("evidence", []).append(built_evidence)
    response["candidate_count"] = len(response["candidates"])
    response.setdefault("candidate_states", {})[entry.get("candidate_id")] = "review_ready"
    response["reserve_available"] = max(len(held) - 1, 0)
    entry["shown"] = True  # so the same profile is never revealed twice

    record["response"] = response
    record["internal_diagnostics"] = diag
    return True


def _title_excluded(record, exclude_titles) -> bool:
    import re
    if not exclude_titles:
        return False
    raw = record.raw if isinstance(record.raw, dict) else {}
    headline = (raw.get("basic_profile") or {}).get("headline") or ""
    hay = f"{record.title or ''} {headline}".lower()
    return any(re.search(r"\b" + re.escape(t.lower()) + r"\b", hay) for t in exclude_titles if t)


def _candidate_companies(record) -> set:
    names = set()
    raw = record.raw if isinstance(record.raw, dict) else {}
    exp = raw.get("experience") if isinstance(raw.get("experience"), dict) else {}
    details = exp.get("employment_details") or {} if isinstance(exp, dict) else {}
    for bucket in ("current", "past"):
        for role in details.get(bucket) or []:
            if isinstance(role, dict):
                name = role.get("employer_name") or role.get("company") or role.get("company_name")
                if name:
                    names.add(str(name).lower())
    return names


def _company_excluded(record, exclude_current, exclude_ever) -> bool:
    current = (record.company or "").lower()
    if exclude_current and any(x.lower() in current for x in exclude_current if x and current):
        return True
    if exclude_ever:
        ever = _candidate_companies(record) | ({current} if current else set())
        if any(any(x.lower() in company for company in ever) for x in exclude_ever if x):
            return True
    return False


def refine_pool_into_record(record: Dict[str, Any], model: RoleModel, deltas: Dict[str, Any],
                            show: int = 5) -> Dict[str, Any]:
    """Pool-first refine: apply structured deltas to the RoleModel, then RE-CHECK the
    already-read (judged) pool against the refined non-negotiables and re-rank what
    survives — free, instant, no new search. Rewrites the shown set to the refined
    top; the rest stays held. When nothing in the read pool matches, the current view
    is left untouched and `exhausted` is returned so the caller can offer reach-wider
    (a separate, credit-gated step). Mutates `record`."""
    from recruiter.agents.calibration.refine import refine_model
    from recruiter.agents.ranking.experience import below_floor
    from recruiter.agents.ranking.score import final_score

    refined = refine_model(model, deltas)
    diag = record.get("internal_diagnostics") or {}
    pool = diag.get("pool") or {}
    judged = pool.get("judged") or []
    response = record.get("response")
    if not isinstance(response, dict) or not judged:
        return {"refined": False, "matched": 0, "dropped": 0, "shown": 0, "exhausted": True}

    min_years = refined.seniority.min_years
    kept = []
    dropped = 0
    for entry in judged:
        rec = _record_from_pool_entry(entry)
        if (below_floor(rec, min_years)
                or _title_excluded(rec, refined.exclude_titles)
                or _company_excluded(rec, refined.companies.exclude_current, refined.companies.exclude_ever)):
            dropped += 1
            continue
        kept.append((final_score(refined, rec), entry, rec))
    kept.sort(key=lambda t: (-t[0], (t[2].name or "")))

    outcome = {"refined": True, "matched": len(kept), "dropped": dropped,
               "shown": min(len(kept), show), "exhausted": len(kept) == 0}
    if not kept:
        # Nobody in the read pool matches the tighter brief — keep the current view
        # and let the caller offer a (credit-gated) wider search.
        response["refine_outcome"] = outcome
        record["response"] = response
        return outcome

    intent = _search_intent_dataclass(refined)
    candidates, explanations, evidence = [], [], []
    for score, entry, rec in kept[:show]:
        candidate, explanation, built = shape_candidate(refined, intent, rec, score, entry.get("fit") or "")
        candidates.append(candidate)
        explanations.append(explanation)
        evidence.append(built)
        entry["shown"] = True
    for _, entry, _ in kept[show:]:
        entry["shown"] = False

    response["candidates"] = candidates
    response["explanations"] = explanations
    response["evidence"] = evidence
    response["candidate_count"] = len(candidates)
    response["candidate_states"] = {c["candidate_id"]: "review_ready" for c in candidates if c.get("candidate_id")}
    response["reserve_available"] = max(len(kept) - len(candidates), 0)
    response["refine_outcome"] = outcome
    record["response"] = response
    record["internal_diagnostics"] = diag
    return outcome


def to_search_response(provider: str, search_id: str, model: RoleModel,
                       search_result, ranking, *, surface_all: bool = False) -> Dict[str, Any]:
    """Map the ranked result into the frontend SearchResponse: candidates +
    evidence-based explanations + rich CandidateEvidence (career/education/contact/
    role-alignment, via the keeper candidate_evidence_builder) + diagnostics."""
    intent = _search_intent_dataclass(model)
    candidates: List[Dict[str, Any]] = []
    explanations: List[Dict[str, Any]] = []
    evidence: List[Dict[str, Any]] = []
    rows = ranking.ranked if surface_all else ranking.shown
    for rc in rows:
        candidate, explanation, built_evidence = shape_candidate(model, intent, rc.record, rc.score, rc.fit)
        candidates.append(candidate)
        explanations.append(explanation)
        evidence.append(built_evidence)
    diagnostics = {
        "pulled": search_result.pulled, "kept": len(search_result.candidates),
        "geo_dropped": search_result.geo_dropped, "excluded_dropped": search_result.excluded_dropped,
        "est_credits": search_result.est_credits, "admitted": ranking.admitted,
        "judged": ranking.judged, "judge_failures": ranking.judge_failures,
        "experience_excluded": ranking.experience_excluded,
        "total_available": search_result.total_available,
        "next_cursor": search_result.next_cursor,
        "credits_used": search_result.credits_used,
    }
    return {
        "provider": provider, "search_id": search_id, "candidate_count": len(candidates),
        "candidates": candidates, "explanations": explanations, "evidence": evidence,
        "diagnostics": diagnostics, "warnings": [], "status": "complete",
        # Ask the recruiter why on Maybe/Reject, and reveal the next already-read
        # candidate for free when one is rejected. reserve_available = the judged-
        # but-not-shown profiles we can bring forward with no new search / no credits.
        "feedback_capture": True,
        "reserve_available": 0 if surface_all else max(ranking.admitted - len(ranking.shown), 0),
        # Lifted out of the frontend response by the caller (api.py) and persisted
        # into the record's internal_diagnostics — the held pool for the loop.
        "pool": pool_snapshot(ranking, surface_all=surface_all),
    }
