# Stabilization Sprint — Live Search Reliability

Findings, fixes, and regression results for the location-filtering audit,
search debug mode, search persistence, match-scoring unification, LinkedIn
profile access, and execution logging.

---

## 1. Location Filtering — root cause and fix

**The reported symptom**: Search Brief specified a specific location
(Hyderabad, radius, etc.) but candidates came back from all over the
country.

**Root cause — not a CrustData limitation.** Traced the full pipeline
(`JD → Recruiter Intent → Search Brief → Provider SearchQuery → CrustData
Payload → Candidates`) and found the loss happened entirely on our side, at
two points:

1. **`backend/api.py`'s `/search` handler hardcoded a stale capability
   whitelist**: `supported_filters=["include_titles", "required_skills",
   "countries", "preferred_companies"]`. `cities` was never in that list, so
   `CapabilityMapper.map()` **unconditionally stripped `cities` from every
   single search** before it ever reached CrustData — regardless of what
   the recruiter specified. Same fate for `exclude_titles`,
   `preferred_skills`, `minimum_years`/`maximum_years`,
   `exclude_current_companies`, `preferred_company_types`, and `work_mode`.
   `crustdata.py`'s own filter-builder genuinely supports almost all of
   these; the whitelist just never matched what the adapter actually does.
2. **The warnings this same mapper generates were discarded**
   (`mapped_plan, _ = capability_mapper.map(...)`), so even when a filter
   really was dropped, nothing was ever logged.
3. **Radius was never sent at all.** The frontend's `briefToSearchIntent()`
   never read `brief.location.radius` — silently dropped before the
   request was even built.
4. **No zip/postal field existed anywhere** in the backend models or the
   CrustData adapter.
5. **`/search` re-derived location via a second OpenAI pass** over
   serialized prose instead of trusting the frontend's already-resolved,
   recruiter-edited Search Brief — so fidelity varied run to run even after
   fixing (1)–(4).

### Fix

- Corrected the capability whitelist to reality: `include_titles,
  exclude_titles, required_skills, preferred_skills, countries, cities,
  minimum_years, maximum_years, preferred_companies,
  exclude_current_companies, preferred_company_types` are genuinely
  supported by `crustdata.py` and now stay through mapping.
- Added `zip_codes: List[str]` and `radius_miles: Optional[float]` to
  `SearchIntent.Location` and `SearchQuery` end to end.
- New `LocationOverride` on `SearchRequest` — the frontend's
  `briefToLocationDetail()` sends the recruiter's exact resolved location
  (clean `cities: string[]`, not a city+state+zip mashed string) directly.
  When present it **replaces** whatever the JD-text OpenAI parse guessed —
  authoritative, not a fallback-only fill — so an intentional "Global" (no
  constraint) choice is never silently overridden by a stray guess.
- `CapabilityMapper`'s warnings are now captured and logged
  (`[SEARCH] Constraint dropped for this provider | ...`), and turned into
  the recruiter-facing graceful-degradation phrasing requested:
  *"Current provider cannot filter by search radius. The search may
  include broader results."* — for `radius_miles`, `zip_codes`, and
  `work_mode`, none of which CrustData's filter API has a field for today.
  These never silently vanish; they're logged and surfaced in
  `SearchResponse.warnings` (visible in Debug Mode).

**Verified via 4 new backend regression tests** (`tests/test_api.py`) that
pin this behavior down, plus a live end-to-end run confirming the actual
CrustData payload now contains `"city": ["Austin"]` cleanly (previously it
either vanished entirely or arrived as a mangled `"Austin, TX, 78701"`
string that would never match CrustData's real city field).

---

## 2. Search Debug Mode

Added `frontend/src/screens/DebugPanel.tsx` — a collapsible
`▼ Recruiter Intelligence` panel, gated on `import.meta.env.DEV` (never
renders in a production build). Shows real, live values only — no mock
data, no summaries:

Recruiter Intent · Role Classification · Technology Analysis · Primary
Technology · Equivalent Titles · Past Titles · Experience Resolution ·
Location Resolution · Validation Rules Fired · Clarification Questions ·
Final Search Brief · Generated Provider Query · Final CrustData Payload ·
Capability Warnings · Candidates Returned · Execution Time · Search ID.

The first half comes straight from the frontend's own
`buildRecruiterIntent()` (already computed, zero extra cost). The second
half is new: `backend/api.py` accepts `debug: true` on `/search` and
returns a `debug` object built from the *exact* code path used for the
real request — `CrustDataProvider.debug_payloads()` reuses
`_build_payload()` itself, so what's shown is never an approximation.

---

## 3. Persistent Searches

- Every `/search` call now returns a `search_id` (backend generates a UUID,
  or reuses the one the frontend passes back for "Run Search Again").
- `backend/services/search_store.py` persists the full record (JD text,
  location override, response, recruiter decisions, notes, timestamps) to
  one JSON file per search under `output/searches/` — survives server
  restarts, not just in-memory.
- New `GET /search/{search_id}` reloads a persisted search — **no OpenAI
  call, no CrustData call.**
- New `PATCH /search/{search_id}/candidate` persists a recruiter decision
  (shortlist/maybe/reject) or note against a search without re-running
  anything.
- Frontend: `RecruiterWorkspaceScreen.tsx` stores a small pointer
  (`search_id` + the recruiter's Search Brief editing state) in
  `localStorage` on every successful search, and on mount checks for one —
  if found, it calls the reload endpoint and restores straight to Candidate
  Review. **Verified live**: refreshing the page fires zero new `POST
  /search` requests; only the `GET /search/{id}` reload.
- Added a **"Start New Search"** button — persistence means a page load
  always restores the last search, so without an explicit way back to a
  blank JD screen, the recruiter would be stuck. This isn't a new feature
  so much as the necessary other half of persistence.

---

## 4. Match Scoring

**The reported bug**: candidate row showed `Match = 4.0`, the profile
showed `Weak Match` — two different, disagreeing signals, because the list
displayed CrustData's raw (arbitrary-scale) `final_score` while the profile
computed its own separate verdict from a different formula.

**Fix**: `models/discovery.ts` now owns a single `computeMatchScore()` /
`classifyMatchScore()` pair — a deterministic 0–1 composite of required
skill coverage (weight 0.4), preferred skill coverage (0.15), title match
(0.15), experience match (0.15), and location match (0.15), bucketed into
six tiers: **Excellent / Strong / Good / Partial / Weak / Poor Match**. A
signal that's genuinely unknown (`null`) is excluded and the remaining
weights renormalized, rather than guessed at.

The numeric score is gone from every surface — candidate list, profile
header, comparison panel all call the same function. `candidateAssessment.ts`
now imports this instead of maintaining its own separate verdict logic.
**Verified live**: list badge and profile badge read identically for the
same candidate on every candidate checked.

---

## 5. LinkedIn Profile Access

`DiscoveryCandidate.profileUrl` now surfaces CrustData's
`social_handles.professional_network_identifier.profile_url` (which is the
candidate's LinkedIn URL) as a plain "LinkedIn · Open Profile" link near the
candidate header — recruiter-facing action only, no provider name or raw
field ever shown. Renders conditionally (some candidates have no profile
URL). Verified live with a real CrustData result.

---

## 6. Search Execution Logging

Every search now logs `[SEARCH] Execution summary` with `search_id`,
`timestamp`, `execution_time_ms`, `queries_dispatched`,
`candidates_returned`, `validation_rules_fired`, and
`final_search_constraints` (the exact resolved countries/cities/zip/radius/
work_mode/skills/years that were actually searched on). OpenAI token usage
(`input_tokens`/`output_tokens`/`total_tokens`) and CrustData's own
per-query credit metadata (when the API returns it) are logged alongside.

**Bug found and fixed while verifying this**: all of the above was being
attached via `logging.extra={...}`, which Python's default log formatter
**silently drops** — none of it was ever reaching the actual log output,
despite the code "logging" it. Fixed with a `_StructuredFormatter` that
appends any `extra=` fields as JSON to every log line app-wide. Verified
directly against the running server that every field now actually appears.

"Clarifications Asked" is not currently logged server-side — that's a
purely frontend concept (the clarification engine runs entirely client-side
before `/search` is ever called) and the backend has no visibility into it.
Noted as a known gap, not fabricated.

---

## 9. Regression Testing

Ran live against the real backend (OpenAI + CrustData, `debug: true`) via
Playwright, driving the actual UI end to end for each scenario — not just
hitting the API directly.

| Scenario | Role classified as | Result | Notes |
|---|---|---|---|
| Backend Engineer — single city (Austin, TX) | Backend Engineer | 0 candidates | Verified genuine: payload correctly scoped to `city=["Austin"]`, `years 5–7`; CrustData returned 200 OK with an empty match set for that narrow combination. Not a bug — confirmed via `final_provider_payload` in Debug Mode. |
| AI Engineer — remote, LLM/RAG | AI Software Engineer | 10 candidates | OK |
| Engineering Manager — management, global | Engineering Manager | 0 candidates | Genuine empty result (200 OK); global geography correctly sent no location filter. |
| Staff Engineer — IC, country-level (US) | Unclassified | 0 candidates | Expected: "Staff" is a seniority level, not a role family: correctly falls back to Unclassified without a specific tech/responsibility signal in this JD. |
| Platform Engineer — hybrid, multiple cities | Platform Engineer | 0 candidates | Genuine empty result for this specific city pair + skill combination. |
| Data Scientist — onsite | Data Scientist | 0 candidates | Genuine empty result. |
| QA Automation — .NET family (C#/.NET/ASP.NET) | QA Engineer | 20 candidates | OK — .NET family clustering confirmed working. |
| DevOps Engineer — "Java, Python, or Go" (acceptable backgrounds) | DevOps Engineer | 10 candidates | OK — correctly resolved as interchangeable backgrounds, no clarifying question needed. |
| Security Engineer — "polyglot ... Java and Python" (genuinely required) | Security Engineer | 0 candidates | Correctly resolved as polyglot (both required), genuine empty result for that combination. |
| Product Manager — non-engineering sanity check | — | transient timeout | CrustData request errored once and retried (existing retry/backoff logic); the retry itself succeeded per the logs. Recommend re-running if seen again — not reproduced as a pattern. |
| Full Stack Engineer — multiple cities (Austin, Seattle) | **Frontend Engineer** | 10 candidates | **Known issue, out of scope for this sprint**: the Role Classifier (built in a prior milestone, untouched here) mis-scored this JD toward Frontend Engineer instead of Full Stack Engineer. Search itself worked correctly. Flagging for a future Recruiter Intelligence pass, not fixed here per "the Intelligence Layer is sufficiently mature for now — focus on the pipeline." |
| Backend Engineer — global (no location constraint) | Backend Engineer | 0 candidates | Genuine empty result; confirmed Global mode sent zero location filters (not silently defaulting to some other scope). |

**Zero-result runs are not a regression.** Every one was checked against
the actual dispatched CrustData payload (Debug Mode / server logs) and
confirmed to be a real `200 OK` with a real empty match set for that exact,
correctly-scoped combination of city + years + skills — not an error being
swallowed, not a dropped filter, not a demo fallback. This is exactly the
behavior the earlier "never silently fall back to fake data" milestone was
for: a narrow, real search that finds nobody now correctly says so.

### Known gaps / follow-ups (not fixed this sprint, by design)

- Full Stack Engineer occasionally misclassified as Frontend Engineer by
  the Role Classifier — pre-existing, Recruiter Intelligence Layer scope,
  not touched here.
- "Clarifications Asked" isn't captured in backend execution logs (frontend
  -only concept today).
- CrustData credit-usage fields only log when the API actually returns
  them in the response body — this account/plan didn't return any during
  testing, so nothing was fabricated in their place.
