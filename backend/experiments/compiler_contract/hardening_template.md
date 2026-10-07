# RESULTS — Compiler hardening (offline; intent → compiler contract)

**Acceptance gate: all 10 criteria met, measured.** Compiler `{{version}}`, contract `compiler-contract-1` (`backend/services/COMPILER_CONTRACT.md`).
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
{{silent}}

After hardening, every atom has exactly one fate:

{{after_fates}}

## 2. Before / after field fate matrix
BEFORE is the legacy compiler (a byte-identical copy is kept in `legacy_compiler_v1.py` and pinned by hash); AFTER is the hardened compiler's own declared fate, which the independent verifier confirmed is consistent with what the output depends on. The BEFORE column classifies by routing (an audit row routed `downstream_evidence` counted as `VERIFIED_DOWNSTREAM`); the AFTER column uses the contract's strength rule (a preferred or context atom is `PREFERENCE_CONTEXT`, even where it still appears in the Judge checklist at a lower tier).

{{matrix}}

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

{{leaves}}

## 4. Relationship semantics
`SkillReq`, `SkillAnyOf` and `CompanyScale` default to `None` (the smallest backward-compatible representation: the field already existed and accepted strings). An explicit `current`, `past`, `any` keeps its exact meaning.

{{relationship}}

An omitted relationship has the fate `VERIFIED_DOWNSTREAM` because the only provider field that could carry "at any time" is not in the capability map (so nothing provider-side can enforce it without inventing a time scope), and the Judge can check the skill against the whole profile. A preferred unspecified skill is `PREFERENCE_CONTEXT`. An omitted company-scale relationship is `UNRESOLVED`. The stored raw model outputs omitted `relationship` on 0 of 343 atoms, so this closes a latent hazard; it did not change any frozen result.

## 5. Provenance gate
{{location}}

- A skill, group, company, experience, education, location or explicit exclusion whose only source is `inferred` never produces a leaf. Test A covers each case.
- Gate 2 is measured independently by `invented_model_only_hard_filters`: 0 over the 15 intents (Role 2's `country = India` and `state = Telangana` leaves, and Role 3's `state = Telangana`, are gone: the sources said `Hyderabad` / `Hyderabad, India`).
- Not invented: no company, radius, seniority, title alternative, experience bound or provider semantic that the intent does not carry (bare-intent test).

## 6. Strength semantics
Provider hard leaves (besides the title) before → after, for each strength:

{{strength}}

Only `required` selects candidates. `preferred` and `context` keep their strength in the audit and are `PREFERENCE_CONTEXT`; there is no invented ranking boost.

## 7. Sourcing paths
Each path is compiled from its own effective view (a path inherits the global intent; a singleton it states replaces the global one; a same-named skill or domain replaces; the rest is added). A test proves the compiler's inheritance equals the frozen `effective_view` on all five real Role 1 intents. Role 1, per path:

{{paths}}

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

{{gate}}

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
