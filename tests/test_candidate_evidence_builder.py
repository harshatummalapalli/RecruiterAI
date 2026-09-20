from backend.models.candidate import Candidate
from backend.models.search_intent import Role, SearchIntent
from backend.services.candidate_evidence_builder import build_candidate_evidence


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
