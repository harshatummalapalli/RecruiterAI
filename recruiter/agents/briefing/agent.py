"""Agent 2 — Briefing. RoleModel -> CrustData query + honest disclosures.

Every candidate filter is routed through the SAME capability model Intake used,
so we only ever enforce what CrustData can actually enforce; anything else is
disclosed (recorded, shown to the recruiter) or handed to the Judge — never
faked as a filter.
"""

from __future__ import annotations

from typing import Any, List, Tuple

from recruiter.agents.briefing.model import BriefingPlan, ProviderQuery
from recruiter.agents.briefing.query import build_nl_query
from recruiter.providers import capability_model as cap
from recruiter.role_model import RoleModel

_ENFORCEABLE = {cap.ENFORCE, cap.ENFORCE_WITH_WARNING, cap.ENFORCE_NOT_VERIFIABLE}


class BriefingAgent:
    def build(self, model: RoleModel) -> BriefingPlan:
        enforced: dict[str, Any] = {}
        disclosures: List[str] = list(model.limitations)

        def consider(filter_name: str, value: Any) -> None:
            if not value:
                return
            routing = cap.route_filter(filter_name)
            if routing in _ENFORCEABLE:
                enforced[filter_name] = value
            elif routing == cap.DISCLOSE:
                disclosures.append(f"'{filter_name}' cannot be filtered on CrustData — recorded only.")
            # JUDGE / CONTEXT -> not a hard filter; handled via judge_signals / the NL query.

        consider("countries", tuple(model.location.countries))
        consider("states", tuple(model.location.states))
        consider("cities", tuple(model.location.cities))
        consider("minimum_years", model.seniority.min_years)
        consider("maximum_years", model.seniority.max_years)
        consider("exclude_titles", tuple(model.exclude_titles))
        consider("exclude_current_companies", tuple(model.companies.exclude_current))
        consider("preferred_companies_ever", tuple(model.companies.prefer_ever))
        consider("industries", tuple(model.industries))

        # Radius (geo_distance) — a location hard filter, enforced when anchored.
        if model.location.radius_place and model.location.radius_miles and cap.route_filter("radius_place") in _ENFORCEABLE:
            enforced["radius_place"] = model.location.radius_place
            enforced["radius_miles"] = model.location.radius_miles

        # Employment type — enforce only a CrustData-recognised value; an
        # unrecognised one silently returns zero rows, so disclose instead.
        if model.employment_type:
            normalized = cap.normalize_employment_type(model.employment_type)
            if normalized and cap.route_filter("employment_type") in _ENFORCEABLE:
                enforced["employment_type"] = normalized
            else:
                disclosures.append(
                    f"Employment type '{model.employment_type}' isn't a filterable CrustData value — recorded only."
                )

        groups: Tuple[Tuple[str, ...], ...] = tuple(tuple(g.terms) for g in model.capability_groups if g.terms)
        if groups and cap.route_filter("must_have_keyword_groups") in _ENFORCEABLE:
            enforced["must_have_keyword_groups"] = groups

        query = ProviderQuery(
            natural_language=build_nl_query(model),
            countries=enforced.get("countries", ()),
            states=enforced.get("states", ()),
            cities=enforced.get("cities", ()),
            min_years=enforced.get("minimum_years"),
            max_years=enforced.get("maximum_years"),
            radius_place=enforced.get("radius_place"),
            radius_miles=enforced.get("radius_miles"),
            employment_type=enforced.get("employment_type"),
            exclude_titles=enforced.get("exclude_titles", ()),
            exclude_current_companies=enforced.get("exclude_current_companies", ()),
            preferred_companies_ever=enforced.get("preferred_companies_ever", ()),
            must_have_keyword_groups=enforced.get("must_have_keyword_groups", ()),
            industries=enforced.get("industries", ()),
        )
        # De-dupe disclosures, preserve order.
        seen: set = set()
        unique = tuple(d for d in disclosures if not (d in seen or seen.add(d)))
        return BriefingPlan(query=query, disclosures=unique, judge_signals=model.requirements)
