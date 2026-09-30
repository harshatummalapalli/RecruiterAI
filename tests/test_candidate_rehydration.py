# Server-side presentation-field rehydration (career/photo_url/open_to_work)
# for evidence dicts persisted before those fields existed on
# CandidateEvidence. Pure-function tests over the rehydration helpers
# themselves; the GET /search/{id} wiring is covered separately in
# tests/test_api.py against a real, on-disk stored search.

from backend.services.candidate_evidence_builder import (
    rehydrate_presentation_fields,
    rehydrate_response_evidence,
)


def _old_shape_evidence(**overrides):
    """An evidence dict as it looked before `career`/`photo_url`/
    `open_to_work` existed — the exact shape confirmed on every real search
    stored before that release. role_alignment/requirement_judgments are
    included to prove they survive untouched."""
    base = {
        "candidate_id": "c1",
        "name": "Priya Rao",
        "current_title": "Senior Recruiter",
        "headline": "Talent leader",
        "profile_url": "https://www.linkedin.com/in/priya",
        "location": "Hyderabad, India",
        "current_company": "Epiq",
        "current_industries": ["Legal Services"],
        "past_roles": [
            {
                "title": "Recruiter",
                "company": "Acme",
                "industries": ["Technology"],
                "function": "Human Resources",
                "seniority": "Entry Level",
                "start_date": "2019-01-01T00:00:00",
                "end_date": "2021-01-01T00:00:00",
                "description": None,
            }
        ],
        "education": [],
        "harvest_skills": ["Sourcing"],
        "harvest_certifications": [],
        "harvest_about": "Recruiter with 6 years of experience.",
        "role_alignment": {"title_relevance": "direct", "title_relevance_basis": "Current title matches."},
        "requirement_judgments": [{"tier": "core", "signal_text": "Full-cycle recruiting", "verdict": "met"}],
        "uncertainty": [],
    }
    base.update(overrides)
    return base


def _harvest_raw(element, success=True):
    return {"raw": {"element": element}, "success": success, "cost": 0.0064, "error": None}


def test_backfills_career_photo_open_to_work_when_keys_absent():
    evidence = _old_shape_evidence()
    candidate_raw_data = {"basic_profile": {"profile_picture_permalink": "https://img.example/crustdata.jpg"}}
    harvest_raw = _harvest_raw(
        {
            "photo": "https://img.example/harvest.jpg",
            "openToWork": True,
            "experience": [
                {"position": "Senior Recruiter", "companyName": "Epiq", "startDate": {"text": "Apr 2025"}, "endDate": {"text": "Present"}, "description": "Leads technical hiring."}
            ],
        }
    )

    result = rehydrate_presentation_fields(evidence, candidate_raw_data, harvest_raw)

    assert result["photo_url"] == "https://img.example/crustdata.jpg"  # CrustData's own image wins over Harvest's
    assert result["open_to_work"] is True
    assert len(result["career"]) == 1
    assert result["career"][0]["title"] == "Senior Recruiter"
    assert result["career"][0]["description"] == "Leads technical hiring."
    # Nothing role-specific was touched.
    assert result["role_alignment"] == evidence["role_alignment"]
    assert result["requirement_judgments"] == evidence["requirement_judgments"]
    # Every pre-existing key is preserved unchanged.
    for key, value in evidence.items():
        if key not in ("career", "photo_url", "open_to_work"):
            assert result[key] == value


def test_is_a_strict_noop_when_all_three_keys_already_present():
    evidence = _old_shape_evidence(career=[{"title": "x"}], photo_url="already-there", open_to_work=None)
    result = rehydrate_presentation_fields(evidence, {"basic_profile": {"profile_picture_permalink": "should-be-ignored"}}, _harvest_raw({"photo": "also-ignored"}))
    assert result is evidence  # returned unchanged, not even copied


def test_repeated_rehydration_is_idempotent():
    evidence = _old_shape_evidence()
    candidate_raw_data = {"basic_profile": {"profile_picture_permalink": "https://img.example/crustdata.jpg"}}
    harvest_raw = _harvest_raw({"experience": [{"position": "Recruiter", "companyName": "Epiq"}]})

    once = rehydrate_presentation_fields(evidence, candidate_raw_data, harvest_raw)
    twice = rehydrate_presentation_fields(once, candidate_raw_data, harvest_raw)

    assert once == twice
    assert twice is once  # second call is the no-op path


def test_candidate_with_no_raw_harvest_falls_back_to_crustdata_only_career():
    evidence = _old_shape_evidence()
    candidate_raw_data = {"basic_profile": {}}  # no profile_picture_permalink either

    result = rehydrate_presentation_fields(evidence, candidate_raw_data, harvest_raw=None)

    assert result["photo_url"] is None
    assert result["open_to_work"] is None
    # Falls back to current_title/current_company (synthesized first, same as
    # _build_career's existing CrustData fallback) plus the past_roles
    # already on the evidence dict.
    assert [entry["title"] for entry in result["career"]] == ["Senior Recruiter", "Recruiter"]
    assert result["career"][1]["company"] == "Acme"


def test_failed_harvest_raw_is_treated_the_same_as_no_harvest():
    evidence = _old_shape_evidence()
    harvest_raw = _harvest_raw({"experience": [{"position": "Should not be used"}]}, success=False)

    result = rehydrate_presentation_fields(evidence, {}, harvest_raw)

    assert result["photo_url"] is None
    assert result["open_to_work"] is None
    # CrustData fallback (current + past_roles), never the failed Harvest payload.
    assert [entry["title"] for entry in result["career"]] == ["Senior Recruiter", "Recruiter"]


def test_malformed_optional_fields_do_not_crash_rehydration():
    evidence = _old_shape_evidence(
        past_roles="not-a-list",  # malformed
    )
    candidate_raw_data = {"basic_profile": "not-a-dict"}  # malformed
    harvest_raw = {"raw": "not-a-dict", "success": True}  # malformed

    result = rehydrate_presentation_fields(evidence, candidate_raw_data, harvest_raw)

    assert result["photo_url"] is None
    assert result["open_to_work"] is None
    # past_roles was malformed (not a list) so only the synthesized
    # current-role entry survives — no crash, no fabricated past role.
    assert [entry["title"] for entry in result["career"]] == ["Senior Recruiter"]


def test_malformed_individual_past_role_entries_are_skipped_not_fatal():
    evidence = _old_shape_evidence(
        past_roles=[
            "not-a-dict",  # not a mapping at all -> skipped
            {"title": "Recruiter", "company": "Acme", "industries": "should-be-a-list"},
            {"title": "Sourcer", "company": "Beta"},
        ]
    )
    result = rehydrate_presentation_fields(evidence, {}, None)
    titles = [entry["title"] for entry in result["career"]]
    # The non-dict entry is skipped; both real dict entries survive — nothing
    # raises even though one has an unexpectedly-typed field.
    assert titles == ["Senior Recruiter", "Recruiter", "Sourcer"]


def test_rehydrate_response_evidence_zips_candidates_and_evidence_by_index():
    candidates = [
        {"candidate_id": "c1", "raw_data": {"basic_profile": {"profile_picture_permalink": "https://img/c1.jpg"}}},
        {"candidate_id": "c2", "raw_data": {}},
    ]
    evidence_list = [_old_shape_evidence(candidate_id="c1"), _old_shape_evidence(candidate_id="c2", current_title="Sourcer", past_roles=[])]
    harvest_store = {"c1": _harvest_raw({"experience": []})}

    result = rehydrate_response_evidence(candidates, evidence_list, harvest_store)

    assert len(result) == 2
    assert result[0]["photo_url"] == "https://img/c1.jpg"
    assert result[1]["photo_url"] is None  # no harvest entry for c2, no CrustData photo either
    assert [entry["title"] for entry in result[1]["career"]] == ["Sourcer"]  # synthesized from current_title, no past_roles


def test_rehydrate_response_evidence_handles_missing_harvest_store():
    evidence_list = [_old_shape_evidence()]
    result = rehydrate_response_evidence([{"candidate_id": "c1"}], evidence_list, harvest_store=None)
    assert result[0]["photo_url"] is None
    assert result[0]["career"][0]["title"] == "Senior Recruiter"
