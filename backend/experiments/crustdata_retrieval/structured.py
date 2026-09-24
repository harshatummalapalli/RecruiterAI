"""Strategy B for the NL-vs-structured retrieval experiment: the SAME
confirmed hiring intent expressed ONLY in CrustData's verified structured
filter language. Experiment code; nothing in production imports this module.

What "structured" means here, precisely:
- the filters production already emits and has verified live (location,
  geo_distance radius, years of experience, current title, exclusions, company
  filters, employment type) - built by the production CrustDataProvider payload
  builder, so no filter can be emitted that production could not emit;
- NO `search` (natural-language) clause;
- NO title synonym expansion (backend/knowledge/titles.json is deliberately
  NOT applied), NO LLM, NO skills/technology filters - skills are not a
  filterable or returned field on this account;
- every requirement the filter language cannot express is listed explicitly as
  a `structured_unrepresented_requirement`, never silently dropped."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

from backend.api import CRUSTDATA_SUPPORTED_FILTERS
from backend.models.provider_capabilities import ProviderCapabilities
from backend.models.search_intent import SearchIntent
from backend.models.search_plan import SearchPlan, SearchQuery
from backend.providers.crustdata import CrustDataProvider, SUPPORTED_EMPLOYMENT_TYPES
from backend.services.capability_mapper import CapabilityMapper
from backend.services.search_planner import SearchPlanner

# Every CrustData field a payload from either strategy may filter on. This is
# the verified boundary; a test fails if a payload ever contains anything else.
VERIFIED_FILTER_FIELDS: Set[str] = {
    "basic_profile.location.country",
    "basic_profile.location.state",
    "basic_profile.location.city",
    "basic_profile.location",  # geo_distance
    "experience.employment_details.current.title",
    "experience.employment_details.current.company_name",
    "experience.employment_details.current.company_type",
    "experience.employment_details.current.employment_type",
    "experience.employment_details.company_name",
    "years_of_experience_raw",
    "basic_profile.name",  # the provider's no-condition placeholder filter
}


@dataclass
class StructuredPlan:
    query: SearchQuery
    payload: Dict[str, Any]
    unrepresented: List[Dict[str, str]] = field(default_factory=list)
    dropped_by_capability_mapper: List[str] = field(default_factory=list)


def build_structured_plan(intent: SearchIntent, provider: CrustDataProvider) -> StructuredPlan:
    """Deterministic: the same intent always yields the same payload."""
    planned = SearchPlanner().build(intent)
    title_queries = [q for q in planned.searches if q.query_name == "title_expansion"]
    if not title_queries:
        raise ValueError("The intent has no role title, so no structured title filter can be built.")
    # The planner's supplementary query is exactly "shared filters + current-title
    # OR of [role title + confirmed include_titles]" with no NL clause. It is used
    # as-is; the query expander (title synonyms) is intentionally NOT run.
    structured = title_queries[0].model_copy(update={"query_name": "structured"})
    mapped, dropped = CapabilityMapper().map(
        SearchPlan(searches=[structured]), ProviderCapabilities(supported_filters=CRUSTDATA_SUPPORTED_FILTERS)
    )
    query = mapped.searches[0]
    payload = provider._build_payload(query, options={"page_size": 50})
    return StructuredPlan(
        query=query,
        payload=payload,
        unrepresented=unrepresented_requirements(intent, query),
        dropped_by_capability_mapper=dropped,
    )


def build_nl_plan(intent: SearchIntent, provider: CrustDataProvider) -> Dict[str, Any]:
    """Strategy A exactly as production builds it: planner -> query expander ->
    capability mapper, first (natural_language) query, first page of 50."""
    from backend.services.query_expansion import QueryExpansionService

    planned = SearchPlanner().build(intent)
    expanded = QueryExpansionService().expand(planned)
    mapped, dropped = CapabilityMapper().map(expanded, ProviderCapabilities(supported_filters=CRUSTDATA_SUPPORTED_FILTERS))
    query = [q for q in mapped.searches if q.query_name == "natural_language"][0]
    return {"query": query, "payload": provider._build_payload(query, options={"page_size": 50}), "dropped_by_capability_mapper": dropped}


def unrepresented_requirements(intent: SearchIntent, query: SearchQuery) -> List[Dict[str, str]]:
    """Everything in the confirmed intent that the emitted structured payload
    does NOT enforce, with the reason."""
    out: List[Dict[str, str]] = []

    def add(kind: str, text: str, reason: str) -> None:
        out.append({"kind": kind, "requirement": text, "reason": reason})

    for tier, signals in (
        ("core", intent.core_signals),
        ("supporting", intent.supporting_signals),
        ("differentiator", intent.differentiator_signals),
    ):
        for text in signals:
            add(f"{tier}_signal", text, "skills, technologies, domain and experience-of-kind are not filterable fields on this account")
    if intent.role.seniority:
        add("seniority", intent.role.seniority, "no verified seniority filter; only the title text and the years-of-experience floor can carry it")
    if intent.location.work_mode:
        add("work_mode", intent.location.work_mode, "work mode is not a People Search filter")
    if intent.location.zip_codes:
        add("zip_codes", ", ".join(intent.location.zip_codes), "ZIP code is not a People Search filter")
    if intent.role.employment_type and intent.role.employment_type.strip().lower() not in SUPPORTED_EMPLOYMENT_TYPES:
        add("employment_type", intent.role.employment_type, f"value not in the verified vocabulary {sorted(SUPPORTED_EMPLOYMENT_TYPES)}")
    for skill in list(intent.skills.required_skills) + list(intent.skills.preferred_skills):
        add("skill", skill, "skills are not a returned or filterable field on this account")
    if intent.titles.include_titles == [] and intent.role.title:
        add("title_variants", "any title other than the role title itself", "no synonym expansion is permitted in the structured strategy")
    return out


def payload_fields(payload: Dict[str, Any]) -> Set[str]:
    """Every filter field named anywhere in a CrustData payload."""
    found: Set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "field" in node:
                found.add(node["field"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload.get("filters", {}))
    return found
