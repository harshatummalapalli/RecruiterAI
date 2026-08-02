from backend.models.candidate import Candidate
from backend.models.search_plan import SearchPlan, SearchQuery
from backend.services.search_diagnostics import SearchDiagnostics


def test_analyze_reports_search_run_summary() -> None:
    plan = SearchPlan(
        searches=[
            SearchQuery(query_name="Primary", include_titles=["ML Engineer"]),
            SearchQuery(query_name="Alternate 1", include_titles=["Data Scientist"]),
        ]
    )

    candidates = [
        Candidate(name="Alice", title="ML Engineer", company="OpenAI", provider_score=0.95, final_score=9.5),
        Candidate(name="Alice", title="ML Engineer", company="OpenAI", provider_score=0.92, final_score=9.2),
        Candidate(name="Bob", title="Data Scientist", company="Anthropic", provider_score=0.88, final_score=8.8),
    ]

    report = SearchDiagnostics().analyze(plan, candidates)

    assert report.total_queries == 2
    assert report.total_candidates == 3
    assert report.candidates_per_query["Primary"] == 2
    assert report.candidates_per_query["Alternate 1"] == 1
    assert len(report.duplicate_candidates) == 1
    assert report.average_provider_score == 0.9166666666666666
    assert report.average_final_score == 9.166666666666666
    assert report.top_job_titles == [("ML Engineer", 2), ("Data Scientist", 1)]
    assert report.top_companies == [("OpenAI", 2), ("Anthropic", 1)]
    assert report.query_execution_summary[0]["query_name"] == "Primary"
