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


def _issue(q) -> Dict[str, Any]:
    return {
        "issue": q.id, "decision": "ask", "id": q.id, "reasoning": None,
        "question": q.prompt, "options": [{"value": o, "label": o} for o in q.options],
        "consequence_if_answer_a": None, "consequence_if_answer_b": None,  # brain-only -> trim
        "insight_text": None, "injected_by_backstop": False, "backstop_category": None,
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
        "core_capabilities": [_cap_item(r) for r in model.tier("core")],
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
    decision = {
        "issues": [_issue(q) for q in questions],
        "recommended_ask_count": len(list(questions)),
        "stop_reasoning": None,
        "warnings": [],
        "search_consequence_summary": None,   # brain-only -> trim
        "limitations": list(model.limitations),
        "final_search_intent": {
            "hard_requirements": [r.text for r in model.hard_requirements],
            "strong_signals": [r.text for r in model.tier("supporting")],
            "preferred_differentiators": [r.text for r in model.tier("differentiator")],
            "natural_language_search_query": build_nl_query(model),
            "exclusions": list(model.exclude_titles),
            "evidence": {r.text: r.provenance.evidence for r in model.requirements if r.provenance.evidence},
        },
    }
    return {"raw_input": raw_input, "role_understanding": role_understanding,
            "decision": decision, "status": status}


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

def to_search_response(provider: str, search_id: str, model: RoleModel,
                       search_result, ranking) -> Dict[str, Any]:
    """Map the ranked result into the frontend SearchResponse. Minimal-but-valid:
    candidates + evidence-based explanations + diagnostics. `evidence` (the rich
    CandidateEvidence) is left empty for now — reusing the keeper
    candidate_evidence_builder (it wants a legacy Candidate + SearchIntent) is a
    follow-up; every rich SearchResponse field is optional, so the record renders."""
    candidates: List[Dict[str, Any]] = []
    explanations: List[Dict[str, Any]] = []
    for rc in ranking.shown:
        r = rc.record
        candidates.append({
            "candidate_id": r.candidate_id or None, "name": r.name, "title": r.title,
            "company": r.company, "location": r.location, "provider_score": r.provider_score,
            "final_score": rc.score, "profile_url": r.profile_url, "source": "crustdata",
            "experience_years": None, "years_of_experience": None, "summary": None,
            "ai_skills": None, "raw_data": r.raw if isinstance(r.raw, dict) else {},
        })
        explanations.append({
            "relevance_tier": "direct", "why_this_candidate": rc.fit,
            "strong_evidence": [rc.fit] if rc.fit else [], "potential_concerns": [],
            "what_we_dont_know": [], "matched_signals": [], "seniority_alignment": None,
            "provider_fit": None, "convergence": False, "matched_queries": list(r.matched_queries),
            "final_score": rc.score, "review_first": [], "experience_floor": None, "level_fit": None,
        })
    diagnostics = {
        "pulled": search_result.pulled, "kept": len(search_result.candidates),
        "geo_dropped": search_result.geo_dropped, "excluded_dropped": search_result.excluded_dropped,
        "est_credits": search_result.est_credits, "admitted": ranking.admitted,
        "judged": ranking.judged, "judge_failures": ranking.judge_failures,
        "experience_excluded": ranking.experience_excluded,
    }
    return {
        "provider": provider, "search_id": search_id, "candidate_count": len(candidates),
        "candidates": candidates, "explanations": explanations, "evidence": [],
        "diagnostics": diagnostics, "warnings": [], "status": "complete",
    }
