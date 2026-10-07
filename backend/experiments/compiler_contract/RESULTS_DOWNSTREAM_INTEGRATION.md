# RESULTS — downstream consumer integration (offline; synthetic candidates only)

Phase: DOWNSTREAM CONSUMER INTEGRATION. Frozen and accepted before this phase: Role 1/2/3 intake validation, the compiler contract, compiler hardening (contract-1), runtime integration. **Not called:** CrustData, Harvest, any provider, any retrieval, any real candidate data. **Not deployed.** Ranking, admission thresholds, level rules and N → 50 → 25 are unchanged (`admission.py` and `candidate_ranker.py` are pinned by content hash). The contract is `backend/services/DOWNSTREAM_CONSUMER_CONTRACT.md`. Measurements: `results/downstream/summary.json` (`python -m backend.experiments.compiler_contract.downstream_verify`); this report is generated from them.

Suite at the end of this phase: **1242 passed, 4 skipped** (the runtime-phase pin "the Judge and admission consume only the legacy intent" was superseded on purpose; its report is now pinned by hash).

## 1. Legacy consumer audit (RUNTIME_INTEGRATION_CONTRACT §8's six changes; no seventh abstraction)
The only new abstraction at the seam is the one field `SearchIntent.compiled_context` and the one resolver `consumer_input.resolve` (changes 2 and 3 of §8, which that contract already named).

| consumer | CURRENT INPUT | REQUIRED NEW INPUT | ADAPTER NEEDED? | SOURCE OF TRUTH |
|---|---|---|---|---|
| `RequirementJudge._judge` (`requirement_judge.py`) | `SearchIntent.core/supporting/differentiator_signals` (bare strings) | a per-path checklist: requirements, exclusions, preferences, unresolved, proficiency, work mode, provenance, path | yes: `consumer_input.resolve` (one call replaces the three list reads); legacy intent unchanged | `DownstreamContext` entries (compiled)  — change 2 (Judge input) |
| evidence builder → `RoleAlignment` (`candidate_evidence_builder.py`) | `intent.role.seniority`, `experience.minimum_years`, `role.title`, `titles.include_titles`, the three signal lists | the compiled level, accepted levels, floor, title facts, and the same judged texts the Judge was asked | yes: `resolve(intent).facts` / `.role_title` / `judged_signals`; the `_classify_*` rules are not touched | `seniority.*`, `experience.min`, `role_family` atoms — changes 2 and 3 |
| `admission.evaluate_eligibility` (`admission.py`) | `RoleAlignment.level_fit` / `experience_floor` (already computed by the evidence builder) | the same two values, computed from compiled facts | no: admission is unchanged (pinned by hash); its inputs change at the evidence builder | compiled atoms through `AdmissionFacts` — change 3 |
| `search_pipeline` (`search_pipeline.py`) | `intent.core_signals` (judging enabled; `core_requirements_total`) | the Judge's resolved tiers | yes: two reads go through `judged_signals`; N → 50 → 25 untouched | the resolved checklist — change 1 (per-path execution) is NOT wired: recorded |
| `candidate_ranker`, `match_explainer`, `role_feedback`, `candidate_presentation` | `RoleAlignment` / the evidence dict (never the intent) | nothing new | no | inherit the compiled facts through `RoleAlignment`; unchanged (ranker pinned by hash) |
| provenance and path on a candidate (`MatchedSignal`, `CandidateEvidence`) | none | provenance per item, the contributing path ids | partly: on the Judge interface and `JudgeOutcome`; the two model fields are not added | change 4 — recorded as unresolved |
| path merge (`merge_path_results`) | (contract only) | per-path results | no | change 5 — unchanged, still a data contract |
| persistence of contexts | the shadow audit record | — | no | change 6 — unchanged |

## 2. Judge interface, before and after
| | before | after |
|---|---|---|
| input | `SearchIntent.core_signals` / `supporting_signals` / `differentiator_signals` (strings) | `resolve(intent)`: the compiled `JudgeChecklist` of THAT path when `compiled_context` is set, else the same three lists |
| negatives | none (`NO_NEGATIVE_SLOT`) | `exclusions` (`must_not_have`) on the interface and in `JudgeOutcome.checklist`; **not evaluated** (no negative verdict yet) |
| unresolved | none (`NO_UNRESOLVED_SLOT`) | `unresolved` with the reason, visible, never judged |
| preferences | forwarded as differentiator text, indistinguishable from requirements | `preferences` (`prefer`), never core, context-only ones carried and not judged |
| proficiency, work mode | text only | `proficiency` field + text; work mode as an item with its fate |
| provenance / path | none (`NO_PROVENANCE_FIELD`, `NO_PATH_CONTEXT`) | on every item: `provenance`, `path_id`, `inherited`, `unsupported_qualifiers` |
| provider syntax | n/a | none (scanned over all 15 frozen intents), and no score / rank / weight field |
| outcome | judgments | + `input_source`, `checklist`, `disagreements` |

## 3. Admission interface, before and after
| | before | after |
|---|---|---|
| target level | `intent.role.seniority` | the `seniority.value` atom, only when it is a requirement of a known level; a preference or an unmapped level is `ungated` and visible |
| accepted levels | none | `seniority.alternatives` (supported by the source), judged by the unchanged level rule once per level |
| experience floor | `intent.experience.minimum_years` | the `experience.min` atom when enforced and supported by the source |
| rules, thresholds, ladder, `evaluate_eligibility` | — | **unchanged** |

## 4. Legacy compatibility
`compiled_context is None` → every consumer behaves exactly as before (`input_source: legacy`; tested including the exact judgments of a scripted run). The default `SearchIntent` has no compiled context, so every production-shaped flow today is legacy. A wrong-typed value raises, it never falls back silently.

## 5. Path contract
Per path, never merged; `PathAttribution.satisfies_required` is a flag, not a score; a path-only requirement is absent from the other path's Judge input; a global atom reaches each path as `inherited`. Details: contract §4.

## 6. Semantic provenance contract
Contract §5. Qualifier claims the cited source did not support, over the 15 frozen intents (each was NOT used; each is kept as a claim with a reason):

| role | qualifier | claims withheld (5 runs) |
|---|---|---|
| R1 | proficiency | 11 |
| R1 | relationship | 3 |
| R2 | proficiency | 55 |
| R2 | relationship | 32 |
| R3 | leadership_kind | 2 |

Generic matrix A-F (current / past / strength / proficiency / alternative level / geographic qualifier) is tested on two unrelated vocabularies; no Role-2 example is in the code.

## 7. Conflict resolution rule
Compiled wins; the difference is recorded; never reconciled (contract §2).

* **legacy: current Python required   |   compiled: Python relationship UNSPECIFIED**: the Judge was asked `['Python']`; winner **compiled**; relationship carried `[None]`; current Python asked or enforced: **False**; recorded disagreements: `[{"compiled": null, "field": "signal.core", "legacy": "Currently works with Python (required)", "winner": "compiled"}, {"compiled": "Python", "field": "signal.core", "legacy": null, "winner": "compiled"}]`
* **legacy: company is a hard (core) requirement   |   compiled: company is a PREFERENCE**: the Judge was asked `[]`; winner **compiled**; carried as `[['prefer', 'Quuxcorp']]`; company required: **False**; recorded disagreements: `[{"compiled": null, "field": "signal.core", "legacy": "Works at Quuxcorp", "winner": "compiled"}]`

## 8. Checklist coverage over the 15 frozen intents
`verified reaching a consumer` counts every `VERIFIED_DOWNSTREAM` atom of every context that reached the Judge, the exclusion slot or `AdmissionFacts`. `admission` = contexts with a level / with a floor / ungated facts.

| role | contexts | verified reaching a consumer | judged items | preferences | exclusions | unresolved | enforced (info) | proficiency items | work-mode items | unsupported qualifiers | admission level/floor/ungated |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R1 | 10 | 234/234 | 308 | 199 | 30 | 21 | 31 | 25 | 0 | 26 | 5/6/10 |
| R2 | 5 | 397/397 | 400 | 3 | 0 | 60 | 50 | 54 | 0 | 87 | 0/5/0 |
| R3 | 5 | 103/103 | 176 | 109 | 5 | 11 | 50 | 5 | 5 | 2 | 1/5/4 |

## 9. Synthetic candidates A / B / C / D (scripted model; wiring only, not candidate quality)
The REAL `RequirementJudge` (verified-quote gate, review pass, evidence builder) runs on synthetic profiles built from each path's own checklist; a scripted stand-in answers "met" iff the requirement's text is in a passage. A states what only Path A asks (plus what both ask), B only Path B, C both, D neither. Expected is plain set logic over the required texts, independent of the Judge. Roles 2 and 3 declare no sourcing paths, so each is run on its real single context and on a **synthetic** two-path overlay (one extra skill per path); Role 1 has real paths A and B (run 3 has requirements exclusive to each). All match: **yes**.

| case | cand. | paths satisfied | expected | match | requirements asked per path | judge input |
|---|---|---|---|---|---|---|
| R1 run 3 (real paths) | A | PATH A | PATH A | yes | 29/29 | compiled |
| R1 run 3 (real paths) | B | PATH B | PATH B | yes | 29/29 | compiled |
| R1 run 3 (real paths) | C | PATH A, PATH B | PATH A, PATH B | yes | 29/29 | compiled |
| R1 run 3 (real paths) | D | — | — | yes | 29/29 | compiled |
| R1 run 1 + synthetic two-path overlay | A | PATH A | PATH A | yes | 29/29 | compiled |
| R1 run 1 + synthetic two-path overlay | B | PATH B | PATH B | yes | 29/29 | compiled |
| R1 run 1 + synthetic two-path overlay | C | PATH A, PATH B | PATH A, PATH B | yes | 29/29 | compiled |
| R1 run 1 + synthetic two-path overlay | D | — | — | yes | 29/29 | compiled |
| R2 run 1 (no sourcing paths: one context) | A | None | None | yes | 82 | compiled |
| R2 run 1 (no sourcing paths: one context) | B | — | — | yes | 82 | compiled |
| R2 run 1 (no sourcing paths: one context) | C | None | None | yes | 82 | compiled |
| R2 run 1 (no sourcing paths: one context) | D | — | — | yes | 82 | compiled |
| R3 run 1 (no sourcing paths: one context) | A | None | None | yes | 35 | compiled |
| R3 run 1 (no sourcing paths: one context) | B | — | — | yes | 35 | compiled |
| R3 run 1 (no sourcing paths: one context) | C | None | None | yes | 35 | compiled |
| R3 run 1 (no sourcing paths: one context) | D | — | — | yes | 35 | compiled |
| R2 run 1 + synthetic two-path overlay | A | PATH A | PATH A | yes | 83/83 | compiled |
| R2 run 1 + synthetic two-path overlay | B | PATH B | PATH B | yes | 83/83 | compiled |
| R2 run 1 + synthetic two-path overlay | C | PATH A, PATH B | PATH A, PATH B | yes | 83/83 | compiled |
| R2 run 1 + synthetic two-path overlay | D | — | — | yes | 83/83 | compiled |
| R3 run 1 + synthetic two-path overlay | A | PATH A | PATH A | yes | 36/36 | compiled |
| R3 run 1 + synthetic two-path overlay | B | PATH B | PATH B | yes | 36/36 | compiled |
| R3 run 1 + synthetic two-path overlay | C | PATH A, PATH B | PATH A, PATH B | yes | 36/36 | compiled |
| R3 run 1 + synthetic two-path overlay | D | — | — | yes | 36/36 | compiled |

Verified in the tests for every case: the path attribution above; every compiled semantic requirement visible to the Judge; negatives, preferences, proficiency and unresolved items present on the interface (Role 1 has all four, Role 3 has exclusions, unresolved and proficiency); preferences stay preferences (a profile that states only preferences satisfies no path); no path is flattened; `input_source` is `compiled` everywhere (no legacy fallback).

## 10. Acceptance gates
| # | gate | test(s) |
|---|---|---|
| 1 | the Judge consumes the compiled context when available | `test_JC_the_judge_asks_exactly_the_checklist_and_never_reconstructs_from_prose` |
| 2 | admission consumes the compiled facts | `test_AD_admission_gates_on_the_compiled_level_and_floor`, `test_AD_the_compiled_facts_match_the_legacy_facts_when_they_agree` |
| 3 | legacy fallback works | `test_BC_without_a_compiled_context_every_consumer_behaves_as_before` |
| 4 | the compiled context is the semantic source of truth | `test_ST_compiled_meaning_wins_and_the_disagreement_is_recorded_not_reconciled`, `test_ST_the_legacy_fields_are_read_for_meaning_only_inside_the_consumer_seam` |
| 5 | no path flattening | `test_PATH_each_path_has_its_own_checklist_and_nothing_is_flattened`, `test_PATH_a_path_specific_atom_is_not_in_another_paths_judge_input` |
| 6 | provenance survives into the Judge | `test_JC_every_item_carries_provenance_and_its_path` |
| 7 | semantic exclusions, proficiency and work mode reach the Judge | `test_JC_exclusions_are_must_not_have_and_carry_provenance`, `test_JC_proficiency_and_work_mode_reach_the_checklist` |
| 8 | preferences remain preferences | `test_JC_preferences_stay_preferences_and_are_never_required`, `test_SY_a_candidate_matching_a_preference_only_does_not_satisfy_a_path` |
| 9 | unresolved facts remain visible | `test_JC_unresolved_stays_visible_with_a_reason_and_is_never_judged`, `test_AD_an_unresolved_level_is_never_invented` |
| 10 | an unspecified relationship never becomes current | `test_UR_*` |
| 11 | conflict tests prefer the compiled semantics | `test_ST_conflict_legacy_current_required_vs_compiled_unspecified_relationship`, `test_ST_conflict_legacy_company_hard_filter_vs_compiled_company_preference` |
| 12 | every VERIFIED_DOWNSTREAM atom reaches a consumer | `test_JC_every_verified_downstream_atom_reaches_the_judge_the_exclusion_slot_or_admission` |
| 13 | semantic provenance covers the complete constraint (matrix A-F, generic) | `test_SP_A_*` … `test_SP_F_*`, `test_SP_no_source_supported_value_plus_model_inferred_qualifier_becomes_a_hard_filter` |
| 14 | no threshold, level rule or ranking changed; all existing tests green | `test_AD_no_threshold_level_rule_or_ranking_changed` (content-hash pin of `admission.py` and `candidate_ranker.py`) and the full suite |

## 11. Unresolved downstream issues (for architecture review)
1. **No negative verdict.** Exclusions reach the Judge's input but are not evaluated. A profile that states an excluded profile is judged only on the positive requirements (tested, documented). Needs a decision: a new verdict, and its validation, belong to a later phase.
2. **Per-path execution is not wired.** `search_pipeline` runs one search per intent; the shadow does not hand the compiled context, and does not pass the recruiter brief. Until the pipeline sets `compiled_context` once per path, production stays on the legacy path. Not deployed.
3. **A preference no longer gates admission.** The legacy path gated on a *preferred* level; "compiled wins" removes that. This is the correct reading of the contract but it changes which candidates an unclear-strength seniority would have excluded: needs sign-off.
4. **Conservative qualifier checks.** The checks are lexical. Role 2 has 55 depth claims withheld across 5 runs, mostly depths the model inferred from a verb ("build and deploy" → hands-on). They stay visible as `UNRESOLVED` with the claim; whether verb-implied depth should count is a policy decision.
5. **Alternative levels use the unchanged rule per level.** That is the smallest migration, but it is new behaviour for an alternative the legacy intent never carried: needs sign-off.
6. `MatchedSignal.provenance` and `CandidateEvidence.contributing_path_ids` (§8 change 4), the merge hook (5) and persistence (6) are not wired.
7. A synthetic scripted model proves the wiring, not what the real model does with the new checklist; the real Judge has not been run on any candidate in this phase (no live call).

## 12. Hard stop
No CrustData. No retrieval. No deployment. No live candidate testing. Waiting for architecture review.
