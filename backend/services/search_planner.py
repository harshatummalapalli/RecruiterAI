from backend.models.search_intent import SearchIntent
from backend.models.search_plan import SearchPlan, SearchQuery


class SearchPlanner:
    def build(self, intent: SearchIntent) -> SearchPlan:
        query = SearchQuery(
            include_titles=intent.titles.include_titles,
            exclude_titles=intent.titles.exclude_titles,
            required_skills=intent.skills.required_skills,
            preferred_skills=intent.skills.preferred_skills,
            countries=intent.location.countries,
            cities=intent.location.cities,
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

        return SearchPlan(
            searches=[query],
            strategy="single_query",
            reasoning="Deterministic mapping from SearchIntent to a single SearchQuery",
            confidence_score=intent.confidence_score,
        )
