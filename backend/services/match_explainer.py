from typing import List, Optional

from backend.models.candidate import Candidate
from backend.models.match_explanation import MatchExplanation
from backend.models.search_intent import SearchIntent
from backend.utils.text import deduplicate_preserve_order, equals_normalized_text, normalize_text


class MatchExplainer:
    """Generate a provider-agnostic explanation for how a candidate matches a search intent."""

    def explain(self, candidate: Candidate, intent: SearchIntent) -> MatchExplanation:
        required_skills = [skill for skill in (intent.skills.required_skills or []) if skill]
        preferred_skills = [skill for skill in (intent.skills.preferred_skills or []) if skill]

        candidate_skills = self._candidate_skills(candidate)
        matched_required_skills = [skill for skill in required_skills if self._skill_matches(skill, candidate_skills)]
        missing_required_skills = [skill for skill in required_skills if skill not in matched_required_skills]
        matched_preferred_skills = [skill for skill in preferred_skills if self._skill_matches(skill, candidate_skills)]
        missing_preferred_skills = [skill for skill in preferred_skills if skill not in matched_preferred_skills]

        title_match = self._matches_title(candidate.title, intent.titles.include_titles)
        location_match = self._matches_location(candidate.location, intent.location.countries, intent.location.cities)
        company_match = self._matches_company(candidate.company, intent.previous_background.preferred_companies)
        experience_match = self._matches_experience(candidate.raw_data, intent.experience.minimum_years, intent.experience.maximum_years)

        matched_titles = [candidate.title] if title_match and candidate.title else []
        matched_skills = deduplicate_preserve_order(matched_required_skills + matched_preferred_skills)
        missing_skills = deduplicate_preserve_order(missing_required_skills)
        matched_location = candidate.location if location_match else None
        matched_ai_technologies = self._candidate_ai_technologies(candidate)
        matched_experience, missing_experience = self._experience_summary(candidate.raw_data, intent.experience.minimum_years, intent.experience.maximum_years)
        potential_risks = self._build_potential_risks(
            title_match=title_match,
            location_match=location_match,
            company_match=company_match,
            experience_match=experience_match,
            missing_skills=missing_skills,
            missing_experience=missing_experience,
        )

        summary = self._build_summary(
            title_match=title_match,
            location_match=location_match,
            company_match=company_match,
            experience_match=experience_match,
            matched_required_skills=matched_required_skills,
            missing_required_skills=missing_required_skills,
            matched_preferred_skills=matched_preferred_skills,
        )

        return MatchExplanation(
            final_score=candidate.final_score,
            matched_required_skills=matched_required_skills,
            missing_required_skills=missing_required_skills,
            matched_preferred_skills=matched_preferred_skills,
            missing_preferred_skills=missing_preferred_skills,
            matched_titles=matched_titles,
            matched_skills=matched_skills,
            missing_skills=missing_skills,
            matched_location=matched_location,
            matched_experience=matched_experience,
            matched_ai_technologies=matched_ai_technologies,
            missing_experience=missing_experience,
            potential_risks=potential_risks,
            title_match=title_match,
            location_match=location_match,
            company_match=company_match,
            experience_match=experience_match,
            summary=summary,
        )

    def _candidate_skills(self, candidate: Candidate) -> List[str]:
        raw_data = candidate.raw_data or {}
        skills: List[str] = []
        if isinstance(raw_data.get("skills"), list):
            skills.extend([skill for skill in raw_data["skills"] if isinstance(skill, str)])
        if isinstance(raw_data.get("raw_skills"), list):
            skills.extend([skill for skill in raw_data["raw_skills"] if isinstance(skill, str)])
        if candidate.title:
            skills.append(candidate.title)
        return deduplicate_preserve_order(skills)

    def _skill_matches(self, required_skill: str, candidate_skills: List[str]) -> bool:
        normalized_required = normalize_text(required_skill)
        return any(normalized_required == normalize_text(skill) for skill in candidate_skills)

    def _matches_title(self, candidate_title: Optional[str], expected_titles: List[str]) -> bool:
        if not candidate_title or not expected_titles:
            return False
        return equals_normalized_text(candidate_title, next((title for title in expected_titles if title), None))

    def _candidate_ai_technologies(self, candidate: Candidate) -> List[str]:
        raw_data = candidate.raw_data or {}
        ai_technologies: List[str] = []
        if isinstance(raw_data.get("ai_skills"), list):
            ai_technologies.extend([skill for skill in raw_data["ai_skills"] if isinstance(skill, str)])
        if isinstance(raw_data.get("skills"), list):
            ai_technologies.extend([skill for skill in raw_data["skills"] if isinstance(skill, str)])
        return deduplicate_preserve_order(ai_technologies)

    def _experience_summary(self, raw_data: Optional[dict], minimum_years: Optional[int], maximum_years: Optional[int]) -> tuple[Optional[str], Optional[str]]:
        years = None
        if isinstance(raw_data, dict):
            years = raw_data.get("years_experience")
        if years is None:
            return None, None
        text = f"{years} years"
        if minimum_years is not None and years < minimum_years:
            return f"Requires at least {minimum_years} years of experience", f"Requires at least {minimum_years} years of experience"
        if maximum_years is not None and years > maximum_years:
            return f"Requires at most {maximum_years} years of experience", f"Requires at most {maximum_years} years of experience"
        return text, None

    def _matches_location(
        self,
        candidate_location: Optional[str],
        countries: List[str],
        cities: List[str],
    ) -> bool:
        if not candidate_location:
            return False
        candidate_norm = normalize_text(candidate_location)
        if any(candidate_norm == normalize_text(country) for country in countries):
            return True
        return any(candidate_norm == normalize_text(city) for city in cities)

    def _matches_company(self, candidate_company: Optional[str], preferred_companies: List[str]) -> bool:
        if not candidate_company or not preferred_companies:
            return False
        candidate_norm = normalize_text(candidate_company)
        return any(candidate_norm == normalize_text(company) for company in preferred_companies)

    def _matches_experience(self, raw_data: Optional[dict], minimum_years: Optional[int], maximum_years: Optional[int]) -> bool:
        if minimum_years is None and maximum_years is None:
            return True
        years = None
        if isinstance(raw_data, dict):
            years = raw_data.get("years_experience")
        if years is None:
            return False
        if minimum_years is not None and years < minimum_years:
            return False
        if maximum_years is not None and years > maximum_years:
            return False
        return True

    def _build_potential_risks(
        self,
        title_match: bool,
        location_match: bool,
        company_match: bool,
        experience_match: bool,
        missing_skills: List[str],
        missing_experience: Optional[str],
    ) -> List[str]:
        if not experience_match and missing_experience:
            return ["Experience is below the requested range"]
        return []

    def _build_summary(
        self,
        title_match: bool,
        location_match: bool,
        company_match: bool,
        experience_match: bool,
        matched_required_skills: List[str],
        missing_required_skills: List[str],
        matched_preferred_skills: List[str],
    ) -> str:
        parts: List[str] = []
        if title_match:
            parts.append("title matches the requested role")
        else:
            parts.append("title does not clearly match the requested role")

        if location_match:
            parts.append("location aligns with the target geography")
        else:
            parts.append("location does not align with the target geography")

        if company_match:
            parts.append("company matches a preferred employer")
        else:
            parts.append("company is not in the preferred employer list")

        if experience_match:
            parts.append("experience satisfies the requested range")
        else:
            parts.append("experience does not satisfy the requested range")

        if matched_required_skills:
            parts.append(f"matched required skills: {', '.join(matched_required_skills)}")
        if missing_required_skills:
            parts.append(f"missing required skills: {', '.join(missing_required_skills)}")
        if matched_preferred_skills:
            parts.append(f"matched preferred skills: {', '.join(matched_preferred_skills)}")

        return "; ".join(parts)

