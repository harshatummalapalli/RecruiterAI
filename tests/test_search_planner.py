from backend.models.search_intent import (
    AIFocus,
    CompanyPreferences,
    Experience,
    Location,
    PreviousBackground,
    Role,
    SearchIntent,
    Skills,
    Titles,
)
from backend.services.search_planner import (
    EXECUTIVE_TITLE_EXCLUSIONS,
    SearchPlanner,
    _is_leadership_role,
)


def test_build_creates_primary_natural_language_and_title_expansion_queries():
    intent = SearchIntent(
        role=Role(title="Machine Learning Engineer", seniority="senior", employment_type="full_time"),
        location=Location(countries=["US"], states=["New York"], cities=["New York"], work_mode="hybrid"),
        experience=Experience(minimum_years=5, maximum_years=10),
        titles=Titles(include_titles=["ML Engineer"], exclude_titles=["Manager"]),
        skills=Skills(required_skills=["Python", "PyTorch"], preferred_skills=["LLM"], required_weight=0.9, preferred_weight=0.1),
        previous_background=PreviousBackground(preferred_technologies=["LangChain"], preferred_companies=["OpenAI"]),
        ai_focus=AIFocus(llm=True, rag=True, agentic_ai=False, mcp=True, semantic_kernel=False),
        company_preferences=CompanyPreferences(exclude_current_companies=["Big Tech"], preferred_company_types=["startup"]),
        confidence_score=88,
        natural_language_search_query="Senior ML engineer with strong Python and PyTorch experience.",
    )

    plan = SearchPlanner().build(intent)

    assert len(plan.searches) == 2
    assert [query.query_name for query in plan.searches] == ["natural_language", "title_expansion"]

    primary, expansion = plan.searches

    # Primary: natural-language driven, NEVER a title hard filter. The LLM
    # sentence is preserved and then augmented with the confirmed location (a
    # weak/location-less hybrid query makes CrustData stop enforcing the hard
    # filters — see _augment_query).
    assert primary.natural_language_query.startswith(
        "Senior ML engineer with strong Python and PyTorch experience."
    )
    assert "New York" in primary.natural_language_query
    assert primary.include_titles == []
    assert primary.required_skills == ["Python", "PyTorch"]
    assert primary.preferred_skills == ["LLM"]

    # Title expansion: conservative title family, structural (list, not a
    # pipe string), no natural-language query of its own.
    assert expansion.include_titles == ["Machine Learning Engineer", "ML Engineer"]
    assert expansion.natural_language_query is None

    # Shared hard filters/exclusions apply to both queries.
    for query in plan.searches:
        assert query.countries == ["US"]
        assert query.states == ["New York"]
        assert query.cities == ["New York"]
        assert query.minimum_years == 5
        assert query.maximum_years == 10
        assert query.preferred_companies == ["OpenAI"]
        assert query.exclude_current_companies == ["Big Tech"]
        assert query.preferred_company_types == ["startup"]
        # Recruiter-specified exclusion plus the standing executive policy.
        assert "Manager" in query.exclude_titles
        for excluded in EXECUTIVE_TITLE_EXCLUSIONS:
            assert excluded in query.exclude_titles

    assert plan.confidence_score == 88


def test_build_normalizes_maximum_years_zero_to_no_maximum():
    # The JD parser's "not specified" placeholder for maximum_years is 0.
    # SearchQuery must normalize this to None so it never reaches the
    # provider as a real (and self-contradicting) upper bound.
    intent = SearchIntent(
        role=Role(title="Backend Engineer"),
        location=Location(countries=["United States"], cities=["New York"], work_mode="hybrid"),
        experience=Experience(minimum_years=5, maximum_years=0),
    )

    plan = SearchPlanner().build(intent)

    assert plan.searches[0].minimum_years == 5
    assert plan.searches[0].maximum_years is None


def test_build_falls_back_to_deterministic_natural_language_query_when_llm_omits_it():
    # No natural_language_search_query set (e.g. a non-LLM caller) — the
    # planner must still build a usable query from only what's on the
    # intent, never inventing a requirement that wasn't provided.
    intent = SearchIntent(
        role=Role(title="Senior Backend Engineer", seniority="Senior"),
        skills=Skills(required_skills=["Python"], preferred_skills=["Distributed Systems"]),
    )

    plan = SearchPlanner().build(intent)

    query_text = plan.searches[0].natural_language_query
    assert "Senior" in query_text
    assert "Python" in query_text
    assert "Distributed Systems" in query_text
    # Never invents a technology that wasn't on the intent.
    assert "PySpark" not in query_text
    assert "Kubernetes" not in query_text


def test_executive_exclusions_never_target_legitimate_senior_ic_titles():
    # "Principal Software Engineer" containing the ambiguous word "Principal"
    # must never become a rejection — only real leadership/executive titles
    # are excluded.
    protected_titles = [
        "Staff Engineer",
        "Principal Engineer",
        "Principal Software Engineer",
        "Principal Architect",
        "Lead Engineer",
        "Engineering Manager",
    ]
    for title in protected_titles:
        assert title not in EXECUTIVE_TITLE_EXCLUSIONS
        assert not any(title == excluded for excluded in EXECUTIVE_TITLE_EXCLUSIONS)


def test_build_omits_title_expansion_query_when_no_titles_available():
    intent = SearchIntent(skills=Skills(required_skills=["Python"]))

    plan = SearchPlanner().build(intent)

    assert len(plan.searches) == 1
    assert plan.searches[0].query_name == "natural_language"


def test_confirmed_core_supporting_differentiator_signals_survive_the_fallback_when_no_sentence_is_given():
    # The real shape of the Senior AI Software Engineer (.NET + AI) confirmation this bugfix was diagnosed from:
    # candidate_identity is generic ("Senior Backend Engineer"), skills.required/preferred are empty (the
    # confirmed-intake path never populates them — search_translator.to_search_intent doesn't set SearchIntent.skills
    # at all), and the only place the real requirements live is core/supporting/differentiator_signals. This is
    # exactly the SearchIntent api._gate_search_request hands to the planner once
    # RECRUITERAI_SEND_CONFIRMED_SEARCH_SENTENCE=false has blanked the model's own sentence.
    intent = SearchIntent(
        role=Role(title="Senior Backend Engineer", seniority="senior"),
        location=Location(countries=["India"], work_mode="remote"),
        experience=Experience(minimum_years=5),
        core_signals=[
            "5+ years of professional experience",
            "Proficiency in C# .NET",
            "Experience in AI Engineering",
            "Experience deploying AI into production",
        ],
        supporting_signals=["Agentic AI frameworks"],
        differentiator_signals=["LangChain or LangGraph"],
        natural_language_search_query=None,
    )

    plan = SearchPlanner().build(intent)
    query_text = plan.searches[0].natural_language_query

    for requirement in ["C# .NET", "AI Engineering", "deploying AI into production", "Agentic AI frameworks", "LangChain or LangGraph"]:
        assert requirement in query_text, query_text

    # Not title/seniority-only: the pre-fix behavior for this exact shape was "senior Senior Backend Engineer" alone.
    assert query_text != "senior Senior Backend Engineer"
    assert len(query_text) > len("senior Senior Backend Engineer") + 40


def test_required_and_preferred_skills_still_reach_the_fallback_for_the_legacy_non_intake_shape():
    # The older /parse-jd path populates skills.required/preferred but never core/supporting/differentiator_signals —
    # the combined fallback must keep serving that shape exactly as before.
    intent = SearchIntent(
        role=Role(title="Senior Backend Engineer", seniority="Senior"),
        skills=Skills(required_skills=["Python"], preferred_skills=["Distributed Systems"]),
    )

    plan = SearchPlanner().build(intent)
    query_text = plan.searches[0].natural_language_query

    assert "Senior" in query_text
    assert "Python" in query_text
    assert "Distributed Systems" in query_text
    assert "PySpark" not in query_text


def test_llm_query_is_augmented_with_location_and_missing_capabilities():
    # The exact NCS shape: the LLM sentence omitted the defining capability
    # (RAG, carried as a supporting signal) and never named the location.
    # _augment_query must inject both so the hybrid query is specific and
    # location-anchored (which is what makes CrustData's hard filters bind).
    intent = SearchIntent(
        role=Role(title="AI Data Engineer", seniority="mid"),
        location=Location(countries=["India"], states=["Maharashtra"], cities=["Pune"], radius_miles=10.0, radius_place="Pune, Maharashtra"),
        experience=Experience(minimum_years=5, maximum_years=8),
        core_signals=["Data Pipeline Development", "Python", "SQL", "Apache Spark (PySpark)"],
        supporting_signals=["Knowledge Base and RAG Solutions"],
        natural_language_search_query=(
            "Looking for a mid-level AI Data Engineer with 5-8 years of experience, "
            "proficient in Python, SQL, and Apache Spark, capable of designing data pipelines."
        ),
    )

    query = SearchPlanner().build(intent).searches[0].natural_language_query

    # Location is now named in the query text.
    assert "Pune" in query
    # The defining capability the LLM omitted is injected.
    assert "Knowledge Base and RAG Solutions" in query
    # The original LLM sentence is preserved, not discarded.
    assert query.startswith("Looking for a mid-level AI Data Engineer")


def test_augment_query_is_idempotent_for_already_present_terms():
    # Capabilities and location already in the sentence must not be duplicated.
    intent = SearchIntent(
        role=Role(title="AI Engineer", seniority="mid"),
        location=Location(cities=["Pune"], states=["Maharashtra"]),
        core_signals=["Python"],
        supporting_signals=["RAG"],
        natural_language_search_query="AI engineers in Pune, Maharashtra skilled in Python and RAG.",
    )

    query = SearchPlanner().build(intent).searches[0].natural_language_query

    assert query.lower().count("python") == 1
    assert query.lower().count("rag") == 1
    assert query.lower().count("pune") == 1
    # Nothing was appended, so no injected clauses.
    assert "strong experience in" not in query
    assert "based in" not in query


def test_years_signals_are_not_injected_as_search_terms():
    intent = SearchIntent(
        role=Role(title="AI Engineer", seniority="mid"),
        location=Location(cities=["Pune"]),
        core_signals=["5+ years of professional experience", "Python"],
        natural_language_search_query="AI engineer skilled in machine learning.",
    )

    query = SearchPlanner().build(intent).searches[0].natural_language_query

    assert "Python" in query           # a real capability is injected
    assert "years" not in query.lower()  # a pure experience statement is not


def test_is_leadership_role_detection():
    assert _is_leadership_role(SearchIntent(role=Role(title="Engineering Manager")))
    assert _is_leadership_role(SearchIntent(role=Role(title="Director of Data")))
    assert _is_leadership_role(SearchIntent(role=Role(title="Chief Technology Officer")))
    assert _is_leadership_role(SearchIntent(role=Role(title="VP, Finance")))
    assert _is_leadership_role(SearchIntent(role=Role(title="Head of AI")))
    assert _is_leadership_role(SearchIntent(role=Role(title="Software Engineer", seniority="Director")))
    # Individual-contributor roles are not leadership.
    assert not _is_leadership_role(SearchIntent(role=Role(title="AI Data Engineer", seniority="mid")))
    assert not _is_leadership_role(SearchIntent(role=Role(title="Senior Data Scientist", seniority="senior")))


def test_executive_exclusions_suppressed_for_a_leadership_role():
    # Hiring a Director: the blanket exec exclusions must NOT strip Director/VP/
    # C-level, or we drop the very candidates sought. Recruiter-stated
    # exclusions are still honored.
    intent = SearchIntent(
        role=Role(title="Director of Data Engineering", seniority="director"),
        titles=Titles(exclude_titles=["Intern"]),
    )

    plan = SearchPlanner().build(intent)

    for query in plan.searches:
        assert "Director" not in query.exclude_titles
        assert "VP" not in query.exclude_titles
        assert "Chief Data Officer" not in query.exclude_titles
        assert "Intern" in query.exclude_titles  # recruiter's own exclusion kept


def test_executive_exclusions_applied_for_an_ic_role():
    intent = SearchIntent(role=Role(title="AI Data Engineer", seniority="mid"))

    plan = SearchPlanner().build(intent)

    for query in plan.searches:
        for excluded in EXECUTIVE_TITLE_EXCLUSIONS:
            assert excluded in query.exclude_titles


def test_any_time_company_scope_reaches_the_search_query():
    # Phase 2 §2.5: CompanyPreferences any-time ("ever") lists flow through the
    # planner to every SearchQuery (the provider maps them to the any-time field).
    from backend.models.search_intent import CompanyPreferences as _CP
    intent = SearchIntent(
        role=Role(title="Backend Engineer", seniority="senior"),
        company_preferences=_CP(preferred_companies_ever=["Infosys"], exclude_companies_ever=["Acme"]),
    )
    plan = SearchPlanner().build(intent)
    for q in plan.searches:
        assert q.preferred_companies_ever == ["Infosys"]
        assert q.exclude_companies_ever == ["Acme"]
