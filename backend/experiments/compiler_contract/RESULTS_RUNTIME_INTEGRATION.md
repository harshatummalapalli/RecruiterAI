# RESULTS — Offline runtime integration (compiled plan → downstream context)

**All 10 acceptance gates are met, measured.** Compiler `v2-2026-10-07`. No CrustData, Harvest, retrieval, deployment or model call; no real candidate; no ranking, admission-threshold, prompt or Judge change.

```
BEFORE  compiler  →  provider filter tree + audit rows.            Everything else the compiler had decided (an exclusion, a proficiency, a work
                                                                    mode, a preference, a path) lived only in the compiler's own audit.
AFTER   compiler  →  explicit provider plan PER PATH
                  +  downstream execution context PER PATH:          one entry per intent atom, with its fate, provenance and tier
                  +  adapters for today's consumers + a recorded     (to_judge_signals; legacy_consumer_gaps)
                     list of what they cannot yet accept
                  +  a path-merge data contract                      (one record per candidate, every contributing path id, no path rank)
```

**What this phase did NOT do, by instruction:** no Judge, admission, ranking or pipeline change. The Judge and admission still read only the legacy `SearchIntent` / `intent.role`; the compiled plan and the contexts exist, are verified, and are not yet consumed. That is recorded below as LEGACY DOWNSTREAM CONSUMER with the exact interface changes needed (not made).

## What to distrust (read first)
1. **"Survives the boundary" is structural.** The contexts contain every atom with its fate, provenance and tier; nothing says a future Judge will use them well. This is not a relevance result.
2. **The provenance gate got stricter, on purpose, and has one behaviour you should know.** An intent that records provenance, compiled WITHOUT its source text, gets no title filter at all (every title is `absent`). The runtime must pass the JD / brief; the shadow audit does (JD only: the pipeline does not give it the brief). A legacy intent that records provenance nowhere keeps its old behaviour and the audit says `unrecorded`.
3. **Source classification is lexical.** A title or headcount is "stated" by the intake's own one-sentence word-share check; a comparison is detected by a generic English cue list ("more like", "similar to", "resembles", "akin to", "comparable to", "reminiscent of", "someone like", "like a"). A comparison phrased another way would be read as a target. It does not decide on role identity; it decides whether the SOURCE states a value as the thing to hire.
4. **The verifier and the audit tables are mine.** The 15 frozen intents, Roles 1-3, one model, five runs each; Role 2 is prompt_v3. Role 1 run 1 has an intake error (6+ years in the GLOBAL intent): its contexts show it inherited by both paths, faithfully.
5. **An explicit `current` the source does not support** (Role 2 prompt_v3: 32 skills) is still enforced as stated; an explicit meaning is never changed. That is an intake validation item.

## 1. Provenance hardening (generic)
Every intent field that can become a provider filter, its provenance carrier, and what the gate did over the 15 frozen intents (with each role's verbatim JD / brief supplied):

| hard-filter-capable field | provenance carrier | ENFORCED atoms by provenance state (15 intents; `*` = classified from the source text) | WITHHELD atoms by reason |
|---|---|---|---|
| `company` | `basis` | – | – |
| `company_scale` | none (production `CompanyScale`): the number must be stated in the source text | – | – |
| `education.degree` | `basis` | source×15 | – |
| `education.stream` | `basis` | source×45 | – |
| `exclusion.exclude_past_company` | `basis` | – | – |
| `exclusion.exclude_title` | `basis` | – | – |
| `experience.max` | `basis` | source×5 | – |
| `experience.min` | `basis` | source×15 | – |
| `location.country` | `basis` | source×5 | – |
| `location.entry` | `basis`; state / country also need to be in the quote | source×20 | – |
| `location.radius` | `basis` | – | – |
| `role_family` | none (a plain list of titles): classified from the source text (target / comparison / absent) | source*×20 | comparison×5 |
| `skill` | `basis` (quote verified against the source) | source×35 | – |
| `skill_any_of` | `basis` | – | – |

The rule, in one sentence: a hard filter needs `source` or `knowledge` provenance (or `unrecorded` in a legacy intent); `model_only`, `absent`, `comparison` and `unverified_quote` are withheld with a fate and a reason (`COMPILER_CONTRACT.md` section 4, `RUNTIME_INTEGRATION_CONTRACT.md` section 1). No value of Role 1, 2 or 3 is named in the compiler, the classifier, the context builder or the merge module (a test scans them).

Titles, per role (run 1):

| role (run 1) | each role_family title → its provenance state | titles in the provider filter |
|---|---|---|
| R1 | Data Analyst → source | Data Analyst |
| R2 | Forward Deployed Engineer → comparison, Software Engineer → source, Solution Architect → source | Backend Developer, Backend Engineer, Python Developer, Software Engineer, Solution Architect |
| R3 | FP&A and Business Finance Manager → source | FP&A and Business Finance Manager |

Provider leaves, contract-1 compiler (no source text) vs now (with source text). The gate withheld exactly one leaf per Role 2 run and nothing else:

| intent | contract-1 leaves | now (with source text) | withheld | added |
|---|---|---|---|---|
| R1/1 | 13 | 13 | – | – |
| R1/2 | 4 | 4 | – | – |
| R1/3 | 4 | 4 | – | – |
| R1/4 | 4 | 4 | – | – |
| R1/5 | 4 | 4 | – | – |
| R2/1 | 44 | 43 | title "Forward Deployed Engineer" | – |
| R2/2 | 44 | 43 | title "Forward Deployed Engineer" | – |
| R2/3 | 29 | 28 | title "Forward Deployed Engineer" | – |
| R2/4 | 17 | 16 | title "Forward Deployed Engineer" | – |
| R2/5 | 32 | 31 | title "Forward Deployed Engineer" | – |
| R3/1 | 11 | 11 | – | – |
| R3/2 | 11 | 11 | – | – |
| R3/3 | 11 | 11 | – | – |
| R3/4 | 11 | 11 | – | – |
| R3/5 | 11 | 11 | – | – |

## 2. Analogy safety
Role 2's brief says "...more like a Forward Deployed Engineer who understands the client requirements". Every sentence that states that title introduces it with a comparison cue, so it is classified `comparison`: it is withheld from the title filter in 5/5 runs and kept as an `UNRESOLVED` entry with the quote. `Software Engineer` and `Solution Architect` (stated as the role, in the JD title) stay targets. The same mechanism handles eight generic cues on an invented title ("Quantum Plumber"), a title that is a target in one place and compared elsewhere (stays a target), and a title never stated (`absent`). Without the source text, no title of a provenance-carrying intent reaches a filter at all. Nothing is Role-2-specific.

## 3. Relationship migration audit
Every production reader and writer of a relationship, after the default changed from `current` to unspecified:

| consumer | lines reading / writing a relationship | role and migration status |
|---|---|---|
| `backend/models/structured_intent.py` | 4 | DEFINITION. `SkillReq`, `SkillAnyOf`, `CompanyScale`: default `None` (unspecified, never current); `CompanyReq`: default `any`. Validator accepts `None` or current / past / any |
| `backend/services/downstream_context.py` | 1 | CARRIER. Copies the atom's relationship (None stays None) into every entry |
| `backend/services/search_compiler.py` | 15 | CONSUMER. `current` / `past` → provider fields; `any` → downstream; `None` → downstream with capability `unspecified_relationship` (no current-role filter); company scale: `== "current"` only |
| `backend/services/structured_intent_extractor.py` | 6 | WRITER. `_fix_strength_relationship` repairs a strength word in the slot to `any`; group-collapse keeps an ABSENT relationship absent. Never writes `current` |
| `backend/experiments/intake_strategy/*` (gold, validators, compare: 7 files) | 17 | READERS (experiments). Equality comparisons (`== "current"`, `!= "any"`, `Counter`); all None-safe; the frozen stored intents state every relationship explicitly (0 of 343 atoms omitted it) |
| `prompts/structured_intent.txt` | 6 | PROMPT. Lists `current\|past\|any`; has no 'unspecified' option, so an omitted value (now `None`) is the model's only way to say unspecified. Not changed |
| `frontend/**` | 0 | no reader |

- Explicit `current`, `past`, `any` keep their meaning through the JSON model, the compiler, the atom audit, the context and the Judge adapter (parametrized tests). An unspecified relationship stays `None` in each layer, is never enforced, and is told apart from an explicit `current` by `intent_hash`.
- The old default is NOT restored. A test pins the exact set of production files that read a relationship and fails on any `relationship or "current"` / `.get("relationship", "current")` style default, so a new consumer must be reviewed.
- `requirement_semantics.py` has its own `scope = "current" | "career"`; it is derived from the requirement's text, not from `SkillReq.relationship`, and is unaffected.

## 4. Path contract (Role 1)
Each path has its own `DownstreamContext`; a global atom is inherited into each path's context (marked `inherited`), a path atom appears only in its own. Role 1, runs 1-5:

| intent | path | strategy | that path's provider plan | 6+ years | Power Query (tier, scope) | Power Query depth | remote | inherited entries | path-specific entries |
|---|---|---|---|---|---|---|---|---|---|
| R1/1 | PATH A | domain_led | country ["India"]; description Python; description SQL; headline Python; headline SQL; summary Python; summary SQL; title Data Analyst; years_of_experience_raw 6 | yes | absent | – | allowed / PREFERENCE_CONTEXT | 42 | 10 |
| R1/1 | PATH B | capability_led | city ["Hyderabad", "Pune"]; description Power Query; description Python; description SQL; headline Power Query; headline Python; headline SQL; summary Power Query; summary Python; summary SQL; title Data Analyst; years_of_experience_raw 6 | yes | core (path:PATH B) | working knowledge of Power Query | – | 42 | 8 |
| R1/2 | PATH A | domain_led | country ["India"]; title Data Analyst | no | absent | – | allowed / PREFERENCE_CONTEXT | 43 | 9 |
| R1/2 | PATH B | capability_led | city ["Hyderabad", "Pune"]; title Data Analyst; years_of_experience_raw 6 | yes | core (path:PATH B) | working knowledge of Power Query | – | 43 | 9 |
| R1/3 | PATH A | domain_led | country ["India"]; title Data Analyst | no | absent | – | allowed / PREFERENCE_CONTEXT | 40 | 10 |
| R1/3 | PATH B | capability_led | city ["Hyderabad", "Pune"]; title Data Analyst; years_of_experience_raw 6 | yes | core (path:PATH B) | working knowledge of Power Query | – | 43 | 6 |
| R1/4 | PATH A | domain_led | country ["India"]; title Data Analyst | no | supporting (path:PATH A) | working knowledge of Power Query | allowed / PREFERENCE_CONTEXT | 40 | 11 |
| R1/4 | PATH B | capability_led | city ["Hyderabad", "Pune"]; title Data Analyst; years_of_experience_raw 6 | yes | core (path:PATH B) | working knowledge of Power Query | – | 40 | 9 |
| R1/5 | PATH A | domain_led | country ["India"]; title Data Analyst | no | absent | – | allowed / PREFERENCE_CONTEXT | 39 | 11 |
| R1/5 | PATH B | capability_led | city ["Hyderabad", "Pune"]; title Data Analyst; years_of_experience_raw 6 | yes | core (path:PATH B) | working knowledge of Power Query | – | 39 | 9 |

Runs 2-5 satisfy every requested property: **Path A** is India (country filter) with remote acceptable (`PREFERENCE_CONTEXT`, an allowance), domain-led, no 6+ years, Power Query absent or only a `supporting` preference (waived); **Path B** is Hyderabad / Pune, 6+ years, Power Query `core` with `working_knowledge`, capability-led. No path atom appears in another path's context (0 leaks over 15 intents). Run 1 shows 6+ years on Path A too: the intake put it in the global intent, and the context says so (`scope: global`, `inherited`).

## 5. Downstream evidence contract
Every `VERIFIED_DOWNSTREAM` atom is an explicit entry (`judge_requirement`, `judge_exclusion` or `admission`) in each context it applies to. Where each concept lands, over the 15 intents (entries counted once per context):

| intent concept | context entry kinds (entries over all contexts of the 15 intents) |
|---|---|
| `semantic_exclusion` | judge_exclusion×35 |
| `skill.proficiency` | judge_requirement×159, preference×1 |
| `location.work_mode` | unresolved×5 |
| `seniority.leadership` | judge_requirement×12, preference×10 |
| `seniority.alternatives` | preference×5 |
| `seniority.value` | admission×6, preference×5, unresolved×4 |
| `domain` | preference×52, judge_requirement×21 |
| `location.remote` | preference×5 |
| `location.country` | provider_enforced×5 |
| `location.entry` | provider_enforced×20 |
| `company` | preference×30 |
| `education.degree` | provider_enforced×15, preference×10 |
| `experience.min` | provider_enforced×16 |
| `evidence_signal` | judge_requirement×256, preference×100 |
| `skill` | judge_requirement×265, preference×39, provider_enforced×37 |
| `skill_any_of` | judge_requirement×20 |
| `role_family` | provider_enforced×25, unresolved×5 |
| `reconciliation` | record×43 |
| `role_archetype` | record×20 |

- **Semantic exclusions** reach the context as `judge_exclusion` (negatives): 35 entries, never a company / title filter, and never mixed into the positive Judge signals.
- **Proficiency** arrives verbatim: `advanced proficiency in Microsoft Excel`, `working knowledge of Power Query`, `hands-on SQL`.
- **Work mode** arrives as `unresolved` with its typed value (`hybrid`) and the reason (no provider filter, not verifiable from the profile): visible, never remapped, never part of geography (`location` keeps `entry` / `country` and `work_mode` apart).
- **Leadership kinds, domain, alternatives** arrive as requirement / preference entries with their tier.
- **Provenance** (`state`, `sources`, `quote`) travels with every entry. **Unresolved** items (an unknown level, a work mode, a withheld title) stay visible in every context they apply to.

**DOWNSTREAM CONTRACT GAPS.** Some entries have no slot in the interface the current consumers accept. They stay in the context and are listed by `legacy_consumer_gaps` (atoms over the 15 intents):

| legacy-consumer gap (atoms; 5 runs per role) | Role 1 | Role 2 | Role 3 |
|---|---|---|---|
| NO_NEGATIVE_SLOT | 30 | 0 | 5 |
| NO_UNRESOLVED_SLOT | 0 | 5 | 9 |
| ADMISSION_READS_LEGACY_INTENT | 5 | 0 | 1 |
| PREFERENCE_NOT_FORWARDED | 85 | 0 | 30 |

`NO_NEGATIVE_SLOT`: the Judge cannot be told a candidate must NOT have a profile. `NO_UNRESOLVED_SLOT`: nothing can carry an unresolved item. `ADMISSION_READS_LEGACY_INTENT`: the compiled level is not what admission reads. `PREFERENCE_NOT_FORWARDED`: a preference kept as context reaches no signal or ranking input. Structurally, SearchIntent signals are bare strings (`NO_PROVENANCE_FIELD`) and one SearchIntent is one search (`NO_PATH_CONTEXT`).

## 6. Preference contract
Preferences survive as preferences: never required, never provider filters, no invented ranking or boost (no entry, context or merged record has a score, rank, weight or boost field).

| PREFERENCE_CONTEXT entries by concept (all contexts of the 15 intents) | entries |
|---|---|
| `evidence_signal` | 100 |
| `education.stream` | 60 |
| `domain` | 52 |
| `skill` | 39 |
| `company` | 30 |
| `seniority.leadership` | 10 |
| `education.degree` | 10 |
| `location.remote` | 5 |
| `seniority.value` | 5 |
| `seniority.alternatives` | 5 |
| `skill.proficiency` | 1 |
| **preferred / context atoms that became provider filters** | 0 |

Role 3's six named companies are `preference` entries (strength `preferred`) in 5/5 runs and appear in no provider leaf and no `core` Judge signal; Role 1's preferred domain and Role 2's context domain are preferences; preferred education and preferred skills are preferences.

## 7. Synthetic end-to-end and path merge
`tests/test_runtime_integration.py::test_S_*` runs Roles 1-3 through compile → context with invented candidates (no real data) while trapping every network connection, and proves: A path-specific requirements stay path-specific; B the downstream context sees semantic exclusions; C it sees proficiency; D it sees work mode; E preferences stay preferences; F unresolved taxonomy stays unresolved (`Senior Manager`); G provenance survives; H no flattening (the two Role 1 contexts differ exactly where the paths differ); I nothing is scored or ranked.

**Merge contract** (`path_merge.merge_path_results`, data contract only; nothing is merged live): identity is the pipeline's existing deduplication key; a candidate returned by Path A and Path B becomes ONE record with `contributing_path_ids = (PATH A, PATH B)`, each path's own unmodified payload (no score merged or chosen), and each path's own context entries as separate obligations; a candidate with no identity key is kept and flagged; the output is sorted by identity and is independent of the order the paths are given; no path is ranked above another and there is no path score.

## 8. Judge / admission consumer analysis (LEGACY DOWNSTREAM CONSUMER)
| consumer | reads today | does not read |
|---|---|---|
| `RequirementJudge` | `SearchIntent.core_signals` / `supporting_signals` / `differentiator_signals` (strings) | the compiled plan, a path, an exclusion, provenance, proficiency (except as text), work mode, unresolved items |
| `candidate_evidence_builder` → `RoleAlignment` | `intent.role.seniority`, `experience.minimum_years` | the compiled `seniority` / `alternatives` / `leadership` |
| `admission.evaluate_eligibility` | `RoleAlignment.level_fit` / `experience_floor` | the compiled plan |
| `search_pipeline` | the legacy `mapped_plan`; calls `run_shadow(search_id, jd_text, mapped_plan)` | the recruiter brief is not passed to the shadow; the compiled plan never leaves the shadow |

Tests assert that none of these references the compiled plan, a path, the context, an exclusion or provenance, and that the shadow hook is the compiler's only production caller. **Smallest interface changes for the compiled plan to become the source of truth** (not made; `RUNTIME_INTEGRATION_CONTRACT.md` section 8): (1) pass the recruiter brief to the compile and keep the plan beyond the shadow, running the existing search once per context with that path's provider plan; (2) feed the Judge a per-path `SearchIntent` built by `to_judge_signals` (no Judge change) plus one new field, `exclusion_signals`, and one new verdict; (3) fill admission's seniority / experience floor from the context's `admission` entries, leaving an `UNRESOLVED` level ungated and visible; (4) carry `provenance` on `MatchedSignal` and `contributing_path_ids` on `CandidateEvidence`; (5) run `merge_path_results` before `CandidateMerger`; (6) persist `atom_audit` and the contexts in the search record.

## 9. Capability / taxonomy items (recorded, not solved, nothing mapped to pass a test)
- **`Staff`, `Senior Manager`, `Principal`, `Director`**: no approved level mapping (`seniority.json` only): `UNRESOLVED`, kept verbatim; the downstream level reader still reads "Senior Manager" as `senior` (not changed).
- **Work mode**: no provider capability and not verifiable from the profile: `UNRESOLVED`, visible in every context.
- The any-time skill field is not in the capability map; education literals; the two-entry role-family taxonomy; an explicit `current` the source does not support; a comparison phrased outside the cue list.

## 10. Acceptance gates
| # | gate | measured | result |
|---|---|---|---|
| 1 | every hard provider filter has source / approved provenance | 0 violations over the provider-enforced atoms of 15 intents (with the JD / brief supplied) | PASS |
| 2 | unspecified relationship never becomes current | 0 unspecified atoms enforced; None stays None through model → extractor → compiler → audit → context (tests R) | PASS |
| 3 | every sourcing path independently addressable | 20 contexts over 15 intents; Role 1: 2 contexts per run, each with its own provider plan | PASS |
| 4 | downstream context receives every VERIFIED_DOWNSTREAM atom | 774 VERIFIED_DOWNSTREAM entries; for every context the set of such atoms in the plan equals the set in the context; 0 atoms silent at the boundary of 1137 | PASS |
| 5 | preferences preserved without hardening | 0 preferred / context atoms became provider filters; Role 3's 6 companies are preference entries in 5/5 runs | PASS |
| 6 | unresolved values remain visible | 14 unresolved entries (Senior Manager, hybrid, withheld titles); each plan's unresolved atoms are all in its contexts | PASS |
| 7 | provenance survives compiler → downstream | every entry carries a provenance state; 0 provenance / placement problems | PASS |
| 8 | no path flattening | 0 path atoms in another path's context; a global atom reaches every inheriting path, a path atom only its own (checked independently) | PASS |
| 9 | synthetic path merge preserves contributing paths | a candidate in A and B keeps both ids, both payloads and both contexts' obligations; order-independent; no ranking (tests M, S) | PASS |
| 10 | no live provider is called | no network connection in the synthetic end-to-end test (socket.connect is trapped); no new module imports a provider, an HTTP client or the Judge | PASS |

## Tests
`tests/test_runtime_integration.py` (provenance P, analogy A, relationship R, path contract C, evidence routing D, preferences E, synthetic end-to-end S, merge M, consumer audit J, gates G); `tests/test_compiler_contract.py` (contract-1 matrix A-O, kept green; recorded-mode cases now pass the source text). Full suite: see the final line of the session report. The independent verification is `runtime_verify.py` (removes every schema atom, recompiles, rebuilds the contexts, and checks where each atom lands); its committed output is `results/runtime/` and `results/runtime_summary.json`.

## Disclosures
- Production files changed (shadow path only): `search_compiler.py` (provenance gate, `sources`, per-path atom audit, route and text on each atom record), `compiler_audit.py` (contexts in the audit record), `search_compiler_shadow.py` (passes the JD). New: `source_provenance.py`, `downstream_context.py`, `path_merge.py`. Not touched: the Judge, admission, ranking, the pipeline, providers, prompts, the intent schema (the experimental schema is unchanged), the frozen intents and ground truths.
- The contract-1 results (`RESULTS_COMPILER_HARDENING.md`, `results/hardened/`) are kept as the record of that phase and are reproduced with a pinned snapshot of the contract-1 compiler (`compiler_contract1_snapshot.py`); its section 11 item 1 (the analogy title) is superseded by this phase.
- Offline only: no provider, no model, no deployment.

**Stopped here. Waiting for architecture review.**
