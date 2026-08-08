from typing import List, Set

from backend.models.search_intent import SearchIntent
from backend.models.search_plan import SearchPlan, SearchQuery
from backend.utils.text import deduplicate_preserve_order, normalize_text


class SearchPlanner:
    def build(self, intent: SearchIntent) -> SearchPlan:
        title_variants = self._build_title_variants(intent)
        queries: List[SearchQuery] = []
        seen: Set[tuple] = set()

        for index, title in enumerate(title_variants, start=1):
            query = SearchQuery(
                query_name=self._build_query_name(index),
                include_titles=[title],
                exclude_titles=intent.titles.exclude_titles,
                required_skills=intent.skills.required_skills,
                preferred_skills=intent.skills.preferred_skills,
                countries=intent.location.countries,
                cities=intent.location.cities,
                zip_codes=intent.location.zip_codes,
                radius_miles=intent.location.radius_miles,
                work_mode=intent.location.work_mode,
                minimum_years=intent.experience.minimum_years,
                maximum_years=intent.experience.maximum_years,
                preferred_companies=intent.previous_background.preferred_companies,
                exclude_current_companies=intent.company_preferences.exclude_current_companies,
                preferred_company_types=intent.company_preferences.preferred_company_types,
                must_have=intent.ranking.must_have,
                nice_to_have=intent.ranking.nice_to_have,
                bonus=intent.ranking.bonus,
            )
            key = (
                tuple(query.include_titles),
                tuple(query.exclude_titles),
                tuple(query.required_skills),
                tuple(query.preferred_skills),
                tuple(query.countries),
                tuple(query.cities),
                tuple(query.zip_codes),
                query.radius_miles,
                query.work_mode,
                query.minimum_years,
                query.maximum_years,
                tuple(query.preferred_companies),
                tuple(query.exclude_current_companies),
                tuple(query.preferred_company_types),
                tuple(query.must_have),
                tuple(query.nice_to_have),
                tuple(query.bonus),
            )
            if key in seen:
                continue
            seen.add(key)
            queries.append(query)

        return SearchPlan(
            searches=queries,
            strategy="multi_query",
            reasoning="Deterministic mapping from SearchIntent to multiple title-based SearchQuery variants",
            confidence_score=intent.confidence_score,
        )

    def _build_title_variants(self, intent: SearchIntent) -> List[str]:
        titles: List[str] = []
        role_title = intent.role.title or ""
        include_titles = [title for title in intent.titles.include_titles if title]

        if role_title:
            titles.append(role_title)
        titles.extend(include_titles)

        if role_title and role_title in titles:
            titles = [title for title in titles if title != role_title or titles.index(title) == 0]

        return self._deduplicate_titles(titles)

    def _deduplicate_titles(self, titles: List[str]) -> List[str]:
        return deduplicate_preserve_order(titles)

    def _build_query_name(self, index: int) -> str:
        if index == 1:
            return "Primary"
        return f"Alternate {index - 1}"
