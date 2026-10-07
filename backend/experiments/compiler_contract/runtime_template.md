# RESULTS — Offline runtime integration (compiled plan → downstream context)

**All 10 acceptance gates are met, measured.** Compiler `{{version}}`. No CrustData, Harvest, retrieval, deployment or model call; no real candidate; no ranking, admission-threshold, prompt or Judge change.

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

{{provenance}}

The rule, in one sentence: a hard filter needs `source` or `knowledge` provenance (or `unrecorded` in a legacy intent); `model_only`, `absent`, `comparison` and `unverified_quote` are withheld with a fate and a reason (`COMPILER_CONTRACT.md` section 4, `RUNTIME_INTEGRATION_CONTRACT.md` section 1). No value of Role 1, 2 or 3 is named in the compiler, the classifier, the context builder or the merge module (a test scans them).

Titles, per role (run 1):

{{titles}}

Provider leaves, contract-1 compiler (no source text) vs now (with source text). The gate withheld exactly one leaf per Role 2 run and nothing else:

{{leaf_delta}}

## 2. Analogy safety
Role 2's brief says "...more like a Forward Deployed Engineer who understands the client requirements". Every sentence that states that title introduces it with a comparison cue, so it is classified `comparison`: it is withheld from the title filter in 5/5 runs and kept as an `UNRESOLVED` entry with the quote. `Software Engineer` and `Solution Architect` (stated as the role, in the JD title) stay targets. The same mechanism handles eight generic cues on an invented title ("Quantum Plumber"), a title that is a target in one place and compared elsewhere (stays a target), and a title never stated (`absent`). Without the source text, no title of a provenance-carrying intent reaches a filter at all. Nothing is Role-2-specific.

## 3. Relationship migration audit
Every production reader and writer of a relationship, after the default changed from `current` to unspecified:

{{relationship}}

- Explicit `current`, `past`, `any` keep their meaning through the JSON model, the compiler, the atom audit, the context and the Judge adapter (parametrized tests). An unspecified relationship stays `None` in each layer, is never enforced, and is told apart from an explicit `current` by `intent_hash`.
- The old default is NOT restored. A test pins the exact set of production files that read a relationship and fails on any `relationship or "current"` / `.get("relationship", "current")` style default, so a new consumer must be reviewed.
- `requirement_semantics.py` has its own `scope = "current" | "career"`; it is derived from the requirement's text, not from `SkillReq.relationship`, and is unaffected.

## 4. Path contract (Role 1)
Each path has its own `DownstreamContext`; a global atom is inherited into each path's context (marked `inherited`), a path atom appears only in its own. Role 1, runs 1-5:

{{paths}}

Runs 2-5 satisfy every requested property: **Path A** is India (country filter) with remote acceptable (`PREFERENCE_CONTEXT`, an allowance), domain-led, no 6+ years, Power Query absent or only a `supporting` preference (waived); **Path B** is Hyderabad / Pune, 6+ years, Power Query `core` with `working_knowledge`, capability-led. No path atom appears in another path's context (0 leaks over 15 intents). Run 1 shows 6+ years on Path A too: the intake put it in the global intent, and the context says so (`scope: global`, `inherited`).

## 5. Downstream evidence contract
Every `VERIFIED_DOWNSTREAM` atom is an explicit entry (`judge_requirement`, `judge_exclusion` or `admission`) in each context it applies to. Where each concept lands, over the 15 intents (entries counted once per context):

{{kinds}}

- **Semantic exclusions** reach the context as `judge_exclusion` (negatives): 35 entries, never a company / title filter, and never mixed into the positive Judge signals.
- **Proficiency** arrives verbatim: `advanced proficiency in Microsoft Excel`, `working knowledge of Power Query`, `hands-on SQL`.
- **Work mode** arrives as `unresolved` with its typed value (`hybrid`) and the reason (no provider filter, not verifiable from the profile): visible, never remapped, never part of geography (`location` keeps `entry` / `country` and `work_mode` apart).
- **Leadership kinds, domain, alternatives** arrive as requirement / preference entries with their tier.
- **Provenance** (`state`, `sources`, `quote`) travels with every entry. **Unresolved** items (an unknown level, a work mode, a withheld title) stay visible in every context they apply to.

**DOWNSTREAM CONTRACT GAPS.** Some entries have no slot in the interface the current consumers accept. They stay in the context and are listed by `legacy_consumer_gaps` (atoms over the 15 intents):

{{gaps}}

`NO_NEGATIVE_SLOT`: the Judge cannot be told a candidate must NOT have a profile. `NO_UNRESOLVED_SLOT`: nothing can carry an unresolved item. `ADMISSION_READS_LEGACY_INTENT`: the compiled level is not what admission reads. `PREFERENCE_NOT_FORWARDED`: a preference kept as context reaches no signal or ranking input. Structurally, SearchIntent signals are bare strings (`NO_PROVENANCE_FIELD`) and one SearchIntent is one search (`NO_PATH_CONTEXT`).

## 6. Preference contract
Preferences survive as preferences: never required, never provider filters, no invented ranking or boost (no entry, context or merged record has a score, rank, weight or boost field).

{{preferences}}

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
{{gate}}

## Tests
`tests/test_runtime_integration.py` (provenance P, analogy A, relationship R, path contract C, evidence routing D, preferences E, synthetic end-to-end S, merge M, consumer audit J, gates G); `tests/test_compiler_contract.py` (contract-1 matrix A-O, kept green; recorded-mode cases now pass the source text). Full suite: see the final line of the session report. The independent verification is `runtime_verify.py` (removes every schema atom, recompiles, rebuilds the contexts, and checks where each atom lands); its committed output is `results/runtime/` and `results/runtime_summary.json`.

## Disclosures
- Production files changed (shadow path only): `search_compiler.py` (provenance gate, `sources`, per-path atom audit, route and text on each atom record), `compiler_audit.py` (contexts in the audit record), `search_compiler_shadow.py` (passes the JD). New: `source_provenance.py`, `downstream_context.py`, `path_merge.py`. Not touched: the Judge, admission, ranking, the pipeline, providers, prompts, the intent schema (the experimental schema is unchanged), the frozen intents and ground truths.
- The contract-1 results (`RESULTS_COMPILER_HARDENING.md`, `results/hardened/`) are kept as the record of that phase and are reproduced with a pinned snapshot of the contract-1 compiler (`compiler_contract1_snapshot.py`); its section 11 item 1 (the analogy title) is superseded by this phase.
- Offline only: no provider, no model, no deployment.

**Stopped here. Waiting for architecture review.**
