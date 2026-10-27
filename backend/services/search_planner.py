import re
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

# When the ROLE being hired for is itself a management/executive role, the
# blanket EXECUTIVE_TITLE_EXCLUSIONS must NOT fire — excluding Director/VP/
# C-level there would strip exactly the people the recruiter wants. Matched
# (word-boundary, case-insensitive) against the role title AND the target
# seniority. Recruiter-stated exclude_titles are always honored regardless;
# only the blanket default list is made conditional. Deliberately includes
# "manager" per product decision (a Manager/Director/C-level search keeps
# those titles eligible).
_LEADERSHIP_ROLE_MARKERS: List[str] = [
    "manager", "director", "managing director", "vp", "vice president", "svp", "evp",
    "chief", "c-level", "c-suite", "cxo", "ceo", "cto", "cio", "cfo", "coo", "cpo",
    "cmo", "cro", "caio", "cdo", "head of", "president", "founder", "executive",
]
_LEADERSHIP_ROLE_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(m) for m in _LEADERSHIP_ROLE_MARKERS) + r")\b", re.IGNORECASE
)


def _is_leadership_role(intent: SearchIntent) -> bool:
    """True when the role being hired for is a management/executive role, so
    the blanket executive-title exclusions should be suppressed for it."""
    text = " ".join(part for part in (intent.role.title, intent.role.seniority) if part)
    return bool(_LEADERSHIP_ROLE_PATTERN.search(text))


class SearchPlanner:
    """Build the two-query V0.1 discovery plan from a canonical SearchIntent:
    a primary, relevance-ranked natural-language query (no title filter —
    verified live to be the strongest single discovery mechanism, and the
    only one that reliably surfaces candidates whose current title doesn't
    match the role), plus a supplementary, conservative title-expansion query
    used only to widen the candidate pool. This intentionally replaces the
    old one-query-per-title-variant fan-out."""

    def build(self, intent: SearchIntent) -> SearchPlan:
        # Executive-title exclusions are ON by default, but suppressed when the
        # ROLE itself targets Manager/Director/C-level (otherwise we would drop
        # the very candidates being sought). Recruiter-stated exclude_titles are
        # always applied either way.
        default_exclusions = [] if _is_leadership_role(intent) else EXECUTIVE_TITLE_EXCLUSIONS
        exclude_titles = deduplicate_preserve_order([
            *[title for title in intent.titles.exclude_titles if title],
            *default_exclusions,
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
        non-intake JD-parse path) are still appended after, unchanged.

        Whichever sentence we start from, it is then AUGMENTED (see
        _augment_query) so the defining capabilities and the confirmed location
        are always present in the text. This is load-bearing for retrieval:
        CrustData's hybrid `search` was observed to stop enforcing the hard
        filters (location included) when the query is generic and does not name
        the location — a specific, location-naming query makes every filter
        bind. It also guarantees a core/supporting capability (e.g. RAG) that
        the LLM happened to omit from its sentence still reaches retrieval."""
        if intent.natural_language_search_query:
            base = intent.natural_language_search_query
        else:
            parts: List[str] = []
            fallback = _fallback_natural_language_query(
                intent.role.title or "",
                intent.role.seniority,
                intent.core_signals,
                intent.supporting_signals,
                intent.differentiator_signals,
            )
            if fallback:
                parts.append(fallback)

            required = [skill for skill in intent.skills.required_skills if skill]
            if required:
                parts.append(f"with required experience in {', '.join(required)}")

            preferred = [skill for skill in intent.skills.preferred_skills if skill]
            if preferred:
                parts.append(f"experience in {', '.join(preferred)} is valuable but not mandatory")

            base = ". ".join(parts)

        return self._augment_query(base, intent)

    def _augment_query(self, base: str, intent: SearchIntent) -> str:
        """Ensure the natural-language query names the confirmed location and
        the defining (core/supporting) capabilities. Idempotent: a term already
        present in the sentence (case-insensitive) is never re-added, so a good
        LLM query is left essentially untouched. Pure-experience signals (a
        years statement already enforced by the structured experience filter)
        are not injected as capabilities."""
        query = (base or "").strip()
        low = query.lower()

        def _is_capability(signal: str) -> bool:
            s = signal.strip().lower()
            return bool(s) and "year" not in s  # years are an experience filter, not a search term

        def _missing(signals: List[str]) -> List[str]:
            out: List[str] = []
            for signal in signals or []:
                if _is_capability(signal) and signal.strip().lower() not in low:
                    out.append(signal.strip())
            return deduplicate_preserve_order(out)

        additions: List[str] = []
        missing_core = _missing(intent.core_signals)
        if missing_core:
            additions.append(f"with strong experience in {', '.join(missing_core)}")
            low = (low + " " + " ".join(missing_core)).lower()

        missing_supporting = _missing(intent.supporting_signals)
        if missing_supporting:
            additions.append(f"experience with {', '.join(missing_supporting)}")

        location = self._location_phrase(intent)
        if location and location.lower() not in (query + " " + " ".join(additions)).lower():
            additions.append(f"based in {location}")

        pieces = [piece for piece in [query.rstrip(" .")] + additions if piece]
        result = ". ".join(pieces).strip()
        if result and not result.endswith("."):
            result += "."
        return result

    def _location_phrase(self, intent: SearchIntent) -> str:
        """A compact, human place name for the NL query, preferring the most
        specific confirmed scope (city, then state, then country, then an
        explicit radius anchor)."""
        location = intent.location
        city = location.cities[0] if location.cities else None
        state = location.states[0] if location.states else None
        specific = ", ".join(part for part in (city, state) if part)
        if specific:
            return specific
        if location.countries:
            return location.countries[0]
        return location.radius_place or ""

    def _build_title_variants(self, intent: SearchIntent) -> List[str]:
        titles: List[str] = []
        role_title = intent.role.title or ""
        include_titles = [title for title in intent.titles.include_titles if title]

        if role_title:
            titles.append(role_title)
        titles.extend(include_titles)

        return deduplicate_preserve_order(titles)
