# RESULTS — Role 1 hardening pass (experimental v3)

**STATUS (owner decision, final): ROLE 1 REPRESENTATION ACCEPTED FOR CROSS-ROLE VALIDATION.** This does not authorize compiler or
retrieval implementation, and it is not a claim of 5/5 stability. See the FROZEN section of `DESIGN.md`.

*Gate verdict as originally written at the end of the hardening pass (kept for the record, superseded by the status above):
"ROLE 1 INTAKE REPRESENTATION STILL NEEDS CORRECTION".*

The schema now holds everything the gate asks about, but the acceptance gate is not met: Path B's "6+ years" leaked into Path A
in 1 of 5 runs, a people-only leadership requirement survived in 1 of 5, and the Path A domain's strength and granularity vary.
Neither failure is a missing field. One (the leak) is caught by the new generic validator at runtime; the other is not. This is
Role 1 only and is not evidence of generality: the next test must be a differently shaped real role.

Same model (`gpt-6.1-sol`, medium), same JD and brief, 5 runs, streamed, 25.1k input / 21.4k output tokens, 63-77 s per run.
Evidence: `results/experimental_v3/`, `results/comparison.json`; reproduce the table with `python -m
backend.experiments.intake_strategy.compare_arms`. Design: `DESIGN.md` (hardening section).

## Read these first (what to distrust, and where I disagree with the brief)
1. **"Senior" is in the source.** The brief, under Path A, says "Lead / Senior Data Analyst identity" (line 50), and nowhere else.
   The instruction "do not promote Senior unless the source supports it" is therefore satisfied by *keeping* Senior on Path A and
   nowhere else, not by removing it. Path A is `[Lead, Senior]` in 5/5 runs, Path B and the global level are `[Lead]` in 5/5, and
   `unsupported_level` fired 0 times. If you intend Path A to be Lead only, that contradicts the brief text and the brief should change.
2. **The earlier "Senior" was probably partly my prompt.** v2's illustration said "any *senior* adjuster in Sao Paulo". It is gone
   from v3 (a test now forbids "senior" in the added prompt text). I did not re-run v2 without it, so how much it contributed is unknown.
3. **Prior Lead/Senior variation: classified as instability, and also a representation gap.** Same source, `Senior` x3 / `Lead` x2, is
   extraction instability, as you said. But a single-valued `value` also forced a choice between two source-stated levels, which is
   why `seniority.alternatives` exists. With it the result is 5/5 identical. I would not call it purely extraction.
4. **First v3 attempt failed 4/5 (schema validation).** The model copied a whole heading ("PATH A - DOMAIN-LED CANDIDATE") into the
   24-char path `id`, as my wording invited. I fixed the wording (the SHORT designation) and re-ran all five, so the reported set is
   one clean batch, not a patch. The failed attempt is the prompt defect, not a semantic result. Its one parsed run passed everything
   except leadership.
5. **I changed an evaluator after seeing a result.** `cyber_review_not_secops` failed 2/5 as run because my regex matched "security
   monitoring" / "cybersecurity operations" inside atoms that *deny* them ("...rather than cybersecurity operations", "security
   monitoring alone is not equivalent"). I read them: they are faithful narrowings. The check is now negation-aware. Both counts
   are shown below (FAIL x2 as run, PASS x5 corrected). The negation rule is crude (any negation word in the atom).
6. **A second evaluator weakness, not fixed.** "Path located in the sources" was too loose; I tightened it (a source line must open
   with the id). It can still be fooled by an id that happens to open an unrelated line (v2's `domain-led`), so v2's
   `path_leakage_checkable` PASS x5 is spurious. It does not affect v3 (ids are `PATH A` / `PATH B`).
7. **One role, five runs, one model.** 1/5 is 20% observed with a wide interval; I did not draw more samples to improve it.
8. **The v3 prompt is shaped by this class of role** (its generic rules target the failures just seen). It contains no Role 1 values
   or gold text (tests enforce that), but it is not neutral.

## A-K, five runs each (`v3` is the corrected evaluator; "as run" differs only where noted)
| item | assertion(s) | v2 re-evaluated | v3 |
|---|---|---|---|
| A two paths | `two_paths_preserved`, `path_a_domain_led`, `path_b_capability_led` | PASS x5 | **PASS x5** |
| B path geography (typed) | `path_geography_differs` | PARTIAL x5 (India in `entries`) | **PASS x5** |
| C no Path-B leakage into A | `path_b_requirements_not_in_path_a` | FAIL x5 | PASS x4, **FAIL x1** (EXTRACTION) |
| D Power Query per path | `pq_not_mandatory_path_a`, `pq_working_knowledge_path_b` | PASS x5 | **PASS x5** |
| E Lead semantics | `lead_people_or_technical`, `seniority_levels_source_supported` | PASS x2 PARTIAL x3 / PASS x2 FAIL x3 | PASS x4 **PARTIAL x1** (RECONCILIATION) / **PASS x5** |
| F cyber vs SOC | `cyber_review_not_secops`, `hard_negative_secops_preserved` | PASS x5 | as run: PASS x3 FAIL x2; corrected: **PASS x5** / **PASS x5** |
| G security-firm exclusion | `security_firm_exclusion_semantic`, `no_invented_company_exclusion` | PASS x4 PARTIAL x1 | **PASS x5** / **PASS x5** |
| H reconciliation | `reconciliation_visible`, `jd_not_silently_discarded` | PASS x5 | **PASS x5** |
| I provenance | `provenance_preserved` | PASS x5 | **PASS x5** (every atom `verified`, 0 unsupported, 0 misattributed) |
| J typed India vs cities, remote | `intent_country_level_geography`, `remote_typed` | FAIL x5 (no typed field) | **PASS x5** / **PASS x5** |
| K no invented radius / company filter | `no_invented_radius`, `no_invented_company_filter` | PASS x5 | **PASS x5** |
| validators | `generic_validators_clean`, `path_leakage_checkable` | FAIL x5 / PASS x5 (spurious) | PASS x4 **FAIL x1** (VALIDATION: it correctly caught the leak) / PASS x5 |

Typed results in all 5 v3 runs: Path A `countries=[India]`, `entries=[]`, `remote=allowed`; Path B `countries=[]`,
`entries=[Hyderabad, Telangana, India; Pune, Maharashtra, India]`, `remote=null`. The security-firm exclusion is, every run,
"A strong SQL/Python analyst working at a security firm" as a semantic concept (no `currently`, no blanket form, 0 company exclusions).

## The four requested deterministic validators
| validator | v3 (5 runs) | replayed on the previous v2 outputs |
|---|---|---|
| path requirement leakage | fired 1x: run 1, `experience 6+ years is required for [PATH A, PATH B] but the sources state it only for [PATH B]` (true positive) | fired 1x (run 1); it could not check runs 2-5 (their ids were not the source's names) |
| reconciliation conflict | fired 0x. Unit tests show it fires for `security monitoring` required after a contradiction and for Power Query required on a waived path | 0x (no case it can see) |
| unsupported seniority alternative | fired 0x (Senior on Path A only, verified against the brief) | n/a (field did not exist) |
| country / city representation | fired 0x | fired 5x (India in `entries`), all true positives |

## Acceptance gate
| gate item | result |
|---|---|
| Path B's 6+ years does not leak to Path A | **FAIL, 4/5.** Run 1 inherited it globally. EXTRACTION; detected by VALIDATION |
| unsupported Senior not promoted | PASS (see item 1 above: Senior is supported for Path A only) |
| India is country, not city | PASS 5/5 |
| remote is structural | PASS 5/5 |
| security-firm exclusion stays semantic | PASS 5/5 |
| recruiter/JD conflicts explicitly reconciled | **PARTIAL.** `reconciliation_visible` 5/5, 0 conflict errors, but run 4 kept "Ability to lead, mentor, coach, and support analysts" as a required people-only atom beside `leadership=[people,technical]`, and nothing at runtime saw it (RECONCILIATION, plus a VALIDATION coverage gap) |
| no critical assertion depends only on quote text | PASS: a test strips every quote and the content assertions are unchanged; only `provenance_preserved` and `reconciliation_visible` read quotes, by design |
| five runs semantically stable | **PARTIAL.** Stable 5/5: strategies, both geographies, remote, levels, PQ on B, SQL/Python, experience on B, leadership modes, the semantic negatives, reconciliations (5-6 per run). Not stable: A experience (leak 1/5), Path A domain atoms 4-6 and `required` in 3/5 vs `preferred` in 2/5 (the brief says "Ideal", so this is source ambiguity plus granularity), PQ on A `absent` 4/5 vs `preferred` 1/5 (equivalent meaning, different representation) |

## Failure classification
- **EXTRACTION**: 6+ years placed globally (run 1); Path A domain strength/granularity; PQ-on-A representation.
- **RECONCILIATION**: leadership responsibility left required (run 4).
- **VALIDATION coverage**: the runtime reconciliation check cannot link the run-4 atom to the quoted JD sentence (different sentences).
- **PROVENANCE**: none. **REPRESENTATION**: none observed in v3.
- Not model failures: attempt-1 id-length parse failures (prompt wording); `cyber_review_not_secops` x2 (evaluator false positive, corrected).

## Owner decisions (answered; now locked ground truth)
1. Path A is Lead OR Senior. Senior stays (the brief says "Lead / Senior Data Analyst identity").
2. Path A's domain is **preferred**, not required (the brief says "Ideally"); never a global requirement.
3. The JD responsibility "Lead, mentor, support analysts" stays contextual; "Lead" means people OR technical. No new field.
4. 6+ years belongs to Path B only: not global, not Path A. The leakage validator stays; the 1/5 leak is documented, not tuned away.
5. The security-firm statement is kept as a qualified semantic concept, subordinate to the work-identity (security operations)
   negative; never an employer-industry exclusion.

## Re-scored under the locked decisions (offline, no new model call)
The stored v3 runs were re-evaluated with the locked ground truth (`path_a_domain_preferred`, `experience_not_global`, Path A levels
must be Lead and Senior, firm statement must sit beside the work-identity negative):
- `path_a_domain_preferred`: PASS x2 (runs 1-2), **FAIL x3** (runs 3-5 hold the Path A domain as `required`). EXTRACTION: the schema
  can express the decided answer; the model does not reliably produce it.
- `experience_not_global`: PASS x4, FAIL x1 (run 1, the same leak the validator caught).
- `seniority_levels_source_supported`: PASS x5 (Path A `[Lead, Senior]`, Path B `[Lead]`).
- `security_firm_exclusion_semantic`: PASS x5. `lead_people_or_technical`: PASS x4, PARTIAL x1 (RECONCILIATION).
So against the locked truth, the 5 runs deviate in three extraction ways (domain strength 3/5, 6+ leak 1/5, leadership 1/5). They are
accepted as known instability for cross-role validation, not fixed here.

## Smallest next step (not run)
Do not tune Role 1 further. Candidate, to be argued before it is built: let a reconciliation name the atoms it retires and have
code verify none remains required, which would catch the run-4 pattern without lexical matching (this is a possible new field and
is NOT added). Then run the unchanged v3 on a differently shaped real role.

## Tests
Full suite: 842 passed, 4 skipped (836 before the locked-decision tests were added; 789 at the original handoff). The new tests are offline and cover: leakage on an unrelated role with
other path names and numbers; the Senior-for-Path-A-only rule; a model-generated level; typed country/city/remote misuse; the
qualified security-firm exclusion; scope-aware reconciliation conflict (and that `unresolved` is never flagged); denial vs promotion;
quote independence; and that both prompts keep production rules 1-10 verbatim with no Role 1 terms in the added text.
