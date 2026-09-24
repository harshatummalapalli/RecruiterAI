"""Field catalog for the CrustData Structured Search Playground.

SOURCES (nothing here is invented):
- The list of filterable columns is CrustData's own `get_schema(person_search, detailed)` "Filterable columns"
  list for /person/search, read on 2026-09-24 (plus the docs' Searchable-fields tables at
  docs.crustdata.com/person-docs/search/reference for types and closed value sets).
- Operators come from the docs' "Filter operator reference" table.
- `verified_in_our_account` comes ONLY from RecruiterAI's own live evidence (production searches, EXP-001, the
  capability findings recorded in backend/providers/crustdata.py) - see VERIFIED / UNAVAILABLE below.
  Everything else is "documented_unverified".

Requested categories that CrustData does NOT document as In-Database People Search filters (news mentions,
company overview, company-level keyword) are listed in NOT_DOCUMENTED_IN_PEOPLE_SEARCH and are deliberately not
turned into fields."""

from typing import Any, Dict, List, Optional

STATUS_VERIFIED = "verified"
STATUS_UNVERIFIED = "documented_unverified"
STATUS_UNAVAILABLE = "unavailable"

SCHEMA_SOURCE = "Crustdata get_schema(person_search, detailed) filterable columns, 2026-09-24"
DOCS_SOURCE = "docs.crustdata.com/person-docs/search/reference"

_EMPLOYER_SUFFIXES = [
    "name", "company_name", "title", "description", "company_id", "professional_network_id", "is_default", "position_id",
    "seniority_level", "start_date", "company_website_domain", "company_professional_network_industry",
    "company_linkedin_profile_url", "company_headcount_range", "company_headcount_latest", "company_industries",
    "company_type", "company_status", "company_headquarters_country", "company_hq_location", "function_category",
    "years_at_company_raw",
]
_ALL_ROLES_SUFFIXES = [
    "company_name", "company_id", "professional_network_id", "title", "description", "location", "start_date", "end_date",
    "seniority_level", "function_category", "company_website_domain", "company_headcount_latest", "company_headcount_range",
    "company_industries", "company_professional_network_industry", "company_type", "company_status",
    "company_headquarters_country", "company_hq_location", "years_at_company_raw", "employment_type", "is_default",
    "company_website", "business_email_verified",
]
_TENSE_EXTRAS = ["business_email_verified", "company_professional_network_profile_url", "employment_type"]

_DEV = [
    "name", "bio", "location", "location.raw", "website_url", "company_text", "is_hireable", "followers", "following",
    "public_repo_count", "metadata.created_at", "total_repos", "total_stars", "max_stars", "median_stars", "all_languages",
    "all_topics", "repos.full_name", "repos.owner", "repos.is_fork", "repos.description", "repos.primary_language",
    "repos.topics", "repos.license_key", "repos.archived", "repos.disabled", "repos.is_template", "repos.has_issues",
    "repos.has_projects", "repos.has_wiki", "repos.stars", "repos.forks_count", "repos.open_issues_count", "repos.size",
    "repos.github_created_at", "repos.github_updated_at", "repos.github_pushed_at",
]


def _paths() -> List[str]:
    p: List[str] = [
        "crustdata_person_id",
        "basic_profile.name", "basic_profile.first_name", "basic_profile.last_name", "basic_profile.headline",
        "basic_profile.summary", "basic_profile.languages", "basic_profile.last_updated", "basic_profile.location",
        "basic_profile.location.full_location", "basic_profile.location.city", "basic_profile.location.state",
        "basic_profile.location.country", "basic_profile.location.continent",
        "basic_profile.normalized_title.matched_title", "basic_profile.normalized_title.department",
        "basic_profile.normalized_title.sub_department",
        "professional_network.connections", "professional_network.followers", "professional_network.open_to_cards",
        "professional_network.location", "professional_network.location.raw", "professional_network.location.city",
        "professional_network.location.state", "professional_network.location.country",
        "professional_network.location.continent", "professional_network.metadata.last_scraped_source",
        "skills.professional_network_skills",
        "recently_changed_jobs", "years_of_experience_raw", "years_of_experience",
    ]
    p += [f"experience.employment_details.{s}" for s in _ALL_ROLES_SUFFIXES]
    for tense in ("current", "past"):
        p += [f"experience.employment_details.{tense}.{s}" for s in _EMPLOYER_SUFFIXES + _TENSE_EXTRAS]
    p += [
        "education.schools.school", "education.schools.degree", "education.schools.field_of_study",
        "education.schools.location", "education.schools.location.city", "education.schools.location.state",
        "education.schools.location.country", "education.schools.location.continent",
        "education.schools.location.full_location", "education.schools.location.raw",
        "certifications.name", "certifications.issue_date", "certifications.expiration_date", "certifications.credential_url",
        "certifications.issuing_organization", "certifications.credential_id", "honors.title",
        "social_handles.twitter_handle",
        "metadata.updated_at", "metadata.last_scraped_source",
        "assessment.authenticity.tier", "assessment.authenticity.verdict",
    ]
    p += [f"dev_platform_profiles.{s}" for s in _DEV]
    return p


DOCUMENTED_PATHS: List[str] = _paths()

# --- value types ------------------------------------------------------------------------------------------------------
_BOOLEAN = {
    "basic_profile.normalized_title.confident", "dev_platform_profiles.is_hireable", "recently_changed_jobs",
    "dev_platform_profiles.repos.archived", "dev_platform_profiles.repos.disabled", "dev_platform_profiles.repos.has_issues",
    "dev_platform_profiles.repos.has_projects", "dev_platform_profiles.repos.has_wiki", "dev_platform_profiles.repos.is_fork",
    "dev_platform_profiles.repos.is_template",
}
_INTEGER = {
    "crustdata_person_id", "professional_network.connections", "professional_network.followers",
    "dev_platform_profiles.followers", "dev_platform_profiles.following", "dev_platform_profiles.public_repo_count",
    "dev_platform_profiles.total_repos", "dev_platform_profiles.total_stars", "dev_platform_profiles.max_stars",
    "dev_platform_profiles.median_stars", "dev_platform_profiles.repos.stars", "dev_platform_profiles.repos.forks_count",
    "dev_platform_profiles.repos.open_issues_count", "dev_platform_profiles.repos.size",
}
_NUMBER = {"years_of_experience_raw"}
_DATE = {"certifications.issue_date", "certifications.expiration_date"}
_DATETIME = {
    "metadata.updated_at", "basic_profile.last_updated", "dev_platform_profiles.metadata.created_at",
    "dev_platform_profiles.repos.github_created_at", "dev_platform_profiles.repos.github_updated_at",
    "dev_platform_profiles.repos.github_pushed_at",
}
_STRING_ARRAY = {
    "basic_profile.languages", "professional_network.open_to_cards", "skills.professional_network_skills",
    "dev_platform_profiles.all_languages", "dev_platform_profiles.all_topics", "dev_platform_profiles.repos.topics",
}

# Closed value sets published in the docs ("Closed value sets" table). Employer paths all share the first four.
CLOSED_SETS: Dict[str, List[str]] = {
    "seniority_level": ["Entry Level", "Entry Level Manager", "Senior", "Director", "Owner / Partner", "CXO", "Vice President",
                        "In Training", "Experienced Manager", "Strategic"],
    "function_category": ["Engineering", "Sales", "Consulting", "Marketing", "Operations", "Finance", "Research",
                          "Customer Success and Support", "Arts and Design", "Human Resources", "Legal", "Product Management"],
    "company_headcount_range": ["myself only", "2-10", "11-50", "51-200", "201-500", "501-1000", "1001-5000", "5001-10000", "10001+"],
    "company_status": ["active", "deleted"],
}
OPEN_TO_CARDS = ["CAREER_INTEREST", "HIRING_MANAGER", "VOLUNTEERING"]

# --- operators (docs "Filter operator reference") --------------------------------------------------------------------
OPERATORS: Dict[str, Dict[str, Any]] = {
    "=": {"shape": "scalar", "meaning": "Exact match against the whole stored value (case-insensitive phrase match on free text)"},
    "!=": {"shape": "scalar", "meaning": "Not equal"},
    "<": {"shape": "scalar", "meaning": "Less than (number or date)"},
    "=<": {"shape": "scalar", "meaning": "Less than or equal (NOT <=)"},
    ">": {"shape": "scalar", "meaning": "Greater than"},
    "=>": {"shape": "scalar", "meaning": "Greater than or equal (NOT >=)"},
    "in": {"shape": "array", "meaning": "Whole stored value is in the list (exact stored spelling)"},
    "not_in": {"shape": "array", "meaning": "Value is not in the list"},
    "is_null": {"shape": "null", "meaning": "Field has no value"},
    "is_not_null": {"shape": "null", "meaning": "Field has at least one non-null value"},
    "has_all": {"shape": "array", "meaning": "Each listed value is matched by some nested-array element (nested-array fields only)"},
    "(.)": {"shape": "scalar", "meaning": "Case-insensitive all-words match, any order, no typo tolerance"},
    "(!)": {"shape": "scalar", "meaning": "Fuzzy negation: excludes substring matches"},
    "[.]": {"shape": "scalar", "meaning": "Case-insensitive exact-phrase match (contiguous, in order)"},
    "geo_distance": {"shape": "geo", "meaning": "Within a radius of a location or coordinate"},
    "geo_exclude": {"shape": "geo", "meaning": "Outside a radius of a location or coordinate"},
}
NEGATIVE_OPERATORS = {"!=", "not_in", "(!)", "geo_exclude"}   # not allowed inside all_of / has_all
GROUP_OPS = ("and", "or", "all_of")

_TEXT_OPS = ["=", "!=", "in", "not_in", "(.)", "(!)", "[.]", "is_null", "is_not_null"]
_NUM_OPS = ["=", "!=", "<", "=<", ">", "=>", "is_null", "is_not_null"]
_BOOL_OPS = ["=", "!=", "is_null", "is_not_null"]
_GEO_FIELDS = {"basic_profile.location", "basic_profile.location.full_location", "professional_network.location", "professional_network.location.raw"}

NESTED_ARRAY_PREFIXES = ("experience.employment_details", "education.schools", "certifications", "honors")

# --- evidence about OUR account -------------------------------------------------------------------------------------
# field -> (operators actually exercised, evidence)
VERIFIED: Dict[str, Any] = {
    "basic_profile.location.country": (["in"], "Production searches and EXP-001 (all five roles filter on it)"),
    "basic_profile.location.state": (["in"], "Production Toronto/Ontario searches"),
    "basic_profile.location.city": (["in"], "Production Toronto/Hyderabad searches and EXP-001"),
    "basic_profile.location": (["geo_distance"], "Production radius search around Toronto, 25 mi (geo_distance takes a place name, not a ZIP)"),
    "experience.employment_details.current.title": (["(.)", "(!)"], "Production NL and structured payloads and EXP-001. Earlier live tests: `in`/`not_in`/`!=` are exact-string only and let compound titles through"),
    "experience.employment_details.past.title": ([], "Earlier CrustData capability experiments (recorded by the project owner; operators not recorded)"),
    "years_of_experience_raw": (["=>", "=<"], "Production searches and EXP-001 (the filter works; the field itself is not returned on our plan)"),
    "experience.employment_details.current.company_name": (["not_in"], "Production searches excluding the hiring company (EXP-001 cyber role)"),
    "basic_profile.name": (["(.)"], "Used by the provider as its no-condition placeholder filter"),
}
UNAVAILABLE: Dict[str, str] = {
    "years_of_experience": "Filtering silently drops the threshold (CrustData returns the is-not-null set for ANY value) and the field is plan-gated in responses on our account. Use years_of_experience_raw.",
    "skills.professional_network_skills": "The `skills` response field is plan-gated on our account (a request that names it is a 403 with denied_fields, verified in earlier experiments). Filtering on it has not been verified, so a query using it may return nothing useful and results can never show skills.",
}
# Response fields the plan withholds (get_schema note; the tool truncated the list at 30 of 30).
RESPONSE_GATED_PREFIXES = (
    "certifications.", "honors.", "recently_changed_jobs", "skills.", "years_of_experience", "basic_profile.first_name",
    "basic_profile.last_name", "basic_profile.languages", "basic_profile.summary", "professional_network.connections",
    "professional_network.followers",
)
# Things the project asked about that have no People Search field at all.
UNSUPPORTED_REQUESTS: List[Dict[str, str]] = [
    {"name": "zip_code", "display_name": "ZIP / postal code", "verified_in_our_account": STATUS_UNAVAILABLE,
     "source": "RecruiterAI capability findings", "notes": "CrustData People Search has no ZIP field. geo_distance takes a place name (a ZIP string is geocoded as text), never a postal filter."},
    {"name": "work_mode", "display_name": "Work mode (remote / hybrid / onsite)", "verified_in_our_account": STATUS_UNAVAILABLE,
     "source": "RecruiterAI capability findings", "notes": "Work mode exists only on job search, not People Search."},
]
NOT_DOCUMENTED_IN_PEOPLE_SEARCH: List[Dict[str, str]] = [
    {"name": "mentioned_in_news", "display_name": "Mentioned in news", "notes": "No such People Search field is documented. (News is a web_search_live capability, a different product.)"},
    {"name": "company_keyword", "display_name": "Company-level keyword", "notes": "Not a People Search field; company keyword search belongs to company_search."},
    {"name": "company_overview", "display_name": "Company overview", "notes": "Not a People Search field; company text belongs to company_search."},
]


_ROLE_LEAVES = {
    "title", "description", "seniority_level", "start_date", "end_date", "function_category", "is_default", "position_id",
    "employment_type", "years_at_company_raw", "business_email_verified", "location",
}


def _category(path: str) -> Dict[str, str]:
    leaf = path.rsplit(".", 1)[-1]
    sub = "Role" if leaf in _ROLE_LEAVES else "Company"
    if path.startswith("experience.employment_details.current."):
        return {"category": "CURRENT EMPLOYMENT", "subcategory": sub}
    if path.startswith("experience.employment_details.past."):
        return {"category": "PAST EMPLOYMENT", "subcategory": sub}
    if path.startswith("experience.employment_details."):
        return {"category": "ANY EMPLOYMENT (all roles)", "subcategory": sub}
    if path.startswith("education."):
        return {"category": "EDUCATION", "subcategory": ""}
    if path.startswith(("certifications.", "honors.")):
        return {"category": "CERTIFICATIONS & HONORS", "subcategory": ""}
    if path.startswith("dev_platform_profiles."):
        return {"category": "DEVELOPER PLATFORM", "subcategory": ""}
    if path.startswith(("metadata.", "assessment.")) or path == "crustdata_person_id":
        return {"category": "IDENTITY, METADATA & ASSESSMENT", "subcategory": ""}
    if path.startswith(("skills.", "recently_changed_jobs", "years_of_experience", "basic_profile.normalized_title.")):
        return {"category": "PROFESSIONAL", "subcategory": ""}
    if path.startswith("professional_network."):
        return {"category": "PROFESSIONAL NETWORK", "subcategory": ""}
    return {"category": "PERSON", "subcategory": ""}


def _value_type(path: str) -> str:
    if path in _BOOLEAN or path.endswith("business_email_verified") or path.endswith("is_default"):
        return "boolean"
    if path in _INTEGER or path.endswith(("company_id", "company_headcount_latest")):
        return "integer"
    if path in _NUMBER or path.endswith("years_at_company_raw"):
        return "number"
    if path in _DATE or path.endswith(("start_date", "end_date")):
        return "date"
    if path in _DATETIME:
        return "datetime"
    if path in _STRING_ARRAY or path.endswith("company_industries"):
        return "string[]"
    return "string"


def _closed_values(path: str) -> Optional[List[str]]:
    leaf = path.rsplit(".", 1)[-1]
    if path.startswith("experience.employment_details.") and leaf in CLOSED_SETS:
        return CLOSED_SETS[leaf]
    if path == "professional_network.open_to_cards":
        return OPEN_TO_CARDS
    return None


def nested_array_path(path: str) -> Optional[str]:
    """The nested-array path a field lives on (employment split by tense), or None for a scalar field."""
    for prefix in NESTED_ARRAY_PREFIXES:
        if path == prefix or path.startswith(prefix + "."):
            if prefix == "experience.employment_details":
                rest = path[len(prefix) + 1:]
                head = rest.split(".", 1)[0]
                return f"{prefix}.{head}" if head in ("current", "past") else prefix
            return prefix
    return None


def _operators(path: str, vtype: str) -> List[str]:
    if vtype in ("integer", "number", "date", "datetime"):
        ops = list(_NUM_OPS)
    elif vtype == "boolean":
        ops = list(_BOOL_OPS)
    else:
        ops = list(_TEXT_OPS)
    if path in _GEO_FIELDS:
        ops += ["geo_distance", "geo_exclude"]
    if nested_array_path(path) and vtype not in ("boolean",):
        ops.append("has_all")
    return ops


def _display(path: str) -> str:
    parts = path.split(".")
    if path.startswith("experience.employment_details."):
        parts = parts[2:]
        if parts and parts[0] in ("current", "past"):
            tense, parts = parts[0].capitalize(), parts[1:]
            return f"{tense} · " + " ".join(parts).replace("_", " ")
        return "Any role · " + " ".join(parts).replace("_", " ")
    return " · ".join(p.replace("_", " ") for p in parts)


def _build_entry(path: str) -> Dict[str, Any]:
    vtype = _value_type(path)
    entry: Dict[str, Any] = {
        "name": path,
        "display_name": _display(path),
        **_category(path),
        "provider_field": path,
        "supported_operators": _operators(path, vtype),
        "value_type": vtype,
        "multi_value": vtype == "string[]" or nested_array_path(path) is not None,
        "nested_array_path": nested_array_path(path),
        "allowed_values": _closed_values(path),
        "response_gated": path.startswith(RESPONSE_GATED_PREFIXES),
        "verified_operators": [],
        "source": SCHEMA_SOURCE + "; types/operators: " + DOCS_SOURCE,
    }
    notes: List[str] = []
    if path in VERIFIED:
        entry["verified_in_our_account"] = STATUS_VERIFIED
        entry["verified_operators"], evidence = VERIFIED[path]
        entry["source"] = evidence
    elif path in UNAVAILABLE:
        entry["verified_in_our_account"] = STATUS_UNAVAILABLE
        notes.append(UNAVAILABLE[path])
    else:
        entry["verified_in_our_account"] = STATUS_UNVERIFIED
    if entry["response_gated"] and path not in UNAVAILABLE:
        notes.append("Plan-gated RESPONSE field on our account: naming it in `fields` 403s the call. Filtering on it is a separate question and is unverified.")
    leaf = path.rsplit(".", 1)[-1]
    if path.endswith(("current.title", "past.title", "employment_details.title")):
        notes.append("Categorical column: `=`/`in` need the exact stored value (person_autocomplete). `(.)` and `[.]` match free text.")
    if path == "basic_profile.location.country":
        notes.append('Full country name, e.g. "United States".')
    if path == "basic_profile.location.state":
        notes.append('Full state/region name, e.g. "Ontario".')
    if leaf == "company_headquarters_country":
        notes.append('ISO 3166-1 alpha-3 code, e.g. "USA", "IND".')
    if leaf in ("company_website_domain",):
        notes.append('Bare domain, e.g. "stripe.com".')
    if path in _GEO_FIELDS:
        notes.append("geo_distance / geo_exclude take {location|lat_lng, distance, unit}; ZIP is not supported.")
    if path == "years_of_experience_raw":
        notes.append("Total years, numeric. Use => and =<, not >= / <=.")
    if entry["allowed_values"]:
        notes.append("Closed value set: a value outside the list matches nothing (400).")
    if entry["nested_array_path"]:
        notes.append("Nested-array field: an `and` group means the SAME role/entry; use `all_of` for different entries.")
    entry["notes"] = " ".join(notes)
    return entry


def build_catalog() -> List[Dict[str, Any]]:
    return [_build_entry(p) for p in DOCUMENTED_PATHS]


CATALOG: List[Dict[str, Any]] = build_catalog()
BY_NAME: Dict[str, Dict[str, Any]] = {e["name"]: e for e in CATALOG}


def catalog_payload() -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    for entry in CATALOG:
        counts[entry["verified_in_our_account"]] = counts.get(entry["verified_in_our_account"], 0) + 1
    return {
        "fields": CATALOG,
        "operators": OPERATORS,
        "group_ops": list(GROUP_OPS),
        "unsupported_requests": UNSUPPORTED_REQUESTS,
        "not_documented_in_people_search": NOT_DOCUMENTED_IN_PEOPLE_SEARCH,
        "counts": counts,
        "schema_source": SCHEMA_SOURCE,
    }
