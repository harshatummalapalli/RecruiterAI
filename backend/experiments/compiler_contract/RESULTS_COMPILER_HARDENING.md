# RESULTS — Compiler hardening (offline; intent → compiler contract)

**Acceptance gate: all 10 criteria met, measured.** Compiler `v2-2026-10-07`, contract `compiler-contract-1` (`backend/services/COMPILER_CONTRACT.md`).
Silent drops over the 15 frozen intents: **336 meaning atoms before → 0 after** (28 decision records and 30 metadata atoms also → 0). No model, CrustData, Harvest,
retrieval or deployment was used. Ranking, admission, the Judge and the production schema were not changed; the schema is not promoted.

This is a compiler-FIDELITY result, not a search-quality result: nothing here says the candidates improved, and no provider was called to find out.

## What to distrust (read first)
1. **The verifier is mine.** "0 silent drops" means: for every atom the schema can hold, the whole compiler output depends on that atom (measured by removing it). The verifier is independent of the compiler's own `atom_audit` (a test plants a drop and shows it is caught), but its atom list comes from the same experiment code I wrote for the baseline; the schema-coverage test makes a future new field fail until it is routed.
2. **A fate is a routing decision, not a correctness proof.** `VERIFIED_DOWNSTREAM` says the atom is preserved for the Judge / admission gate; neither consumer reads the compiled plan today (shadow mode). `UNRESOLVED` items are honest, not solved (section 11).
3. **Gate 2 is about provenance the intent carries.** A source-mentioned analogy title and an explicit-but-unsupported `current` are still enforced as stated, because `role_family` and `CompanyScale` carry no provenance and an explicit `current` must keep its meaning (your instruction). They are intake/validation problems and are listed in section 11.
4. **Role 1 run 1 is not fixed by this phase.** Its intake put "6+ years" in the global intent; the compiler applies it to both paths faithfully. That is an extraction error and is recorded, not hidden.
5. **I changed the production relationship default and one extractor line** (the group-collapse that wrote `"current"`), as the brief asked for relationship semantics; the compiler, the audit and `structured_intent.py` are production files in the shadow path. Nothing executes the compiled plan.
6. **Reconciliation retirement is deliberately conservative and never triggered on the frozen intents (0 retired).** It is proven by synthetic tests only; on the real Role 1 intents the intake already compiled the final meaning into the surviving atoms.
7. **Same stored intents as the baseline**: Role 2 is prompt_v3 (before `advanced` / `work_mode`); its `current` skills and analogy title are intake errors the compiler cannot see.

## 1. Silent-drop count, before / after
| role (5 runs) | meaning atoms | SILENTLY_DROPPED meaning: before | after | decision records: before | after | metadata: before | after |
|---|---|---|---|---|---|---|---|
| R1 | 296 | 174 | 0 | 28 | 0 | 10 | 0 |
| R2 | 510 | 125 | 0 | 0 | 0 | 10 | 0 |
| R3 | 273 | 37 | 0 | 0 | 0 | 10 | 0 |
| **all** | 1079 | 336 | 0 | 28 | 0 | 30 | 0 |

After hardening, every atom has exactly one fate:

| fate after hardening (15 intents) | atoms |
|---|---|
| VERIFIED_DOWNSTREAM | 663 |
| PREFERENCE_CONTEXT | 232 |
| ENFORCED | 170 |
| DROPPED_WITH_JUSTIFICATION | 43 |
| CARRIED (provenance column of every atom record; not an atom with a fate) | 15 |
| UNRESOLVED | 9 |
| NORMALIZED | 5 |
| **atoms** | 1137 |

## 2. Before / after field fate matrix
BEFORE is the legacy compiler (a byte-identical copy is kept in `legacy_compiler_v1.py` and pinned by hash); AFTER is the hardened compiler's own declared fate, which the independent verifier confirmed is consistent with what the output depends on. The BEFORE column classifies by routing (an audit row routed `downstream_evidence` counted as `VERIFIED_DOWNSTREAM`); the AFTER column uses the contract's strength rule (a preferred or context atom is `PREFERENCE_CONTEXT`, even where it still appears in the Judge checklist at a lower tier).

| concept [strength, relationship] | role | BEFORE (legacy compiler) | AFTER (hardened compiler) |
|---|---|---|---|
| `company [preferred]` | R3 | PREFERENCE_CONTEXT×30 | PREFERENCE_CONTEXT×30 |
| `domain (in path) [preferred]` | R1 | SILENTLY_DROPPED×8 | PREFERENCE_CONTEXT×8 |
| `domain (in path) [required]` | R1 | SILENTLY_DROPPED×3 | VERIFIED_DOWNSTREAM×3 |
| `domain [context]` | R1 | SILENTLY_DROPPED×10 | PREFERENCE_CONTEXT×10 |
| `domain [context]` | R2 | SILENTLY_DROPPED×3 | PREFERENCE_CONTEXT×3 |
| `domain [context]` | R3 | SILENTLY_DROPPED×5 | PREFERENCE_CONTEXT×5 |
| `domain [preferred]` | R1 | SILENTLY_DROPPED×3 | PREFERENCE_CONTEXT×3 |
| `domain [preferred]` | R3 | SILENTLY_DROPPED×10 | PREFERENCE_CONTEXT×10 |
| `domain [required]` | R2 | SILENTLY_DROPPED×13 | VERIFIED_DOWNSTREAM×13 |
| `domain [required]` | R3 | SILENTLY_DROPPED×5 | VERIFIED_DOWNSTREAM×5 |
| `education.degree [preferred]` | R1 | SILENTLY_DROPPED×5 | PREFERENCE_CONTEXT×5 |
| `education.degree [required]` | R2 | ENFORCED×10 | ENFORCED×10 |
| `education.degree [required]` | R3 | ENFORCED×5 | ENFORCED×5 |
| `education.stream [preferred]` | R1 | SILENTLY_DROPPED×30 | PREFERENCE_CONTEXT×30 |
| `education.stream [required]` | R2 | ENFORCED×20 | ENFORCED×20 |
| `education.stream [required]` | R3 | ENFORCED×25 | ENFORCED×25 |
| `evidence_signal [context]` | R1 | VERIFIED_DOWNSTREAM×12 | PREFERENCE_CONTEXT×12 |
| `evidence_signal [context]` | R3 | VERIFIED_DOWNSTREAM×54 | PREFERENCE_CONTEXT×54 |
| `evidence_signal [preferred]` | R1 | VERIFIED_DOWNSTREAM×6 | PREFERENCE_CONTEXT×6 |
| `evidence_signal [preferred]` | R3 | VERIFIED_DOWNSTREAM×10 | PREFERENCE_CONTEXT×10 |
| `evidence_signal [required]` | R1 | VERIFIED_DOWNSTREAM×55 | VERIFIED_DOWNSTREAM×55 |
| `evidence_signal [required]` | R2 | VERIFIED_DOWNSTREAM×116 | VERIFIED_DOWNSTREAM×116 |
| `evidence_signal [required]` | R3 | VERIFIED_DOWNSTREAM×30 | VERIFIED_DOWNSTREAM×30 |
| `experience.max [required]` | R3 | ENFORCED×5 | ENFORCED×5 |
| `experience.min (in path) [required]` | R1 | SILENTLY_DROPPED×4 | ENFORCED×4 |
| `experience.min [required]` | R1 | ENFORCED×1 | ENFORCED×1 |
| `experience.min [required]` | R2 | ENFORCED×5 | ENFORCED×5 |
| `experience.min [required]` | R3 | ENFORCED×5 | ENFORCED×5 |
| `location.country (in path)` | R1 | SILENTLY_DROPPED×5 | ENFORCED×5 |
| `location.entry (in path) [required]` | R1 | SILENTLY_DROPPED×10 | ENFORCED×10 |
| `location.entry [required]` | R2 | ENFORCED×5 | ENFORCED×5 |
| `location.entry [required]` | R3 | ENFORCED×5 | ENFORCED×5 |
| `location.remote (in path)` | R1 | SILENTLY_DROPPED×5 | PREFERENCE_CONTEXT×5 |
| `location.work_mode` | R3 | SILENTLY_DROPPED×5 | UNRESOLVED×5 |
| `provenance.basis` | R1 | SILENTLY_DROPPED×5 | CARRIED×5 |
| `provenance.basis` | R2 | SILENTLY_DROPPED×5 | CARRIED×5 |
| `provenance.basis` | R3 | SILENTLY_DROPPED×5 | CARRIED×5 |
| `reconciliation` | R1 | SILENTLY_DROPPED×28 | DROPPED_WITH_JUSTIFICATION×28 |
| `role_archetype` | R1 | SILENTLY_DROPPED×5 | DROPPED_WITH_JUSTIFICATION×5 |
| `role_archetype` | R2 | SILENTLY_DROPPED×5 | DROPPED_WITH_JUSTIFICATION×5 |
| `role_archetype` | R3 | SILENTLY_DROPPED×5 | DROPPED_WITH_JUSTIFICATION×5 |
| `role_family` | R1 | ENFORCED×5 | ENFORCED×5 |
| `role_family` | R2 | ENFORCED×10, NORMALIZED×5 | ENFORCED×10, NORMALIZED×5 |
| `role_family` | R3 | ENFORCED×5 | ENFORCED×5 |
| `semantic_exclusion` | R1 | SILENTLY_DROPPED×15 | VERIFIED_DOWNSTREAM×15 |
| `semantic_exclusion` | R3 | SILENTLY_DROPPED×5 | VERIFIED_DOWNSTREAM×5 |
| `seniority.alternatives (in path)` | R1 | SILENTLY_DROPPED×5 | PREFERENCE_CONTEXT×5 |
| `seniority.leadership` | R1 | SILENTLY_DROPPED×2 | VERIFIED_DOWNSTREAM×2 |
| `seniority.leadership` | R3 | SILENTLY_DROPPED×2 | VERIFIED_DOWNSTREAM×2 |
| `seniority.leadership (in path)` | R1 | SILENTLY_DROPPED×18 | PREFERENCE_CONTEXT×10, VERIFIED_DOWNSTREAM×8 |
| `seniority.value` | R1 | VERIFIED_DOWNSTREAM×1 | VERIFIED_DOWNSTREAM×1 |
| `seniority.value` | R3 | VERIFIED_DOWNSTREAM×5 | UNRESOLVED×4, VERIFIED_DOWNSTREAM×1 |
| `seniority.value (in path)` | R1 | SILENTLY_DROPPED×9 | PREFERENCE_CONTEXT×5, VERIFIED_DOWNSTREAM×4 |
| `skill (in path) [preferred, any]` | R1 | SILENTLY_DROPPED×1 | PREFERENCE_CONTEXT×1 |
| `skill (in path) [required, any]` | R1 | SILENTLY_DROPPED×4 | VERIFIED_DOWNSTREAM×4 |
| `skill (in path) [required, current]` | R1 | SILENTLY_DROPPED×1 | ENFORCED×1 |
| `skill [preferred, any]` | R1 | VERIFIED_DOWNSTREAM×19 | PREFERENCE_CONTEXT×19 |
| `skill [required, any]` | R1 | VERIFIED_DOWNSTREAM×21 | VERIFIED_DOWNSTREAM×21 |
| `skill [required, any]` | R2 | VERIFIED_DOWNSTREAM×172 | VERIFIED_DOWNSTREAM×172 |
| `skill [required, any]` | R3 | VERIFIED_DOWNSTREAM×47 | VERIFIED_DOWNSTREAM×47 |
| `skill [required, current]` | R1 | ENFORCED×2 | ENFORCED×2 |
| `skill [required, current]` | R2 | ENFORCED×32 | ENFORCED×32 |
| `skill.proficiency` | R1 | SILENTLY_DROPPED×20 | VERIFIED_DOWNSTREAM×20 |
| `skill.proficiency` | R2 | SILENTLY_DROPPED×109 | VERIFIED_DOWNSTREAM×109 |
| `skill.proficiency` | R3 | SILENTLY_DROPPED×5 | VERIFIED_DOWNSTREAM×5 |
| `skill.proficiency (in path)` | R1 | SILENTLY_DROPPED×6 | VERIFIED_DOWNSTREAM×5, PREFERENCE_CONTEXT×1 |
| `skill_any_of [required, any]` | R2 | VERIFIED_DOWNSTREAM×10 | VERIFIED_DOWNSTREAM×10 |
| `skill_any_of [required, any]` | R3 | VERIFIED_DOWNSTREAM×10 | VERIFIED_DOWNSTREAM×10 |
| `sourcing_path (in path)` | R1 | SILENTLY_DROPPED×10 | ENFORCED×10 |

## 3. Changed compiler behaviour
| area | before | after |
|---|---|---|
| per-atom audit | none | `atom_audit`: one record per atom (scope, provenance, strength, proficiency, relationship, fate, destination, justification) |
| provenance | `basis` ignored | model-only never a filter; a location state / country the cited text does not contain is not enforced (and is recorded) |
| relationship | an omitted value became `current` and a hard filter | `None` = unspecified: never current; `VERIFIED_DOWNSTREAM` |
| strength | `context` acted as `required`; experience and location ignored strength; a preferred education vanished | only `required` selects; the rest are audited context |
| sourcing paths | ignored: global atoms only, path-only atoms vanished | one independent plan per path (alternatives), explicit inheritance |
| semantic exclusions, domain, proficiency, leadership, alternatives, countries, remote, work mode, reconciliations | silently dropped | explicit fate, destination and justification |
| unknown level | carried verbatim, no fate | `UNRESOLVED`, preserved, never remapped |
| unsupported exclusion kind | ignored | `UNRESOLVED` |
| explicit `past` / `any` company scale | a hard filter on the CURRENT employer's headcount | `UNRESOLVED` (the only verified field is the current employer's) |
| audit record | flat | adds `atom_audit`, `downstream_exclusions`, per-path plans / checklists / requirements; `judge_checklist(plan, path_id)` |

Provider leaves before / after on the frozen intents (every difference is explained by the gate or by path compilation; nothing else moved):

| intent | provider leaves before | after | removed | added |
|---|---|---|---|---|
| R1/1 | 8 | 13 | – | city ["Hyderabad", "Pune"]; country ["India"]; description "Power Query"; headline "Power Query"; summary "Power Query" |
| R1/2 | 1 | 4 | – | city ["Hyderabad", "Pune"]; country ["India"]; years_of_experience_raw 6 |
| R1/3 | 1 | 4 | – | city ["Hyderabad", "Pune"]; country ["India"]; years_of_experience_raw 6 |
| R1/4 | 1 | 4 | – | city ["Hyderabad", "Pune"]; country ["India"]; years_of_experience_raw 6 |
| R1/5 | 1 | 4 | – | city ["Hyderabad", "Pune"]; country ["India"]; years_of_experience_raw 6 |
| R2/1 | 46 | 44 | country ["India"]; state ["Telangana"] | – |
| R2/2 | 46 | 44 | country ["India"]; state ["Telangana"] | – |
| R2/3 | 31 | 29 | country ["India"]; state ["Telangana"] | – |
| R2/4 | 19 | 17 | country ["India"]; state ["Telangana"] | – |
| R2/5 | 34 | 32 | country ["India"]; state ["Telangana"] | – |
| R3/1 | 12 | 11 | state ["Telangana"] | – |
| R3/2 | 12 | 11 | state ["Telangana"] | – |
| R3/3 | 12 | 11 | state ["Telangana"] | – |
| R3/4 | 12 | 11 | state ["Telangana"] | – |
| R3/5 | 12 | 11 | state ["Telangana"] | – |

## 4. Relationship semantics
`SkillReq`, `SkillAnyOf` and `CompanyScale` default to `None` (the smallest backward-compatible representation: the field already existed and accepted strings). An explicit `current`, `past`, `any` keeps its exact meaning.

| relationship | provider hard leaves (excl. title) | fate | capability token | justification |
|---|---|---|---|---|
| current | 3 | ENFORCED | enforce_but_not_verifiable | required with an explicit 'current' relationship; capability enforce_but_not_verifiable |
| past | 2 | ENFORCED | enforce_but_not_verifiable | required with an explicit 'past' relationship; capability enforce_but_not_verifiable |
| any | 0 | VERIFIED_DOWNSTREAM | disclose | relationship 'any' has no verified provider field (capability disclose); verified downstre |
| (omitted) | 0 | VERIFIED_DOWNSTREAM | unspecified_relationship | temporal relationship unspecified: never defaulted to current, so no current-role provider |

An omitted relationship has the fate `VERIFIED_DOWNSTREAM` because the only provider field that could carry "at any time" is not in the capability map (so nothing provider-side can enforce it without inventing a time scope), and the Judge can check the skill against the whole profile. A preferred unspecified skill is `PREFERENCE_CONTEXT`. An omitted company-scale relationship is `UNRESOLVED`. The stored raw model outputs omitted `relationship` on 0 of 343 atoms, so this closes a latent hazard; it did not change any frozen result.

## 5. Provenance gate
| case | provider leaves | component fates |
|---|---|---|
| JD: 'Hyderabad, India'; model wrote Telangana | city=["Hyderabad"]; country=["India"] | country:ENFORCED; state:DROPPED_WITH_JUSTIFICATION; city:ENFORCED |
| JD states all three | city=["Hyderabad"]; country=["India"]; state=["Telangana"] | country:ENFORCED; state:ENFORCED; city:ENFORCED |
| JD: 'Hyderabad' only | city=["Hyderabad"] | country:DROPPED_WITH_JUSTIFICATION; state:DROPPED_WITH_JUSTIFICATION; city:ENFORCED |
| alias: 'Bangalore' | city=["Bengaluru"]; country=["India"]; state=["Karnataka"] | country:ENFORCED; state:ENFORCED; city:ENFORCED |

- A skill, group, company, experience, education, location or explicit exclusion whose only source is `inferred` never produces a leaf. Test A covers each case.
- Gate 2 is measured independently by `invented_model_only_hard_filters`: 0 over the 15 intents (Role 2's `country = India` and `state = Telangana` leaves, and Role 3's `state = Telangana`, are gone: the sources said `Hyderabad` / `Hyderabad, India`).
- Not invented: no company, radius, seniority, title alternative, experience bound or provider semantic that the intent does not carry (bare-intent test).

## 6. Strength semantics
Provider hard leaves (besides the title) before → after, for each strength:

| construct | required (hard leaves before → after) | preferred | context |
|---|---|---|---|
| skill (current) | 3 → 3 | 0 → 0 | 3 → 0 |
| skill group (current) | 6 → 6 | 0 → 0 | 6 → 0 |
| company | 1 → 1 | 0 → 0 | 1 → 0 |
| company scale (current) | 1 → 1 | 0 → 0 | 1 → 0 |
| education (degree+stream) | 3 → 3 | 0 → 0 | 3 → 0 |
| experience | 2 → 2 | 2 → 0 | 2 → 0 |
| location | 3 → 3 | 3 → 0 | 3 → 0 |

Only `required` selects candidates. `preferred` and `context` keep their strength in the audit and are `PREFERENCE_CONTEXT`; there is no invented ranking boost.

## 7. Sourcing paths
Each path is compiled from its own effective view (a path inherits the global intent; a singleton it states replaces the global one; a same-named skill or domain replaces; the rest is added). A test proves the compiler's inheritance equals the frozen `effective_view` on all five real Role 1 intents. Role 1, per path:

| intent | path | strategy | that path's provider plan (leaves) |
|---|---|---|---|
| R1/1 | PATH A | domain_led | headline (.) "Python"; headline (.) "SQL"; country in ["India"]; summary (.) "Python"; summary (.) "SQL"; description (.) "Python"; description (.) "SQL"; title (.) "Data Analyst"; years_of_experience_raw => 6 |
| R1/1 | PATH B | capability_led | headline (.) "Power Query"; headline (.) "Python"; headline (.) "SQL"; city in ["Hyderabad", "Pune"]; summary (.) "Power Query"; summary (.) "Python"; summary (.) "SQL"; description (.) "Power Query"; description (.) "Python"; description (.) "SQL"; title (.) "Data Analyst"; years_of_experience_raw => 6 |
| R1/2 | PATH A | domain_led | country in ["India"]; title (.) "Data Analyst" |
| R1/2 | PATH B | capability_led | city in ["Hyderabad", "Pune"]; title (.) "Data Analyst"; years_of_experience_raw => 6 |
| R1/3 | PATH A | domain_led | country in ["India"]; title (.) "Data Analyst" |
| R1/3 | PATH B | capability_led | city in ["Hyderabad", "Pune"]; title (.) "Data Analyst"; years_of_experience_raw => 6 |
| R1/4 | PATH A | domain_led | country in ["India"]; title (.) "Data Analyst" |
| R1/4 | PATH B | capability_led | city in ["Hyderabad", "Pune"]; title (.) "Data Analyst"; years_of_experience_raw => 6 |
| R1/5 | PATH A | domain_led | country in ["India"]; title (.) "Data Analyst" |
| R1/5 | PATH B | capability_led | city in ["Hyderabad", "Pune"]; title (.) "Data Analyst"; years_of_experience_raw => 6 |

- Path B (`Hyderabad` or `Pune`, 6+ years) never receives India or Path A's requirements; Path A (`India`, remote acceptable) never receives the cities or the 6+ years; `Power Query` is `core` on Path B and absent or only `supporting` on Path A (the waiver), in each path's own checklist.
- Run 1 is the intake error above (6+ years global); the compiler cannot tell.
- `plan.filter_tree` is an OR over the path trees (alternatives); consumers should execute `plan.paths`. Merging and deduplication are not implemented, and nothing is sent to a provider.
- A provider constraint a path cannot express keeps a fate (`remote` allowed → `PREFERENCE_CONTEXT`; leadership, proficiency, domain → downstream), it is not deleted.

## 8. Extension field routing (see the matrix and `COMPILER_CONTRACT.md` section 8)
`semantic_exclusions` → `VERIFIED_DOWNSTREAM` as an exclusion row, never a company/title NOT-IN; `domain` → required `VERIFIED_DOWNSTREAM`, else `PREFERENCE_CONTEXT`; `proficiency` → `VERIFIED_DOWNSTREAM`, `hands-on` / `working knowledge of` / `advanced proficiency in` carried verbatim; `leadership` and `alternatives` → the admission row and a checklist item; `countries` → a country filter; `remote` → `PREFERENCE_CONTEXT` (allowed) or `VERIFIED_DOWNSTREAM` (not allowed); `work_mode` → `UNRESOLVED` (the capability map says no provider filter and it is not verifiable from the profile), the typed value preserved and never turned into another mode; `reconciliations` → decision records (`DROPPED_WITH_JUSTIFICATION` with the result kept, or `UNRESOLVED`); retired JD atoms → `DROPPED_WITH_JUSTIFICATION`.

## 9. Backward compatibility
- `tests/test_search_compiler.py`, `test_compiler_audit.py`, `test_search_compiler_shadow.py`, `test_structured_intent.py`, `test_crustdata_capabilities.py` pass unchanged. The two production anchors compile to the same filter tree, the same audit rows (source, strength, route, temporal, capability), the same warnings and the same checklist as the legacy compiler (a test asserts it).
- The full suite passes: **1102 passed, 4 skipped**.
- One earlier experiment assertion was updated on purpose: `test_a_downstream_compiler_behaviour_is_unchanged` used to prove the compiler ignored proficiency; it now proves the provider plan is unchanged by proficiency while a downstream row carries the level. Before-measurements that need the old behaviour read the committed baseline JSON or the pinned legacy copy; the old compiler-file hash pins were replaced accordingly.
- Frozen ground truths, stored model outputs and Role 1/2/3 results are untouched (hash-pinned by the earlier tests, still passing).

## 10. Tests
`tests/test_compiler_contract.py` (90): A provenance, B omitted relationship, C explicit current, D strength distinct, E preferred never required, F context never required, G independent path plans, H no leakage and per-path checklists, I semantic exclusions, J proficiency, K work mode, L unknown seniority, M reconciliation (waived per path, waived globally, hard filter, unresolved, and the three cases that must NOT be retired), N every atom has exactly one fate and a justification, O silent-drop count zero, consistency of every declared fate, zero invented filters, the planted-drop self-test, backward compatibility on the anchors, determinism, and the schema-coverage guard. Acceptance gate:

| # | gate | measured | result |
|---|---|---|---|
| 1 | SILENTLY_DROPPED = 0 | 0 of 1137 atoms (independent ablation); 0 fates inconsistent with the output | PASS |
| 2 | invented model-only hard filters = 0 | 0 (independent audit of every provider leaf). Before: 15 unsupported state / country leaves, all removed by the gate (Role 2: Telangana and India x5 each; Role 3: Telangana x5) | PASS |
| 3 | unspecified relationship never treated as current | 135 atoms with an unspecified relationship are enforced; omitted → VERIFIED_DOWNSTREAM (tests B) | PASS |
| 4 | strength does not silently strengthen | 0 preferred/context atoms are enforced (tests D, E, F) | PASS |
| 5 | path-specific constraints stay path-specific | Role 1 runs 2-5: 6+ years, Hyderabad/Pune, India and Power Query are each in exactly their own path (tests G, H) | PASS (run 1: its intake put 6+ years in the GLOBAL intent, so the compiler applies it to both paths: an extraction error, recorded) |
| 6 | semantic exclusions remain semantic | 0 negative provider leaves; all 20 semantic exclusions → `downstream_exclusion` (test I) | PASS |
| 7 | proficiency has an explicit fate | all 140 proficiency atoms have a fate (VERIFIED_DOWNSTREAM; PREFERENCE_CONTEXT for a preferred skill), carried verbatim (test J) | PASS |
| 8 | work mode has an explicit fate | 5/5 Role 3 `hybrid` → UNRESOLVED with a reason and a plan warning, never remapped (test K) | PASS |
| 9 | unknown taxonomy values preserved and audited | 'Senior Manager' → UNRESOLVED, kept verbatim; 'Staff' likewise (test L) | PASS |
| 10 | existing production-shaped compiler tests green | tests/test_search_compiler.py, test_compiler_audit.py, test_search_compiler_shadow.py, test_structured_intent.py, test_crustdata_capabilities.py unchanged and passing; anchors compile identically | PASS |

## 11. Unresolved taxonomy / capability / provenance items (recorded, not solved)
1. **`role_family` has no provenance field**: a comparison title the source mentions (Role 2 prompt_v3: `Forward Deployed Engineer`) is still a hard title leaf. The intake validator `title_analogy` exists and is not run at the compiler boundary.
2. **An explicit `current` the source does not support** (Role 2 prompt_v3: 32 skills) is still enforced as stated. It needs a pre-compile provenance validation at intake, not a change of meaning in the compiler. `CompanyScale` also has no `basis`.
3. **Capability map**: no entry for the any-time description field (so `any` and unspecified skills are never provider-enforced); no work-mode capability (`UNRESOLVED`).
4. **Location**: a multi-entry or two-part place compiles to its cities only (the existing rule); the other components are recorded `DROPPED_WITH_JUSTIFICATION`. No approved city → state table exists, so none is invented.
5. **Seniority taxonomy**: the approved levels are `seniority.json` only (senior/lead, junior/entry, mid/intermediate). `Staff`, `Senior Manager`, `Principal`, `Director` are `UNRESOLVED` and preserved. The downstream candidate-evidence level reader reads "Senior Manager" as `senior` (unchanged, not this compiler's).
6. **Education literals** are unchanged: `Bachelor’s degree` (curly apostrophe) and a `Related discipline` stream are still literal provider strings (flagged for a taxonomy/capability pass).
7. **Role-family taxonomy** has two entries; every other title is used verbatim.
8. **Consumers**: the Judge does not yet read `exclusion_checklist` or the per-path checklists, the admission gate reads the legacy `intent.role.seniority`, and path results are not merged. These are wiring items for a later phase.
9. **Reconciliation retirement** is precision-first: an atom shared by several JD items is retired only when the reconciliation's topic names it, so a retired requirement can remain active when the topic does not name it. On the frozen intents no atom needed retiring (the intake compiled the final meaning).

## Disclosures
- Offline only; no provider or model call. Gates 1-9 are measured on the 15 frozen intents plus synthetic cases; no search-quality claim.
- Production files changed (shadow path only): `search_compiler.py`, `compiler_audit.py`, `structured_intent.py` (relationship default), `structured_intent_extractor.py` (one line). `crustdata_capabilities.py`, `role_family_taxonomy.py`, `seniority.json`, prompts, admission, ranking and the Judge are untouched.
- The 15 frozen intents and their ground truths are unchanged.

**Stopped here. Waiting for architecture review.**
