"""Bridge translation — engine objects -> dayzero.partners frontend contract."""

import json

from backend.bridge.translate import (
    pool_snapshot,
    refine_pool_into_record,
    reveal_into_record,
    to_intake_result,
    to_search_intent,
    to_search_response,
)
from recruiter.agents.intake.model import Question
from recruiter.agents.ranking.model import RankedCandidate, RankingResult
from recruiter.agents.search.model import SearchResult
from recruiter.candidates import CandidateRecord
from recruiter.role_model import (
    ARCHITECT,
    JD,
    CapabilityGroup,
    CompanyRules,
    Location,
    Provenance,
    Requirement,
    RoleModel,
    Seniority,
)


def _model() -> RoleModel:
    return RoleModel(
        identity="eDiscovery Operations Analyst",
        seniority=Seniority(8, 12, Provenance(JD, "8-12 yrs")),
        role_level=ARCHITECT,
        location=Location(countries=("India",), states=("Karnataka",), cities=("Bengaluru", "Pune"),
                          work_mode="hybrid"),
        requirements=(
            Requirement("eDiscovery operations", "core", Provenance(JD, "EDRM lifecycle"), hard=True),
            Requirement("Windows/MS Office", "supporting", Provenance(JD)),
        ),
        capability_groups=(CapabilityGroup("eDiscovery", ("Relativity", "Nuix", "EDRM"), "eDiscovery", "x"),),
        companies=CompanyRules(exclude_current=("Epiq",), prefer_ever=("KLDiscovery",)),
        exclude_titles=("VP", "Director"),
        industries=("Legal Services",),
        posted_title="Operations Analyst – eDiscovery",
        posted_title_source="jd",
        employment_type="full-time",
        hiring_company="Epiq",
        limitations=("work mode not filterable",),
    )


def test_search_intent_maps_core_fields_and_is_json_safe():
    si = to_search_intent(_model())
    assert si["role"]["title"] == "eDiscovery Operations Analyst"
    assert si["location"]["cities"] == ["Bengaluru", "Pune"] and si["location"]["work_mode"] == "hybrid"
    assert si["experience"] == {"minimum_years": 8, "maximum_years": 12, "confidence_score": None}
    assert si["titles"]["exclude_titles"] == ["VP", "Director"]
    assert si["company_preferences"]["exclude_current_companies"] == ["Epiq"]
    assert si["company_preferences"]["preferred_companies_ever"] == ["KLDiscovery"]
    assert si["must_have_keyword_groups"] == [["Relativity", "Nuix", "EDRM"]]
    assert "eDiscovery" in si["natural_language_search_query"]
    json.dumps(si)  # must serialize


def test_intake_result_maps_brief_and_marks_status():
    qs = (Question(id="capability", prompt="Require eDiscovery?", kind="capability_confirm",
                   options=("keep", "remove")),)
    result = to_intake_result("JD text", _model(), qs, status="ready")
    ru = result["role_understanding"]
    assert ru["primary_candidate_identity"]["value"] == "eDiscovery Operations Analyst"
    assert ru["posted_title"] == "Operations Analyst – eDiscovery"
    # the role-defining capability leads the core requirements (was empty before)
    assert ru["core_capabilities"][0]["value"] == "eDiscovery (Relativity, Nuix, EDRM)"
    assert any(c["value"] == "eDiscovery operations" for c in ru["core_capabilities"])
    assert ru["technologies_mentioned"] == [{"category": "eDiscovery", "items": ["Relativity", "Nuix", "EDRM"]}]
    assert ru["explicit_constraints"]["experience_minimum_years"] == 8
    assert ru["explicit_constraints"]["locations"] == [
        {"city": "Bengaluru", "state": "Karnataka", "country": "India"},
        {"city": "Pune", "state": "Karnataka", "country": "India"},
    ]
    # brain-only fields present but empty (Phase-2 trim targets)
    assert ru["role_interpretation"] == {"value": None, "evidence": None, "source": None}
    # capability leads the hard requirements, then the recruiter-marked dealbreaker
    assert result["decision"]["final_search_intent"]["hard_requirements"] == ["eDiscovery", "eDiscovery operations"]
    # the capability is an OPTIONAL, interactive refinement ("offer"): the recruiter
    # can keep or remove it (A2), but it never blocks Search, and it still carries
    # the stated-assumption insight note so the brief reads clearly straight away.
    cap = result["decision"]["issues"][0]
    assert cap["question"] == "Require eDiscovery?"
    assert cap["decision"] == "offer"
    assert cap["insight_text"] and "eDiscovery" in cap["insight_text"]
    assert result["status"] == "ready"
    json.dumps(result)  # must serialize


def test_dropped_negative_nudge_is_high_precision():
    from dataclasses import replace
    from recruiter.role_model import CompanyRules
    base = RoleModel(identity="Backend Engineer", seniority=Seniority(5, None, Provenance(JD)),
                     role_level=None, location=Location(countries=("India",)))
    has = lambda r: any("free-text exclusions" in lim for lim in r["decision"]["limitations"])
    # Exclusion phrasing + nothing excluded -> nudge.
    assert has(to_intake_result("We don't want anyone from Google.", base, (), status="ready"))
    assert has(to_intake_result("Please, not a manager for this role.", base, (), status="ready"))
    # No exclusion phrasing -> no nudge (no false positive).
    assert not has(to_intake_result("Backend engineer, Postgres, Kafka.", base, (), status="ready"))
    # Default exec TITLE exclusions must NOT suppress the nudge (CoWork round 2 bug) —
    # only a recruiter-set COMPANY exclusion means nothing was dropped.
    titled = replace(base, exclude_titles=("Manager", "Director"))
    assert has(to_intake_result("We don't want anyone from Google.", titled, (), status="ready"))
    # The AUTOMATIC hiring-company exclusion ("current: Acme") must NOT suppress it
    # (CoWork round 3 — it is always present, so it hid the nudge every time).
    auto = replace(base, hiring_company="Acme", companies=CompanyRules(exclude_current=("Acme",)))
    assert has(to_intake_result("We don't want anyone from Google.", auto, (), status="ready"))
    # A real OTHER company exclusion -> no nudge.
    excl = replace(base, companies=CompanyRules(exclude_current=("Google",)))
    assert not has(to_intake_result("We don't want anyone from Google.", excl, (), status="ready"))


def test_core_requirements_show_even_without_a_capability_group():
    # A role where the reader found core requirements but no capability was inferred
    # (e.g. a Data Engineer). The brief must still show those cores — not "No core
    # requirements" while the summary counts them.
    model = RoleModel(
        identity="Senior Data Engineer",
        seniority=Seniority(7, 12, Provenance(JD)),
        role_level=ARCHITECT,
        location=Location(countries=("India",)),
        requirements=(
            Requirement("Spark", "core", Provenance(JD)),
            Requirement("Airflow", "core", Provenance(JD)),
            Requirement("Python/SQL", "core", Provenance(JD)),
            Requirement("dbt", "supporting", Provenance(JD)),
        ),
    )
    result = to_intake_result("JD", model, (), status="ready")
    core = result["decision"]["final_search_intent"]["hard_requirements"]
    assert core == ["Spark", "Airflow", "Python/SQL"]            # the reader's cores, shown
    assert result["decision"]["final_search_intent"]["strong_signals"] == ["dbt"]


def test_search_response_maps_candidates_and_diagnostics():
    rec = CandidateRecord("c1", name="Asha", title="eDiscovery Analyst", company="KLDiscovery",
                          location="Pune, India", profile_url="http://x", provider_score=0.8,
                          matched_queries=("natural_language",), raw={"basic_profile": {"headline": "Relativity"}})
    ranking = RankingResult(ranked=(), shown=(RankedCandidate(rec, 0.91, "Strong Relativity match."),),
                            admitted=25, judged=5, judge_failures=0, experience_excluded=2)
    search = SearchResult(candidates=(rec,), pulled=50, geo_dropped=1, est_credits=1.5, excluded_dropped=3)
    resp = to_search_response("crustdata", "s-1", _model(), search, ranking)
    assert resp["candidate_count"] == 1 and resp["search_id"] == "s-1"
    c = resp["candidates"][0]
    assert c["name"] == "Asha" and c["final_score"] == 0.91 and c["raw_data"]["basic_profile"]["headline"] == "Relativity"
    # "Why this candidate" is now a grounded summary, not the line-by-line fit. This
    # record carries no judgments, so it honestly says the profile was not read in depth.
    assert "not read in depth" in resp["explanations"][0]["why_this_candidate"]
    assert resp["diagnostics"]["pulled"] == 50 and resp["diagnostics"]["excluded_dropped"] == 3
    assert resp["diagnostics"]["experience_excluded"] == 2 and resp["status"] == "complete"
    # rich evidence now built via the keeper candidate_evidence_builder
    ev = resp["evidence"][0]
    assert ev["current_company"] == "KLDiscovery" and "Relativity" in ev["headline"]
    assert "past_roles" in ev and "education" in ev and "role_alignment" in ev
    json.dumps(resp)


def test_harvest_enrichment_reaches_the_displayed_record():
    # The admitted candidate is read with Harvest, but the DISPLAYED record used to be
    # rebuilt from CrustData only — About, role descriptions and skills were dropped,
    # leaving a thin card beside a rich LinkedIn profile. The enrichment must flow into
    # the shown evidence.
    from backend.models.candidate_evidence import HarvestEvidence

    harvest = HarvestEvidence(
        success=True,
        raw={"element": {
            "about": "I build and govern the enterprise automation platform and the agentic AI framework.",
            "experience": [{"position": "AI Platform Engineer", "companyName": "Teranet",
                            "description": "Owned orchestration, model routing, and evaluation pipelines."}],
            "topSkills": ["Agentic AI", "Platform Engineering", "LLM"],
        }},
    )
    rec = CandidateRecord("c1", name="Hisham", title="AI Platform Engineer", company="Teranet",
                          profile_url="http://x", provider_score=0.8,
                          raw={"basic_profile": {"headline": "AI Platform Engineer"}, "_harvest_evidence": harvest})
    ranking = RankingResult(ranked=(), shown=(RankedCandidate(rec, 0.9, "Strong match."),),
                            admitted=8, judged=5, judge_failures=0)
    search = SearchResult(candidates=(rec,), pulled=50, geo_dropped=0, est_credits=1.5, excluded_dropped=0)
    resp = to_search_response("crustdata", "s-h", _model(), search, ranking)
    ev = resp["evidence"][0]
    assert "enterprise automation platform" in (ev.get("harvest_about") or "")
    assert any("orchestration" in (c.get("description") or "") for c in ev.get("career") or [])
    assert "Agentic AI" in (ev.get("harvest_skills") or [])
    json.dumps(resp)


def test_judge_judgments_flow_into_evidence_for_the_dots_and_ledger():
    # The Judge's verified judgments must reach the frontend evidence, or the green
    # alignment dots and the requirement ledger come back empty (the regression we
    # are fixing). They ride through raw['__requirement_judgments'].
    judgment = {
        "tier": "core", "signal_text": "Relativity", "verdict": "met",
        "quote": "Led Relativity review workflows", "term": "Relativity",
        "source": "headline", "evidence_detail": "", "strength": "strong",
    }
    rec = CandidateRecord("c1", name="Asha", title="eDiscovery Analyst", company="KLDiscovery",
                          profile_url="http://x", provider_score=0.8,
                          raw={"basic_profile": {"headline": "Led Relativity review workflows"}},
                          judgments=(judgment,))
    ranking = RankingResult(ranked=(), shown=(RankedCandidate(rec, 0.91, "Strong match."),),
                            admitted=25, judged=5, judge_failures=0)
    search = SearchResult(candidates=(rec,), pulled=50, geo_dropped=0, est_credits=1.5, excluded_dropped=0)
    resp = to_search_response("crustdata", "s-2", _model(), search, ranking)
    rows = resp["evidence"][0]["requirement_judgments"]
    assert rows and any(r["signal_text"] == "Relativity" and r["verdict"] == "met" for r in rows)
    json.dumps(resp)


def _judged_rc(cid, headline, score):
    rec = CandidateRecord(cid, name=cid, title="eDiscovery Analyst", profile_url="http://x",
                          provider_score=0.5, raw={"basic_profile": {"headline": headline}},
                          judgments=({"tier": "core", "signal_text": "Relativity", "verdict": "met",
                                      "quote": headline},))
    return RankedCandidate(rec, score, f"Match: {headline}")


def test_pool_snapshot_holds_judged_and_reserve_state():
    shown = _judged_rc("shown", "Relativity lead", 0.9)
    held = _judged_rc("held", "Relativity analyst", 0.6)      # judged but not shown
    reserve_rec = CandidateRecord("reserve", name="reserve", title="Analyst",
                                  raw={"basic_profile": {"headline": "generalist"}})
    ranking = RankingResult(ranked=(shown, held), shown=(shown,), admitted=2, judged=2,
                            judge_failures=0, reserve=(reserve_rec,))
    pool = pool_snapshot(ranking)
    assert pool["counts"] == {"judged": 2, "reserve": 1, "shown": 1, "total": 3}
    # shown flag is set only on the surfaced row; both judged rows carry verdicts + fit
    assert [e["shown"] for e in pool["judged"]] == [True, False]
    assert all(e["judged"] and e["judgments"] and e["fit"] for e in pool["judged"])
    # reserve is un-judged but keeps its raw payload for on-demand judging later
    r = pool["reserve"][0]
    assert r["judged"] is False and r["judgments"] is None
    assert r["raw"]["basic_profile"]["headline"] == "generalist" and r["rank"] == 2
    json.dumps(pool)


def test_search_response_carries_the_pool_for_the_caller_to_lift_off():
    rec = CandidateRecord("c1", name="Asha", title="eDiscovery Analyst",
                          raw={"basic_profile": {"headline": "Relativity"}})
    reserve_rec = CandidateRecord("c2", name="Bob", title="Analyst", raw={})
    ranking = RankingResult(ranked=(RankedCandidate(rec, 0.9, "ok"),), shown=(RankedCandidate(rec, 0.9, "ok"),),
                            admitted=1, judged=1, judge_failures=0, reserve=(reserve_rec,))
    search = SearchResult(candidates=(rec,), pulled=50, geo_dropped=0, est_credits=1.5, excluded_dropped=0)
    resp = to_search_response("crustdata", "s-3", _model(), search, ranking)
    assert resp["pool"]["counts"]["total"] == 2        # 1 judged + 1 reserve
    assert len(resp["candidates"]) == 1                 # but only the shown 5 go on the card list
    assert resp["feedback_capture"] is True and resp["reserve_available"] == 0
    json.dumps(resp)


def test_reveal_brings_the_next_read_profile_forward_then_runs_dry():
    model = _model()
    held = {
        "candidate_id": "held1", "name": "Ravi", "title": "eDiscovery Analyst",
        "company": "KLDiscovery", "location": "Pune, India", "profile_url": "http://y",
        "provider_score": 0.6, "final_score": 0.55, "fit": "Evidence: eDiscovery operations",
        "judged": True, "shown": False, "rank": 1,
        "judgments": [{"tier": "core", "signal_text": "eDiscovery operations", "verdict": "met",
                       "quote": "Ran EDRM review workflows"}],
        "matched_queries": ["natural_language"], "raw": {"basic_profile": {"headline": "EDRM reviews"}},
    }
    record = {
        "response": {"candidates": [{"candidate_id": "shown1", "name": "Asha"}],
                     "explanations": [{}], "evidence": [{}], "candidate_count": 1,
                     "reserve_available": 1, "candidate_states": {}},
        "internal_diagnostics": {"pool": {"judged": [{"candidate_id": "shown1", "shown": True}, held], "reserve": []}},
    }
    # First reveal brings held1 forward — no new search.
    assert reveal_into_record(record, model) is True
    resp = record["response"]
    assert resp["candidate_count"] == 2
    assert [c["candidate_id"] for c in resp["candidates"]] == ["shown1", "held1"]
    assert resp["reserve_available"] == 0
    assert held["shown"] is True                                    # never revealed twice
    assert "eDiscovery operations" in resp["explanations"][1]["why_this_candidate"]  # grounded summary
    # Nothing left in the free pool → a second reveal is a no-op.
    assert reveal_into_record(record, model) is False
    json.dumps(record)


def test_reveal_is_a_noop_without_a_pool():
    record = {"response": {"candidates": [], "explanations": [], "evidence": []}, "internal_diagnostics": {}}
    assert reveal_into_record(record, _model()) is False


def _pool_entry(cid, company, title, headline="Relativity"):
    return {
        "candidate_id": cid, "name": cid, "title": title, "company": company,
        "location": "Pune, India", "profile_url": "http://x", "provider_score": 0.5,
        "final_score": 0.5, "fit": "Evidence: eDiscovery operations", "judged": True, "shown": False, "rank": 0,
        "judgments": [{"tier": "core", "signal_text": "eDiscovery operations", "verdict": "met", "quote": "Ran EDRM"}],
        "matched_queries": ["natural_language"], "raw": {"basic_profile": {"headline": headline}},
    }


def _record_with_pool(entries):
    return {
        "response": {"candidates": [], "explanations": [], "evidence": [], "candidate_count": 0,
                     "reserve_available": 0, "candidate_states": {}},
        "internal_diagnostics": {"pool": {"judged": list(entries), "reserve": []}},
    }


def test_refine_pool_drops_an_excluded_company_and_rewrites_the_shown_set():
    record = _record_with_pool([
        _pool_entry("keep1", "KLDiscovery", "eDiscovery Analyst"),
        _pool_entry("drop1", "Epiq", "eDiscovery Analyst"),
        _pool_entry("keep2", "Lighthouse", "eDiscovery Analyst"),
    ])
    outcome = refine_pool_into_record(record, _model(), {"exclude_companies_current": ["Epiq"]}, show=5)
    assert outcome == {"refined": True, "matched": 2, "dropped": 1, "shown": 2, "exhausted": False}
    ids = [c["candidate_id"] for c in record["response"]["candidates"]]
    assert "drop1" not in ids and set(ids) == {"keep1", "keep2"}
    assert record["response"]["candidate_count"] == 2
    json.dumps(record)


def test_refine_pool_excludes_by_title():
    record = _record_with_pool([
        _pool_entry("ic", "Acme", "eDiscovery Analyst"),
        _pool_entry("mgr", "Acme", "eDiscovery Manager"),
    ])
    outcome = refine_pool_into_record(record, _model(), {"exclude_titles": ["Manager"]}, show=5)
    assert outcome["matched"] == 1 and outcome["dropped"] == 1
    assert [c["candidate_id"] for c in record["response"]["candidates"]] == ["ic"]


def test_refine_pool_exhausted_keeps_current_view():
    record = _record_with_pool([_pool_entry("only", "Epiq", "eDiscovery Analyst")])
    record["response"]["candidates"] = [{"candidate_id": "shown_before"}]
    outcome = refine_pool_into_record(record, _model(), {"exclude_companies_current": ["Epiq"]}, show=5)
    assert outcome["matched"] == 0 and outcome["exhausted"] is True
    # Nobody matched → the current view is left untouched (no jarring empty screen).
    assert record["response"]["candidates"] == [{"candidate_id": "shown_before"}]
