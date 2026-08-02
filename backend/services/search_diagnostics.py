from collections import Counter
from typing import Dict, List, Optional

from backend.models.candidate import Candidate
from backend.models.search_plan import SearchPlan, SearchQuery


class SearchDiagnosticsReport:
    """Summary of a search run for debugging and analysis."""

    def __init__(
        self,
        total_queries: int,
        total_candidates: int,
        candidates_per_query: Dict[str, int],
        duplicate_candidates: List[Dict[str, Optional[str]]],
        average_provider_score: Optional[float],
        average_final_score: Optional[float],
        top_job_titles: List[tuple[str, int]],
        top_companies: List[tuple[str, int]],
        query_execution_summary: List[Dict[str, object]],
    ) -> None:
        self.total_queries = total_queries
        self.total_candidates = total_candidates
        self.candidates_per_query = candidates_per_query
        self.duplicate_candidates = duplicate_candidates
        self.average_provider_score = average_provider_score
        self.average_final_score = average_final_score
        self.top_job_titles = top_job_titles
        self.top_companies = top_companies
        self.query_execution_summary = query_execution_summary


class SearchDiagnostics:
    """Analyze a search run and produce a diagnostic report."""

    def analyze(self, plan: SearchPlan, candidates: List[Candidate]) -> SearchDiagnosticsReport:
        query_names = [query.query_name or f"Query {index + 1}" for index, query in enumerate(plan.searches)]
        candidates_per_query: Dict[str, int] = {name: 0 for name in query_names}
        duplicate_candidates: List[Dict[str, Optional[str]]] = []
        provider_scores: List[float] = []
        final_scores: List[float] = []
        title_counter: Counter[str] = Counter()
        company_counter: Counter[str] = Counter()
        query_summary: List[Dict[str, object]] = []

        query_count = len(plan.searches)
        for index, candidate in enumerate(candidates):
            query_name = query_names[index % query_count] if query_count else ""
            candidates_per_query[query_name] += 1
            provider_scores.append(float(candidate.provider_score or 0.0))
            if candidate.final_score is not None:
                final_scores.append(float(candidate.final_score))
            title_counter[candidate.title or ""] += 1
            company_counter[candidate.company or ""] += 1

        for query in plan.searches:
            query_name = query.query_name or f"Query {len(query_summary) + 1}"
            query_summary.append(
                {
                    "query_name": query_name,
                    "include_titles": query.include_titles,
                    "candidate_count": candidates_per_query.get(query_name, 0),
                }
            )

        seen: set[tuple[Optional[str], Optional[str]]] = set()
        for candidate in candidates:
            identity = (candidate.name, candidate.company)
            if identity in seen:
                duplicate_candidates.append({"name": candidate.name, "company": candidate.company})
            seen.add(identity)

        return SearchDiagnosticsReport(
            total_queries=len(plan.searches),
            total_candidates=len(candidates),
            candidates_per_query=candidates_per_query,
            duplicate_candidates=duplicate_candidates,
            average_provider_score=(sum(provider_scores) / len(provider_scores)) if provider_scores else None,
            average_final_score=(sum(final_scores) / len(final_scores)) if final_scores else None,
            top_job_titles=title_counter.most_common(5),
            top_companies=company_counter.most_common(5),
            query_execution_summary=query_summary,
        )
