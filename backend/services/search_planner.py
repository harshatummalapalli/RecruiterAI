from typing import List

from backend.models.search_intent import SearchIntent
from backend.models.search_plan import SearchPlan, SearchQuery
from backend.services.search_translator import _fallback_natural_language_query
from backend.utils.text import deduplicate_preserve_order

# Standing product policy (Part 7 of the V0.1 discovery architecture): current
# leadership/executive titles are excluded from every discovery query by
# default, regardless of what the recruiter's Search Brief does or doesn't
# say. This targets CURRENT title only — a candidate's past Founder/CTO/
# Director history never disqualifies them (see crustdata.py, which scopes
# the exclusion to experience.employment_details.current.title). Deliberately
# conservative: bare "Principal"/"Staff"/"Lead"/"Engineering Manager" are
# NOT excluded, since those are legitimate senior IC or team-lead titles.
EXECUTIVE_TITLE_EXCLUSIONS: List[str] = [
    "Founder",
    "Co-Founder",
    "CEO",
    "Co-CEO",
    "Chief Executive Officer",
    "CTO",
    "Chief Technology Officer",
    "CIO",
    "Chief Information Officer",
    "CPO",
    "Chief Product Officer",
    "CAIO",
    "Chief AI Officer",
    "Chief Data Officer",
    "VP",
    "Vice President",
    "SVP",
    "EVP",
    "Director",
    "Managing Director",
    "Head of Engineering",
    "Head of Technology",
    "Head of Product",
    "Head of Data",
    "Head of AI",
    "Head of ML",
]


class SearchPlanner:
    """Build the two-query V0.1 discovery plan from a canonical SearchIntent:
    a primary, relevance-ranked natural-language query (no title filter —
    verified live to be the strongest single discovery mechanism, and the
    only one that reliably surfaces candidates whose current title doesn't
    match the role), plus a supplementary, conservative title-expansion query
    used only to widen the candidate pool. This intentionally replaces the
    old one-query-per-title-variant fan-out."""

    def build(self, intent: SearchIntent) -> SearchPlan:
        exclude_titles = deduplicate_preserve_order([
            *[title for title in intent.titles.exclude_titles if title],
            *EXECUTIVE_TITLE_EXCLUSIONS,
        ])

        shared_fields = dict(
            exclude_titles=exclude_titles,
            countries=intent.location.countries,
            states=intent.location.states,
            cities=intent.location.cities,
            # zip_codes has no CrustData filter field at all — carried
            # through only so CapabilityMapper's existing drop-and-warn
            # mechanism fires (Part 15: never silently drop an unsupported
            # filter). It is never used to build a request.
            zip_codes=intent.location.zip_codes,
            radius_place=intent.location.radius_place,
            radius_miles=intent.location.radius_miles,
            radius_unit=intent.location.radius_unit,
            # work_mode has no CrustData filter field on person_search (it
            # exists only on job_search) — carried through for the same
            # drop-and-warn reason as zip_codes, never used to build a request.
            work_mode=intent.location.work_mode,
            employment_type=intent.role.employment_type,
            minimum_years=intent.experience.minimum_years,
            maximum_years=intent.experience.maximum_years,
            preferred_companies=intent.previous_background.preferred_companies,
            exclude_current_companies=intent.company_preferences.exclude_current_companies,
            preferred_company_types=intent.company_preferences.preferred_company_types,
        )

        queries: List[SearchQuery] = [
            SearchQuery(
                query_name="natural_language",
                natural_language_query=self._natural_language_query(intent),
                required_skills=intent.skills.required_skills,
                preferred_skills=intent.skills.preferred_skills,
                **shared_fields,
            )
        ]

        title_variants = self._build_title_variants(intent)
        if title_variants:
            queries.append(
                SearchQuery(
                    query_name="title_expansion",
                    include_titles=title_variants,
                    **shared_fields,
                )
            )

        return SearchPlan(
            searches=queries,
            strategy="primary_natural_language_plus_title_expansion",
            reasoning=(
                "Primary relevance-ranked natural-language discovery query, "
                "supplemented by a conservative title-expansion query used "
                "only to widen the candidate pool."
            ),
            confidence_score=intent.confidence_score,
        )

    def _natural_language_query(self, intent: SearchIntent) -> str:
        """Prefer the LLM-authored query (the canonical interpreter of hiring
        intent — see prompts/system.txt). Falls back to a deterministic
        template built only from fields the recruiter/LLM actually populated,
        for non-LLM callers (tests, a missing/empty LLM field) — this
        fallback never invents a requirement that isn't already present on
        the intent.

        The confirmed-intake path's requirements live in
        core_signals/supporting_signals/differentiator_signals, never in
        skills.required_skills/preferred_skills (search_translator.py never
        populates those for that path — see the audit that found this). This
        used to build a query from role+seniority+skills only, so whenever the
        caller had no sentence of its own (e.g. RECRUITERAI_SEND_CONFIRMED_
        SEARCH_SENTENCE=false blanks it before this runs), every confirmed
        core/supporting/differentiator requirement was silently dropped —
        the query planner reused the SAME tier-weighted template
        search_translator._fallback_natural_language_query already builds
        from those fields at confirmation time, so nothing is lost just
        because a different module ended up needing to build the sentence.
        required_skills/preferred_skills (populated only by the older,
        non-intake JD-parse path) are still appended after, unchanged."""
        if intent.natural_language_search_query:
            return intent.natural_language_search_query

        parts: List[str] = []
        base = _fallback_natural_language_query(
            intent.role.title or "",
            intent.role.seniority,
            intent.core_signals,
            intent.supporting_signals,
            intent.differentiator_signals,
        )
        if base:
            parts.append(base)

        required = [skill for skill in intent.skills.required_skills if skill]
        if required:
            parts.append(f"with required experience in {', '.join(required)}")

        preferred = [skill for skill in intent.skills.preferred_skills if skill]
        if preferred:
            parts.append(f"experience in {', '.join(preferred)} is valuable but not mandatory")

        return ". ".join(parts)

    def _build_title_variants(self, intent: SearchIntent) -> List[str]:
        titles: List[str] = []
        role_title = intent.role.title or ""
        include_titles = [title for title in intent.titles.include_titles if title]

        if role_title:
            titles.append(role_title)
        titles.extend(include_titles)

        return deduplicate_preserve_order(titles)
