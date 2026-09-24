# CrustData Structured Search Playground

An internal, local-only tool for building the exact Boolean / nested filter structure CrustData's In-Database
People Search understands, and optionally running that exact query. It is not part of the product: it is a separate
FastAPI app on `127.0.0.1:8765`, is never deployed, never touches the SearchStore, and changes nothing in search,
ranking, admission, Harvest, Candidate Review, Living Brief or Release 1 / 1.1. There is no LLM anywhere in it.

    python -m backend.experiments.structured_playground     # then open http://127.0.0.1:8765

## Two views

- `/` **Recruiter view** (default): a LinkedIn-style page. "+ Add filter" opens a searchable list (job title, city, company, seniority, years of experience, distance from a place, school...). Each filter is a card: type values and press Enter to make chips, choose Include or Exclude (NOT), "words in any order" or "exact phrase", and ANY of these (OR) or ALL of these (AND). Filters are joined by AND (or OR, your choice) and "+ Add a group ( ... )" gives brackets with their own ANY/ALL. The page reads the search back in plain notation ("Current job title: ("A" OR "B") AND City: "Toronto" AND ...") and labels each filter Tested / Not tested yet / Not available.
- `/advanced` **Advanced builder**: the operator-level view described below. "Open this search in the Advanced builder" carries the current search across.

The recruiter view adds no capability: each filter maps to one catalog field and operators the advanced builder already validates (`backend/experiments/structured_playground/simple.py`). Exclude on a text filter is `(!)`, on a list filter `not_in`; "at least/at most" is `=>`/`=<`; distance is `geo_distance`/`geo_exclude`.

## What it does

- **Field catalog**: 164 filterable People Search columns (CrustData `get_schema(person_search, detailed)`,
  2026-09-24, with types and closed value sets from the docs), grouped as PERSON, PROFESSIONAL, PROFESSIONAL
  NETWORK, CURRENT / PAST / ANY EMPLOYMENT (role vs company attributes), EDUCATION, CERTIFICATIONS & HONORS,
  DEVELOPER PLATFORM, IDENTITY/METADATA/ASSESSMENT. Each entry carries `name, display_name, category, provider_field,
  supported_operators, value_type, multi_value, verified_in_our_account, source, notes` (plus nested-array path,
  closed values, response-gated flag, verified operators).
- **Account status (colour)**:
  - Green, verified (9): country/state/city, `basic_profile.location` (geo_distance), current title, past title,
    `years_of_experience_raw`, current company name, `basic_profile.name`. Evidence: production searches, EXP-001,
    earlier capability experiments.
  - Yellow, documented but not yet verified (153): everything else. Some are also plan-gated *response* fields
    (shown as "response gated"): you can filter on them but never see them in results.
  - Red, unavailable (2): `years_of_experience` (filter silently drops its threshold; use `_raw`) and
    `skills.professional_network_skills` (skills is response-gated on our plan; filtering unverified).
  - Requested but not a People Search filter at all, shown in a separate red/grey list and not selectable: ZIP,
    work mode (red); "mentioned in news", company overview, company keyword (not documented for People Search,
    so not invented as fields).
- **Manual values**: used exactly as typed. No synonyms, spelling correction, trimming, case change or title
  expansion. The only transformation is the JSON type a field requires (a number field gets a number). Leading /
  trailing whitespace and closed-set mismatches are flagged, never fixed.
- **Boolean grouping**: `AND`, `OR` and `ALL OF` groups nested to any depth (CrustData documents no depth limit;
  none is imposed). Several values in one row are joined with OR (default), AND or ALL OF. Operators follow the docs
  (`=>` and `=<`, never `>=`/`<=`; `(.)` all-words, `[.]` exact phrase, `(!)` fuzzy negation, `in`, `not_in`,
  `is_null`, `has_all`, `geo_distance`, `geo_exclude`).
- **Validation** (errors block a run, warnings never change the query): unknown field or operator; empty group;
  `all_of` only on nested-array fields (employment, education, certifications, honors), one array path, positive
  operators only, no `all_of`/`has_all` inside `all_of`; a note that an `and` over one nested field means the same
  entry; Boolean text inside a value is flagged (CrustData matches values literally and answers 400).
- **Run**: one request, no retries, no `search` clause; body is exactly `filters` + `limit` (1-50) + `fields`.
  Shows provider order (1..N), `total_count` labelled as provider-reported universe, cursor presence and envelope
  keys. Estimated cost ~0.03 credits per result, confirmed before sending. A query using a red field needs a second
  confirmation. Each run is saved under `output/experiments/structured_playground/runs/` (gitignored).

## Safety

Loopback only; every request needs the per-launch token embedded in the page, so another web page cannot make your
browser spend credits.

## Not built

Importing an existing `filters` JSON back into the tree; the account-side Autocomplete lookups (closed sets are
taken from the docs). Neither was requested.
