from typing import List

from backend.models.candidate import Candidate
from backend.models.search_intent import SearchIntent
from backend.utils.text import normalize_text, normalize_text_values


REQUIRED_SKILL_WEIGHT = 2.0
PREFERRED_SKILL_WEIGHT = 0.5
INCLUDE_TITLE_WEIGHT = 3.0
EXCLUDE_TITLE_WEIGHT = 3.0
PREFERRED_COMPANY_WEIGHT = 2.0
EXCLUDED_COMPANY_WEIGHT = 2.0
LOCATION_WEIGHT = 1.0
# A candidate independently surfaced by more than one discovery query
# (e.g. both the natural-language primary search and the title-expansion
# search) is itself a positive signal — two different retrieval paths
# agreeing is stronger evidence than either alone.
CONVERGENCE_WEIGHT = 1.5


class CandidateRanker:
    """Rank candidates against a SearchIntent using provider-agnostic scoring rules."""

    def rank(self, candidates: List[Candidate], intent: SearchIntent) -> List[Candidate]:
        ranked_candidates: List[Candidate] = []

        for candidate in candidates:
            score = self._calculate_score(candidate, intent)
            candidate.final_score = score
            ranked_candidates.append(candidate)

        return sorted(ranked_candidates, key=lambda item: (item.final_score or 0.0, item.name or ""), reverse=True)

    def _calculate_score(self, candidate: Candidate, intent: SearchIntent) -> float:
        score = float(candidate.provider_score or 0.0)

        required_skills = set(intent.skills.required_skills or [])
        preferred_skills = set(intent.skills.preferred_skills or [])
        include_titles = {normalize_text(title) for title in intent.titles.include_titles or [] if title}
        exclude_titles = {normalize_text(title) for title in intent.titles.exclude_titles or [] if title}
        preferred_companies = {normalize_text(company) for company in intent.previous_background.preferred_companies or [] if company}
        excluded_companies = {normalize_text(company) for company in intent.company_preferences.exclude_current_companies or [] if company}

        # CrustData's person_search response never includes a "skills" field
        # on this account's plan (confirmed live — requesting it 403s the
        # whole call), so candidate.raw_data has no "skills" key in practice.
        # This intersection is therefore always empty today; it's left in
        # place, rather than hardcoded to zero, so it activates automatically
        # if the plan is ever upgraded — but it must never be treated as
        # meaningful evidence in the meantime.
        candidate_skills = {normalize_text(skill) for skill in self._normalize_text_values(candidate.raw_data.get("skills", []))}
        candidate_title = normalize_text(candidate.title)
        candidate_company = normalize_text(candidate.company)
        candidate_location = normalize_text(candidate.location)
        intent_locations = {normalize_text(location) for location in [*intent.location.countries, *intent.location.cities] if location}

        if required_skills:
            matching_required_skills = required_skills.intersection(candidate_skills)
            score += len(matching_required_skills) * REQUIRED_SKILL_WEIGHT

        if preferred_skills:
            matching_preferred_skills = preferred_skills.intersection(candidate_skills)
            score += len(matching_preferred_skills) * PREFERRED_SKILL_WEIGHT

        if include_titles and candidate_title:
            if candidate_title in include_titles:
                score += INCLUDE_TITLE_WEIGHT

        if exclude_titles and candidate_title:
            if candidate_title in exclude_titles:
                score -= EXCLUDE_TITLE_WEIGHT

        if preferred_companies and candidate_company:
            if candidate_company in preferred_companies:
                score += PREFERRED_COMPANY_WEIGHT

        if excluded_companies and candidate_company:
            if candidate_company in excluded_companies:
                score -= EXCLUDED_COMPANY_WEIGHT

        if intent_locations and candidate_location:
            if any(location in candidate_location for location in intent_locations):
                score += LOCATION_WEIGHT

        matched_queries = candidate.raw_data.get("matched_queries")
        if isinstance(matched_queries, list) and len(set(matched_queries)) > 1:
            score += CONVERGENCE_WEIGHT

        return score

    def _normalize_text_values(self, values: List[str]) -> List[str]:
        return normalize_text_values([value for value in values if isinstance(value, str)])
