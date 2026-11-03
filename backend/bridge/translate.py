"""Translate new-engine objects into the dayzero.partners frontend contract.

The frontend shapes (SearchIntent, IntakeResult/RoleUnderstanding, SearchResponse)
were built for the legacy "brain", so they carry fields the new engine deliberately
dropped: candidate_archetype, role_interpretation, seniority_scope, leadership_type,
and consequence-framed questions. We map everything the engine DOES produce and leave
those legacy-only fields empty — they are the Phase-2 frontend trim targets, marked
`# brain-only -> trim` below. No intelligence is re-created here; this is pure shaping.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from recruiter.agents.briefing.query import build_nl_query
from recruiter.role_model import Location, RoleModel


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
            "It's enforced in the search — remove it from the core requirements below if "
            "the role is broader than that.")


def _issue(q, insight_text: Optional[str] = None) -> Dict[str, Any]:
    return {
        "issue": q.id, "decision": "ask" if q.id in _BLOCKING_ISSUES else "tell",
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
        "limitations": list(model.limitations),
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


def to_search_response(provider: str, search_id: str, model: RoleModel,
                       search_result, ranking) -> Dict[str, Any]:
    """Map the ranked result into the frontend SearchResponse: candidates +
    evidence-based explanations + rich CandidateEvidence (career/education/contact/
    role-alignment, via the keeper candidate_evidence_builder) + diagnostics. An
    evidence build never sinks the search — a bad card falls back to {}."""
    from dataclasses import asdict
    from backend.models.candidate import Candidate
    from backend.services.candidate_evidence_builder import build_candidate_evidence

    intent = _search_intent_dataclass(model)
    candidates: List[Dict[str, Any]] = []
    explanations: List[Dict[str, Any]] = []
    evidence: List[Dict[str, Any]] = []
    for rc in ranking.shown:
        r = rc.record
        raw = r.raw if isinstance(r.raw, dict) else {}
        # Build the rich evidence first so we can surface its derived years-of-
        # experience on the candidate card (the keeper computes it from the dated
        # career history; without this the card showed no experience at all).
        built_evidence: Dict[str, Any] = {}
        years = None
        try:
            cand = Candidate(candidate_id=r.candidate_id or None, name=r.name, title=r.title,
                             company=r.company, location=r.location, provider_score=r.provider_score,
                             final_score=rc.score, profile_url=r.profile_url, source="crustdata", raw_data=raw)
            built = build_candidate_evidence(cand, intent)
            built_evidence = asdict(built)
            years = getattr(built, "derived_experience_years", None)
        except Exception:
            built_evidence = {}
        candidates.append({
            "candidate_id": r.candidate_id or None, "name": r.name, "title": r.title,
            "company": r.company, "location": r.location, "provider_score": r.provider_score,
            "final_score": rc.score, "profile_url": r.profile_url, "source": "crustdata",
            "experience_years": years, "years_of_experience": years, "summary": None,
            "ai_skills": None, "raw_data": raw,
        })
        explanations.append({
            "relevance_tier": "direct", "why_this_candidate": rc.fit,
            "strong_evidence": [rc.fit] if rc.fit else [], "potential_concerns": [],
            "what_we_dont_know": [], "matched_signals": [], "seniority_alignment": None,
            "provider_fit": None, "convergence": False, "matched_queries": list(r.matched_queries),
            "final_score": rc.score, "review_first": [], "experience_floor": None, "level_fit": None,
        })
        evidence.append(built_evidence)
    diagnostics = {
        "pulled": search_result.pulled, "kept": len(search_result.candidates),
        "geo_dropped": search_result.geo_dropped, "excluded_dropped": search_result.excluded_dropped,
        "est_credits": search_result.est_credits, "admitted": ranking.admitted,
        "judged": ranking.judged, "judge_failures": ranking.judge_failures,
        "experience_excluded": ranking.experience_excluded,
    }
    return {
        "provider": provider, "search_id": search_id, "candidate_count": len(candidates),
        "candidates": candidates, "explanations": explanations, "evidence": evidence,
        "diagnostics": diagnostics, "warnings": [], "status": "complete",
    }
