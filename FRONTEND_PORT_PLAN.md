# Port Plan — Serve the OCI React Frontend from the New Engine

**Goal:** make the existing `frontend/` React app the production surface, powered by
the new `recruiter/` engine. Swap the *brain* behind `backend/api.py`'s routes;
keep every piece of infra. Retire the minimal `recruiter/web` HTML as a dev harness.

**Principle:** the frontend and the OCI infra (auth, credits, persistence, workspace,
export, canonical typeaheads) were always the keepers. The audit's target — the
overlapping intake/search/ranking "brain" — is the only thing we replace.

---

## 1. Keep / Replace / Translate — inventory

### Keep as-is (infra, engine-agnostic)
- **Auth + credits** — `backend/auth.py`, `/auth/*`, `/credits`, `require_session`/`require_admin`.
- **Persistence + workspace** — `search_store`, `confirmation_store`, `/searches`,
  `/search/{id}/workspace|candidate|role|more`, recruiter decisions/notes.
- **Export** — `/export`, `backend/exporters/excel.py`.
- **`candidate_evidence_builder`** — raw CrustData/Harvest → `CandidateEvidence`; reuse
  to populate `SearchResponse.evidence`.
- **FastAPI shell** — app wiring, `_raise_recruiter_friendly_error`, error envelope
  (`detail.errors` / `detail.reasons` the frontend's `readRefusal` already parses).
- **Frontend infra** — `AppShell`, `AuthGate`, `CreditMeter`, `SearchSidebar`,
  `CandidateWorkspace`/`CandidateRecord`, `LocationTypeahead`/`LocationMultiTypeahead`.

### Replace (the brain → `recruiter/` engine)
`jd_parser`, `intake_reasoning`/`intake_session`/`intake_answer`, the confirmation
builders (`build_snapshot`, `build_confirmed_hiring_intent`, `to_search_intent`,
`search_intent_from_snapshot`), `search_planner`, `query_expander`, `capability_mapper`,
`search_compiler(_shadow)`, `search_pipeline`, `admission`, `candidate_ranker`,
`match_explainer`, `geo_enforcement`, `role_defining_capability`, `role_family_taxonomy`,
`structured_intent_extractor`, `search_translator`, `search_availability`,
`compiler_audit`, `search_diagnostics`.

### Translate (the seam — the real work)
A new module `backend/bridge/` (name TBD) mapping **new-engine objects ⇆ frontend
contract shapes**. One file per direction; pure, unit-tested offline.

---

## 2. Route-by-route mapping

| Route | Today → | New impl |
|---|---|---|
| `POST /parse-jd` | `jd_parser.parse` → `SearchIntent` | new intake reader → `Understanding` → `to_search_intent_shape()` |
| `POST /intake/start` | `intake_session_manager.start` → `{session_id, result, boundary}` | `pipeline.read_intent` + `prepare_review` → `to_result_shape(model, review)`; store `RoleModel` in a session store |
| `POST /intake/{id}/answer` | `intake_session_manager.answer` | re-run `assemble` with the answer merged → `to_result_shape` |
| `GET /intake/{id}` | resume (read-only) | return stored `RoleModel` → `to_result_shape` |
| `PATCH /intake/{id}/boundary` | `update_boundary` (deterministic) | re-run `assemble` with the new boundary (no model call) — **our `assemble` already does exactly this** |
| `POST /intake/{id}/confirmations` | `build_snapshot` → `confirmation_store.create` | `apply_answers`(edits) → `authorize` → store the confirmed `RoleModel` (its `model_id`) as the snapshot; return `brief_summary` shape |
| `POST /intake/{id}/preview` | legacy payload debug | `pipeline.preview` (count + `admin_query`) — already built |
| `POST /search` {confirmation_id} | `search_pipeline` | load confirmed `RoleModel` by id → `pipeline.execute` → `to_search_response()` |
| `GET /search/{id}`, `/more`, `/workspace`, `/candidate`, `/role`, `/searches`, `/export` | search_store | **keep** (store the new `SearchResponse` dicts) |

**Gate stays identical:** `/search` runs only from a stored confirmation id; the browser
sends no intent. `confirmation_id` ≙ `RoleModel.model_id`.

---

## 3. The translation module — key shape mappings

### Boundary (frontend → engine) — already compatible
Frontend `SearchBoundary` = `hiring_company, country, work_mode, state, city,
radius_miles, cities, remote_scope, remote_states, remote_cities`. Our `_location`
already consumes all of these (radius anchors on `city`+`state`). **Additions needed
for the new filters:** `include_companies[]`, `exclude_companies[]`, `radius_unit`
(mi/km), and make `radius_place` derivable (it already is, from city+state).

### `result` (engine → frontend `RoleUnderstanding`) — the lossy seam
Map what the new engine produces; **trim the rest in the UI** (don't fabricate):

| Frontend field | New-engine source |
|---|---|
| `primary_candidate_identity` (`FieldValue`) | `model.identity` (+ provenance from `Requirement.provenance`) |
| `posted_title` / `posted_title_source` | `model.posted_title` / `..._source` |
| `explicit_constraints.{locations,work_mode,experience_min/max,employment_type,exclusions}` | `model.location`, `model.seniority`, `model.employment_type`, `model.exclude_titles`+`companies` |
| `core/supporting_capabilities` (`CapabilityItem`) | `model.tier("core"/"supporting")` + `capability_groups` |
| `technologies_mentioned` | `capability_groups` (label + terms) |
| `open_questions` / issues | `outcome.refinements` + `clarifications` → `IntakeIssue` (prompt/options; **drop** `consequence_*`, `insight_text`, archetype) |
| `candidate_archetype`, `role_interpretation`, `seniority_scope`, `leadership_type` | **no source → trim these UI sections** |

### `SearchResponse` (engine → frontend) — easy (loosely typed `List[Dict]`)
`candidates[]`, `explanations[]`, `evidence[]` built from `RankingResult.shown`
(`record` + `score` + `fit` + evidence) via the kept `candidate_evidence_builder`.
`diagnostics` from `SearchResult` (pulled/kept/geo/excluded/credits) + `RankingResult`
(admitted/judged/experience_excluded). `recruiter_decisions`/`notes`/workspace fields
stay owned by the kept persistence layer.

---

## 4. Frontend changes

### Rewire (not rebuild)
- **Typeaheads**: point `LocationTypeahead`/`MultiTypeahead`'s `search()` at
  `GET /api/autocomplete` (free CrustData `person_autocomplete`), canonical values.
  Country → State → City cascade.

### Trim (match the leaner model)
- Remove brief sections with no engine source: candidate archetype, role interpretation,
  seniority scope, leadership type, consequence-framed questions.

### The UX nits from review (small, in the React controls)
1. **Title** moves above JD.
2. **Work mode** beside Hiring company.
3. **Location scope** directly below Country.
4. **Country** = autocomplete dropdown (no free-typed single-letter errors).
5. **Specific cities** = canonical multi-tag typeahead cascaded on the chosen country.
6. **State** = required, full names (autocomplete), not optional, not short forms.
7. **Cities** = hard filter only; **remove soft "preferred cities"**.
8. **Radius** = place autocomplete + miles **and km** toggle.
9. **Companies** (include/exclude) = individual tags; backend treats include as **OR**
   (= `preferred_companies_ever`, "ever worked at any").

---

## 5. Sequencing

- **Phase 0 — Scaffold.** `backend/bridge/` module + a session store for the new
  `RoleModel`. No route changes yet. Offline tests for every mapping.
- **Phase 1 — Core flow behind existing auth+persistence.** Reimplement `/parse-jd`,
  `/intake/start`, `/intake/{id}/answer`, `PATCH /boundary`, `/intake/{id}/confirmations`,
  `/search` to call `recruiter.pipeline`. Keep auth, credits, `search_store`,
  `confirmation_store`. **Validate with ONE live role** end-to-end through the React app.
- **Phase 2 — Frontend rewire + trim.** Typeahead → our autocomplete; trim brief UI;
  apply the 9 UX nits; company tags.
- **Phase 3 — Workspace/searches/export** on the new result shape (mostly already works
  since persistence is kept).
- **Phase 4 — Cutover + cleanup.** Delete the brain services; delete `recruiter/web`
  (or keep as a dev harness); OCI cleanup for speed; this branch → `main`, delete others.

**Credit discipline:** every phase is offline-testable with injected fakes. The only
credit spend is the single Phase-1 live validation (plus free counts/autocomplete).

---

## 6. §6 unknowns — LOCKED (read of the OCI session/persistence/auth layer, 2026-10-31)

**Storage is file-JSON, no database.** `SearchStore` (`backend/services/search_store.py`)
is one atomic JSON file per id (temp-file + `os.replace`, RLock for read-modify-write).
The session, confirmation, and search stores are all the *same* `SearchStore` class at
different dirs (`output/intake_sessions`, `output/confirmations`, `output/searches`).

- **Session store — ✅ reuse directly.** Persist the new `RoleModel` via
  `dataclasses.asdict(model)` → `SearchStore.save` (it already serializes with
  `default=str`), and rebuild with a `role_model_from_dict()` helper (~30 lines, mirrors
  `intake_session._record_from_dict`, offline-tested). No DB, no migration. The new
  engine's session manager is a thin wrapper over `SearchStore` holding
  `{role_model, answers, boundary, posted_title}`.
- **Confirmation store — ✅ reuse directly.** Same `SearchStore` primitive; store the
  confirmed `RoleModel` keyed by `model_id`/content-hash. `/search` loads by id →
  `pipeline.execute`.
- **Search / workspace store — ✅ reuse as-is.** Store the new `SearchResponse` dicts;
  decisions/notes/workspace state stay owned by the kept layer.
- **Auth / tenancy — ✅ email identity, single allowed domain.** `get_session_email`
  returns the Google-SSO email; `check_domain_allowed` restricts sign-in to ONE
  `ALLOWED_EMAIL_DOMAIN` (e.g. `dayzero.partners`), and "all access is otherwise shared."
  So today it's effectively **single-org, shared data**. Wire
  `org = email.split("@")[-1]` → `IntakeAgent(org=...)` for per-org capability memory
  (single org now; per-domain if multi-tenant later). Admin surfaces stay gated to
  `SUPER_ADMIN_EMAIL`.
- **`candidate_evidence_builder` — ✅ compatible.** It reads the raw CrustData/Harvest
  profile; our `CandidateRecord.raw` already carries the raw CrustData `basic_profile`/
  `experience` (confirmed in the live runs). Harvest evidence is Phase 3.

### Residual risks (not blockers)
- **Brief UI coupling** — trimming the React brief sections (archetype / interpretation /
  seniority-scope / leadership-type / consequence-questions) to the leaner model is the
  largest frontend task. Decision: **trim, don't stub.**
- **Industry filter** — still routed-but-not-forwarded by the adapter; fold into Phase 2
  when the UI exposes the Industry tag.
- **Supabase later** — storage is file-JSON today; a Supabase migration is a *separate*
  later step. The port does **not** require it (reuse `SearchStore` now).
- **Shared (not per-user) data** — fine for a small team; per-user scoping is a later add
  if needed (key stores by email).

---

## 7. Definition of done
A recruiter signs in on the OCI React app, pastes a JD, picks canonical country/state/
city (or a radius in mi/km), sets min/max years and company include/exclude tags, sees
the pool-count preview, confirms, runs one live search, and gets ranked candidates in the
workspace — all served by the new engine, with the brain services deleted and the branch
promoted to `main`.
