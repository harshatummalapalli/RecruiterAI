from backend.models.candidate import Candidate
from backend.models.candidate_evidence import HarvestEvidence
from backend.models.search_intent import Role, SearchIntent
from backend.services.candidate_evidence_builder import build_candidate_evidence


def _harvest(element: dict) -> HarvestEvidence:
    return HarvestEvidence(raw={"element": element}, success=True, cost=0.0064)


def test_education_survives_normalization_when_present() -> None:
    # Real shape confirmed live against CrustData (not documentation-guessed):
    # institution is "school", dates are "start_year"/"end_year" (ints), and
    # there is no separate field_of_study key at all.
    candidate = Candidate(
        name="Grad",
        title="Data Engineer",
        raw_data={
            "education": {
                "schools": [
                    {"school": "MIT", "degree": "Master of Engineering - MEng", "start_year": 2012, "end_year": 2016, "description": ""}
                ]
            }
        },
    )
    evidence = build_candidate_evidence(candidate, SearchIntent(role=Role(title="Data Engineer")))

    assert len(evidence.education) == 1
    assert evidence.education[0].institution == "MIT"
    assert evidence.education[0].degree == "Master of Engineering - MEng"
    assert evidence.education[0].start_date == "2012"
    assert evidence.education[0].end_date == "2016"
    # An empty-string description is treated as absent, not as an empty fact.
    assert evidence.education[0].description is None


def test_education_absence_is_reported_as_uncertainty_not_a_negative_fact() -> None:
    candidate = Candidate(name="NoEdu", title="Data Engineer", raw_data={})
    evidence = build_candidate_evidence(candidate, SearchIntent(role=Role(title="Data Engineer")))

    assert evidence.education == []
    assert any(note.field == "education" for note in evidence.uncertainty)
    assert "not returned" in next(n.note for n in evidence.uncertainty if n.field == "education")


def test_career_history_survives_normalization() -> None:
    candidate = Candidate(
        name="Vet",
        title="Senior Data Engineer",
        raw_data={
            "experience": {
                "employment_details": {
                    "past": [
                        {"title": "Data Analyst", "name": "Acme", "company_industries": ["Retail"], "seniority_level": "Mid"},
                    ]
                }
            }
        },
    )
    evidence = build_candidate_evidence(candidate, SearchIntent(role=Role(title="Senior Data Engineer")))

    assert len(evidence.past_roles) == 1
    assert evidence.past_roles[0].title == "Data Analyst"
    assert evidence.past_roles[0].industries == ["Retail"]


def test_company_context_survives_normalization() -> None:
    candidate = Candidate(
        name="Ctx",
        title="Data Engineer",
        company="Acme",
        raw_data={
            "experience": {
                "employment_details": {
                    "current": [
                        {
                            "company_industries": ["Software"],
                            "function_category": "Engineering",
                            "seniority_level": "Senior",
                            "company_headcount_range": "1001-5000",
                            "company_type": "Public",
                        }
                    ]
                }
            }
        },
    )
    evidence = build_candidate_evidence(candidate, SearchIntent(role=Role(title="Data Engineer")))

    assert evidence.current_industries == ["Software"]
    assert evidence.current_function == "Engineering"
    assert evidence.current_seniority == "Senior"
    assert evidence.current_headcount == "1001-5000"
    assert evidence.current_company_type == "Public"


def test_provider_metadata_survives_when_present() -> None:
    candidate = Candidate(
        name="Meta",
        title="Data Engineer",
        raw_data={"fit": "strong", "metadata": {"updated_at": "2026-01-01"}, "matched_queries": ["natural_language"]},
    )
    evidence = build_candidate_evidence(candidate, SearchIntent(role=Role(title="Data Engineer")))

    assert evidence.search_evidence.provider_fit == "strong"
    assert evidence.updated_at == "2026-01-01"
    assert evidence.search_evidence.matched_queries == ["natural_language"]


def test_contact_is_preserved_but_never_used_as_ranking_relevant_evidence_field() -> None:
    candidate = Candidate(name="Reachable", title="Data Engineer", email="a@example.com", phone="555-0100", raw_data={})
    evidence = build_candidate_evidence(candidate, SearchIntent(role=Role(title="Data Engineer")))

    assert evidence.contact.email == "a@example.com"
    assert evidence.contact.phone == "555-0100"
    # Contact fields are not part of RoleAlignment at all — structurally
    # absent from the alignment computation, not merely unweighted.
    assert not hasattr(evidence.role_alignment, "contact")


def test_short_acronyms_like_ai_are_not_silently_dropped_from_title_comparison() -> None:
    # Regression: found by testing this exact model against real candidates
    # for a "Senior AI Platform Engineer" search. "Senior AI Engineer" was
    # classified "unclear" relevance because a 3+ character word filter
    # silently dropped the 2-letter term "AI" from both titles, hiding real,
    # obvious overlap.
    candidate = Candidate(name="AI Eng", title="Senior AI Engineer", raw_data={})
    evidence = build_candidate_evidence(candidate, SearchIntent(role=Role(title="Senior AI Platform Engineer")))

    assert evidence.role_alignment.title_relevance in ("direct", "adjacent")
    assert "ai" in evidence.role_alignment.title_relevance_basis.lower()


def test_duplicate_education_entries_from_the_provider_are_deduplicated() -> None:
    # Regression: CrustData was observed live to return the exact same
    # school entry twice for a real candidate.
    candidate = Candidate(
        name="Dup",
        title="Data Engineer",
        raw_data={
            "education": {
                "schools": [
                    {"school": "Seneca College", "degree": "Postgraduate Certificate", "start_year": 2018, "end_year": 2019},
                    {"school": "Seneca College", "degree": "Postgraduate Certificate", "start_year": 2018, "end_year": 2019},
                ]
            }
        },
    )
    evidence = build_candidate_evidence(candidate, SearchIntent(role=Role(title="Data Engineer")))

    assert len(evidence.education) == 1


def test_matched_signal_names_its_source_for_a_verifiable_explanation() -> None:
    candidate = Candidate(
        name="Sourced",
        title="Data Engineer",
        raw_data={"basic_profile": {"headline": "Data Engineer building Kafka pipelines"}},
    )
    intent = SearchIntent(role=Role(title="Data Engineer"), core_signals=["Production experience with Kafka."])
    evidence = build_candidate_evidence(candidate, intent)

    assert len(evidence.role_alignment.matched_signals) == 1
    assert evidence.role_alignment.matched_signals[0].source == "headline"


def test_signal_matching_never_searches_industry_classification_text() -> None:
    # Regression: "information" from a past employer's industry tag
    # ("Technology, Information and Internet") was being counted as
    # evidence of "information retrieval" skill — industries are corporate
    # taxonomy, not a description of the candidate's own work, so they must
    # never be part of the signal-matching corpus at all.
    candidate = Candidate(
        name="Industry Noise",
        title="Software Engineer",
        raw_data={
            "experience": {
                "employment_details": {
                    "past": [{"title": "Developer", "name": "Acme", "company_industries": ["Technology, Information and Internet"]}]
                }
            }
        },
    )
    intent = SearchIntent(role=Role(title="Software Engineer"), supporting_signals=["Information retrieval fundamentals."])
    evidence = build_candidate_evidence(candidate, intent)

    assert evidence.role_alignment.matched_signals == []


def test_headline_contributes_to_title_relevance_when_the_formal_title_is_generic() -> None:
    # Regression: found on a real search where the formal title field was a
    # generic internal label ("Senior Software Engineer") but the
    # candidate's own headline specifically named the target discipline.
    candidate = Candidate(
        name="Generic Title",
        title="Senior Software Engineer",
        raw_data={"basic_profile": {"headline": "Senior AI Engineer | LLM Apps, RAG & Agentic Workflows"}},
    )
    evidence = build_candidate_evidence(candidate, SearchIntent(role=Role(title="Senior AI Platform Engineer")))

    assert evidence.role_alignment.title_relevance == "adjacent"
    assert "headline" in evidence.role_alignment.title_relevance_basis.lower()


def test_no_role_specific_hardcoding_generalizes_across_disparate_role_families() -> None:
    # Same builder, no per-role branch, across a genuinely disparate set of
    # role archetypes named in the product ask.
    cases = [
        ("Infrastructure Engineer", "Infrastructure Engineer"),
        ("AI Software Engineer", "AI Software Engineer"),
        ("Backend Engineer", "Backend Engineer"),
        ("Lead Data Analyst", "Lead Data Analyst"),
        ("eDiscovery Project Manager", "eDiscovery Project Manager"),
    ]
    for target_title, candidate_title in cases:
        candidate = Candidate(name="Direct", title=candidate_title, raw_data={})
        evidence = build_candidate_evidence(candidate, SearchIntent(role=Role(title=target_title)))
        assert evidence.role_alignment.title_relevance == "direct", f"failed for {target_title}"


def test_generic_domain_restating_words_are_not_counted_as_signal_hits() -> None:
    # "data" appearing in a differentiator sentence about a data-engineering
    # role would otherwise trivially "match" almost every candidate's title
    # in that search, which is not real differentiating evidence.
    candidate = Candidate(name="Generic", title="Senior Data Engineer", raw_data={})
    intent = SearchIntent(
        role=Role(title="Senior Data Engineer"),
        differentiator_signals=["Experience with AI/ML data infrastructure and retrieval technologies such as Solr or Qdrant."],
    )
    evidence = build_candidate_evidence(candidate, intent)

    assert evidence.role_alignment.matched_signals == []
    assert len(evidence.role_alignment.unmatched_signals) == 1


def test_specific_technology_terms_still_match_despite_the_generic_term_filter() -> None:
    candidate = Candidate(name="Specific", title="Data Engineer, Solr search", raw_data={})
    intent = SearchIntent(
        role=Role(title="Data Engineer"),
        differentiator_signals=["Experience with AI/ML data infrastructure and retrieval technologies such as Solr or Qdrant."],
    )
    evidence = build_candidate_evidence(candidate, intent)

    assert len(evidence.role_alignment.matched_signals) == 1
    assert evidence.role_alignment.matched_signals[0].matched_term == "solr"


def test_unmatched_signals_are_never_phrased_as_negative_evidence_in_the_model() -> None:
    candidate = Candidate(name="NoHit", title="Data Engineer", raw_data={})
    intent = SearchIntent(role=Role(title="Data Engineer"), core_signals=["Proficiency in Rust"])
    evidence = build_candidate_evidence(candidate, intent)

    assert len(evidence.role_alignment.unmatched_signals) == 1
    assert evidence.role_alignment.unmatched_signals[0].matched_term == ""


# ---------------------------------------------------------------------------
# Harvest second-stage enrichment — normalization, source-labeling,
# generic-skill exclusion, self-reported years, evidence corroboration.
# ---------------------------------------------------------------------------


def test_harvest_employment_description_becomes_a_source_labeled_matched_signal() -> None:
    candidate = Candidate(name="Enriched", title="Software Engineer", raw_data={})
    harvest = _harvest(
        {
            "experience": [
                {"position": "AI Engineer", "companyName": "Acme", "description": "Built a production RAG retrieval-routing system."}
            ]
        }
    )
    intent = SearchIntent(role=Role(title="Software Engineer"), core_signals=["Retrieval-Augmented Generation (RAG) experience."])

    evidence = build_candidate_evidence(candidate, intent, harvest_evidence=harvest)

    matches = evidence.role_alignment.matched_signals
    assert len(matches) == 1
    assert matches[0].source == "harvest: employment description"
    assert matches[0].evidence_detail == "AI Engineer at Acme"
    assert matches[0].matched_term == "rag"


def test_harvest_project_becomes_a_matched_signal() -> None:
    candidate = Candidate(name="Builder", title="Software Engineer", raw_data={})
    harvest = _harvest({"projects": [{"title": "Agentic RAG System", "description": "Built with LangGraph."}]})
    intent = SearchIntent(role=Role(title="Software Engineer"), core_signals=["Experience with LangGraph."])

    evidence = build_candidate_evidence(candidate, intent, harvest_evidence=harvest)

    matches = evidence.role_alignment.matched_signals
    assert len(matches) == 1
    assert matches[0].source == "harvest: project"
    assert matches[0].evidence_detail == "Agentic RAG System"


def test_harvest_certification_becomes_a_matched_signal() -> None:
    candidate = Candidate(name="Certified", title="Software Engineer", raw_data={})
    harvest = _harvest({"certifications": [{"title": "Microsoft Certified: Azure AI Engineer Associate"}]})
    intent = SearchIntent(role=Role(title="Software Engineer"), supporting_signals=["Experience with Azure."])

    evidence = build_candidate_evidence(candidate, intent, harvest_evidence=harvest)

    matches = evidence.role_alignment.matched_signals
    assert len(matches) == 1
    assert matches[0].source == "harvest: certification"
    assert matches[0].evidence_detail == "Microsoft Certified: Azure AI Engineer Associate"


def test_harvest_skill_becomes_a_matched_signal() -> None:
    candidate = Candidate(name="Skilled", title="Software Engineer", raw_data={})
    harvest = _harvest({"skills": [{"name": "Model Context Protocol (MCP)"}]})
    intent = SearchIntent(role=Role(title="Software Engineer"), supporting_signals=["Experience with MCP."])

    evidence = build_candidate_evidence(candidate, intent, harvest_evidence=harvest)

    matches = evidence.role_alignment.matched_signals
    assert len(matches) == 1
    assert matches[0].source == "harvest: skill"
    assert matches[0].evidence_detail == "Model Context Protocol (MCP)"


def test_generic_harvest_skill_never_becomes_strong_evidence() -> None:
    # "Software Engineering" is exactly the kind of generic, near-universal
    # term the CrustData stoplist already excludes — the same filter must
    # apply to Harvest skills, not just CrustData text.
    candidate = Candidate(name="Generic", title="Software Engineer", raw_data={})
    harvest = _harvest({"skills": [{"name": "Software Engineering"}]})
    intent = SearchIntent(role=Role(title="Software Engineer"), core_signals=["Software engineering experience."])

    evidence = build_candidate_evidence(candidate, intent, harvest_evidence=harvest)

    assert evidence.role_alignment.matched_signals == []


def test_self_reported_years_are_labeled_unverified_not_converted_to_a_fact() -> None:
    candidate = Candidate(name="Self Reported", title="Software Engineer", raw_data={})
    harvest = _harvest({"about": "AI engineer with 11+ years of experience building production systems."})
    intent = SearchIntent(role=Role(title="Software Engineer"))

    evidence = build_candidate_evidence(candidate, intent, harvest_evidence=harvest)

    assert evidence.harvest_self_reported_experience is not None
    assert "11+ years" in evidence.harvest_self_reported_experience
    assert "self-reported" in evidence.harvest_self_reported_experience.lower()
    assert "not verified" in evidence.harvest_self_reported_experience.lower()
    # Never promoted into a matched_signal/strong-evidence-shaped fact.
    assert evidence.role_alignment.matched_signals == []


def test_about_text_never_feeds_signal_matching_even_when_it_contains_a_core_term() -> None:
    candidate = Candidate(name="About Only", title="Software Engineer", raw_data={})
    harvest = _harvest({"about": "I love RAG and agentic systems."})
    intent = SearchIntent(role=Role(title="Software Engineer"), core_signals=["Retrieval-Augmented Generation (RAG) experience."])

    evidence = build_candidate_evidence(candidate, intent, harvest_evidence=harvest)

    # "about" is deliberately excluded from labeled_text_sources() — a term
    # appearing only there must never become ranking/explanation evidence.
    assert evidence.role_alignment.matched_signals == []
    assert evidence.harvest_about == "I love RAG and agentic systems."


def test_a_term_found_in_both_crustdata_and_harvest_produces_only_one_matched_signal() -> None:
    # Corroboration, not repetition: the CrustData headline already
    # mentions "RAG" — Harvest's employment description mentioning it too
    # must not create a second, duplicate matched_signal for the same term.
    candidate = Candidate(
        name="Dual Source",
        title="Software Engineer",
        raw_data={"basic_profile": {"headline": "Software Engineer building RAG systems"}},
    )
    harvest = _harvest({"experience": [{"position": "Engineer", "companyName": "Acme", "description": "Worked on RAG pipelines."}]})
    intent = SearchIntent(role=Role(title="Software Engineer"), core_signals=["Retrieval-Augmented Generation (RAG) experience."])

    evidence = build_candidate_evidence(candidate, intent, harvest_evidence=harvest)

    matches = evidence.role_alignment.matched_signals
    assert len(matches) == 1
    # CrustData sources are checked before Harvest sources (priority order),
    # so the stronger/first-found attribution wins.
    assert matches[0].source == "headline"


def test_harvest_reveals_a_term_crustdata_never_had_evidence_for() -> None:
    candidate = Candidate(name="New Evidence", title="Software Engineer", raw_data={})
    harvest = _harvest({"skills": [{"name": "LangGraph"}]})
    intent = SearchIntent(role=Role(title="Software Engineer"), supporting_signals=["Experience with LangGraph."])

    evidence = build_candidate_evidence(candidate, intent, harvest_evidence=harvest)

    assert len(evidence.role_alignment.matched_signals) == 1
    assert evidence.role_alignment.matched_signals[0].source == "harvest: skill"


def test_failed_harvest_evidence_never_populates_harvest_fields() -> None:
    candidate = Candidate(name="Failed", title="Software Engineer", raw_data={})
    harvest = HarvestEvidence(success=False, error="timeout")
    intent = SearchIntent(role=Role(title="Software Engineer"), core_signals=["Python."])

    evidence = build_candidate_evidence(candidate, intent, harvest_evidence=harvest)

    assert evidence.harvest_employment_descriptions == []
    assert evidence.harvest_skills == []
    assert evidence.harvest_about is None
    assert evidence.harvest is harvest  # preserved for provenance/debugging even on failure
