# DOWNSTREAM CONSUMER CONTRACT — the compiled context is the input to the Judge and to admission

Companion to `COMPILER_CONTRACT.md` (the compiler never silently discards meaning) and `RUNTIME_INTEGRATION_CONTRACT.md` (the meaning survives the compiler boundary as a per-path `DownstreamContext`). This contract says what happens at the **next** boundary: the consumers read the compiled meaning, not the legacy `SearchIntent`. Offline, deterministic, no provider, no retrieval, no scoring. Nothing here changes ranking, an admission threshold, a level rule, or N → 50 → 25.

```
StructuredHiringIntent (+ JD / brief)
   │ compile_intent(intent, sources)                 provenance gate + SEMANTIC provenance (§5)
   ▼
CompiledPlan ── paths[] ── build_downstream_contexts ──▶ DownstreamContext (one per path)
                                                              │ search_intent_for_context(ctx, base)   adds ONE field: SearchIntent.compiled_context
                                                              ▼
                                                   consumer_input.resolve(intent)                      the ONLY place the legacy fields are read for meaning
                                  ┌───────────────────────────┼─────────────────────────────┐
                         JudgeChecklist              AdmissionFacts                  title facts
                      (what the Judge asks)    (what admission's inputs use)   (role title + approved equivalents)
```

## 0. Architecture-review decisions (binding on this contract)
1. **A preferred requirement never gates admission.** (Level, accepted levels and experience floor gate only when REQUIRED; a preferred / context / unresolved / unsupported fact is carried in `AdmissionFacts.ungated`, visible and never invented.)
2. **Accepted seniority alternatives have OR semantics.** A candidate is `aligned` when aligned at the target level OR any accepted level; a confident `above` / `below` needs every accepted level to agree.
3. **Verb-implied proficiency is not inferred.** A depth the source does not state stays `UNRESOLVED` (visible, with the claim) and is never asked of the Judge. The checks stay conservative.
4. **Pipeline wiring is completed before any live validation** (§9 maps every connection point; nothing is enabled).
5. **The shadow receives the JD AND the recruiter / HM brief**, not the JD alone (§9).

## 1. Single source of truth
`SearchIntent.compiled_context` is `None` or a `DownstreamContext`.
* **Present → source `compiled`.** Every semantic fact the Judge, the evidence builder and admission use comes from the context. The legacy `core_signals` / `supporting_signals` / `differentiator_signals`, `role.seniority`, `experience.minimum_years`, `role.title`, `titles.include_titles` are **not read for meaning**. Nothing is reconstructed from them after compilation.
* **Absent → source `legacy`.** Exactly today's behaviour (capability-aware backward compatibility). A present-but-wrong-typed value raises `TypeError`; it is never a silent fall back to the legacy meaning.
* The legacy fields stay on the intent because the provider flow (natural-language query, planner, translator) still uses them. They are kept untouched by `search_intent_for_context(ctx, base)`; only `compiled_context` is added.
* A test pins that the legacy fields are read for meaning in `consumer_input.py` only, and that no consumer reaches into the compiler, the plan or the atom audit.

## 2. Conflict resolution rule (never silent)
When a legacy value differs from the compiled meaning, **the compiled meaning is used and the difference is recorded** as a `Disagreement(field, legacy, compiled, winner="compiled")` on the resolved input and on `JudgeOutcome.disagreements`. There is no merging, no "stricter of the two", no union.

| field | recorded when |
|---|---|
| `seniority` | legacy `role.seniority` ≠ the compiled admission level (either may be absent) |
| `experience.minimum_years` | legacy ≠ the compiled floor |
| `signal.<tier>` | a legacy requirement text the compiled context does not carry (`compiled: null`: NOT used), or a compiled requirement the legacy intent does not state (`legacy: null`: used) |

Critical cases, both tested: a legacy "current Python required" against a compiled "Python relationship unspecified" → the Judge is asked "Python"; no current-Python requirement is asked, enforced or carried; the relationship travels as `None`. A legacy company requirement against a compiled company preference → a preference; never required.

## 3. The Judge interface (`JudgeChecklist`, per path)
Built only from that path's own context entries. **Never merged across paths.** No provider syntax (no filter tree, no provider field name: pinned by a test over all 15 frozen intents) and no score, rank, weight or boost field (pinned).

| list | polarity | contents | does the Judge evaluate it? |
|---|---|---|---|
| `requirements` | `must_have` | every `VERIFIED_DOWNSTREAM` atom routed to downstream evidence, with tier, proficiency, relationship, provenance | **yes**, at its tier |
| `exclusions` | `must_not_have` | semantic exclusions (the profile the candidate must NOT have) | **yes, as explicit predicates in a separate exclusion pass** (`PRESENT` / `NOT_PRESENT` / `INSUFFICIENT_EVIDENCE`; `PRESENT` needs a quote that passes the gate and names an indicator of the predicate; never part of the positive requirement judgments; §3e) |
| `preferences` | `prefer` | `PREFERENCE_CONTEXT` atoms; never in the core tier | the ones routed to evidence are judged at their own (non-core) tier; context-only ones (a preferred company, an education) are carried, not judged |
| `unresolved` | `undecided` | `UNRESOLVED` atoms with the reason (an unknown level, a work mode no provider filters, an unsupported qualifier) | no, never; visible, never invented |
| `already_enforced` | informational | what the provider already enforced | no (not re-required independently) |

Each `ChecklistItem`: `item_id` (the compiled atom id), `concept`, `text` (recruiter meaning), `polarity`, `tier`, `judged`, `strength`, `proficiency` (`hands_on` / `working_knowledge` / `advanced`, also in the text), `relationship` (`None` = unspecified, never read as current), `fate`, `path_id`, `inherited`, `provenance` (`state`, `sources`, `quote`), `reason`, `alternatives`, `unsupported_qualifiers` (the claim the source did not support, and why). Work mode is an item with `concept == "location.work_mode"` (verified, preferred or unresolved by its fate), exposed as `JudgeChecklist.work_mode`; proficiencies as `.proficiencies`.

Two rules in the checklist: (a) leadership kinds the source accepts as alternatives ("people **or** technical") are **one** item with `alternatives`, so an OR is not turned into an AND; (b) a preference that would inherit a required strength (the "remote is acceptable" allowance inside a required place) is carried without the core tier.

`JudgeOutcome` additionally records `input_source`, the `checklist` the Judge was given, and the `disagreements`. The scripted/real model sees only requirement texts (no provenance, no path); provenance and path live on the interface and in the outcome. The verified-quote gate and the review pass are unchanged.

### 3a. The exclusion pass (superseded by 3b-3f; kept for the history)
The first exclusion pass (v1, then one revision v2) gave the model the recruiter's prose and answered `present` / `not_present`. It is validated in `RESULTS_REAL_JUDGE_VALIDATION.md` and was replaced by the Evidence Check below because the prose form was read inconsistently.

## 3b. The Evidence Check (`backend/services/evidence_check.py`)
The semantic unit the Judge evaluates. A **downstream execution artifact**: built from the compiled checklist, per path; **not** part of `StructuredHiringIntent` (that module is hash-pinned). One check = one semantic claim = one `check_id`.

| field | meaning |
|---|---|
| `check_id` | unique per path (`<path or global>#<atom id>|<tier or exclusion>`); the ONLY key a verdict may bind to |
| `path_id` | the sourcing path the check belongs to (a global atom is one check per path) |
| `concept`, `kind` | the atom's concept; `skill` / `proficiency` / `any_of` / `prose` / `legacy` / `exclusion` |
| `criterion` | positives: the exact claim the model is asked about (for a depth claim: the skill AND the depth). negatives: a one-line description; the model is given the predicate |
| `label` | the stable text key of the existing judgments and alignment (the checklist item text) |
| `polarity` | `positive` or `negative` |
| `strength`, `tier` | from the compiled atom |
| `proficiency`, `proficiency_source` | `hands_on` / `working_knowledge` / `advanced`; source `intent` (a compiled atom) or `stated_in_criterion_text` (an explicit leading depth phrase such as "Working knowledge of X"). **Never inferred from a verb.** |
| `relationship` | `None` = unspecified; never read as current |
| `provenance` | `state`, `sources`, `quote`, as in the checklist |
| `subject`, `subject_terms`, `requires_work_evidence` | the deterministic binding rules of 3c |
| `predicate`, `recruiter_wording` | negatives only: the explicit predicate (3e); the recruiter's original wording is kept for audit and **never sent to the model** |

## 3c. Requirement binding
* A verdict binds to exactly **one** `check_id` (the model's `r` / `x` number is an alias; an id answered twice is ambiguous and is treated as unanswered, not guessed).
* `met` / `partly` / `PRESENT` stands only if (1) its quote passes the quote gate (3f) **and** (2) the quote supports THIS check, deterministically:
  * **subject binding**: a named skill's quote must contain that skill (every significant token, whole words, plural tolerant). The evidence for Python is never the evidence for Java just because the candidate has both.
  * **work evidence**: a check that requires a depth needs demonstrated work or a certification. A skills-list entry, a title, a headline or a computed passage is "a skill quote alone" and does not evidence a depth.
  * **indicator binding** (exclusions): a PRESENT quote must contain one of the predicate's own indicator terms.
* A quote that does not support the exact check is **discarded** (the verdict becomes `not_evidenced`, with `discard_reason` and the discarded quote, and the discard is listed in `JudgeOutcome.binding_discards`). A binding discard is final: it is not retried.
* The review pass (unchanged prompt) is given the check's complete `criterion`, not a label.
* Known limit: subject binding is lexical. A plain, multi-word CATEGORY skill is bound on all its tokens in this implementation, which over-rejects legitimate evidence ("Financial modeling" vs "builds financial models"); see `RESULTS_EVIDENCE_CHECK_VALIDATION.md` (class VALIDATION, fix recommended and not applied).

## 3d. Proficiency
The Judge evaluates the **complete** claim `skill + proficiency` (Java + hands_on; Excel + advanced; Power BI + working_knowledge), as ONE check whose criterion states both. The plain skill ("Java") is a separate check. The depth text is deterministic: hands-on = built/written/operated it in real work (listing, studying or working beside users is not); working knowledge = practical familiarity from actual use; advanced = depth beyond routine use (stated expertise or sophisticated work). A depth is never inferred from an action verb in the source, and an unsupported depth stays `UNRESOLVED` (never a check at all).

## 3e. Exclusions: explicit predicates and three states
An exclusion is built into a predicate; the Judge does not infer it from recruiter prose.

```
subject: candidate_work_identity
must_not_indicate: [...]            what, if the profile shows it, excludes the candidate
not_sufficient: [...]               what NEVER makes it apply (works for a company in the field, mentions the topic, adjacent duties)
unless_candidate_also_shows: [...]  the recruiter's "without Y" / "not equivalent to Y": if the profile also shows it, the exclusion does not apply
exclusive: true                     "exclusively in X": applies only if ALL the substantive work shown is X
qualifier: "generic"                the recruiter's qualifier, kept
```
Forms parsed structurally and generically: "X are not equivalent to Y", "X alone without Y", "exclusively in X without Y"; anything else is a literal profile statement. An exclusion phrase that names a known identity gets that identity spelled out from approved, versioned knowledge (`exclusion-predicates-v1`, same status as the role-family taxonomy; one validated anchor: security operations = SOC, security operations, cybersecurity operations, equivalent security-operations work; never "works for a security company", "mentions security", "has security experience"). Every other phrase gets a structural predicate (its own words, the qualifier, no expansion).

| state | meaning | how it arises |
|---|---|---|
| `PRESENT` | supported evidence exists; the candidate fails the exclusion | the model says present AND the quote passes the gate AND names an indicator of the predicate |
| `NOT_PRESENT` | no supported evidence of the exclusion | the model says not_present AND the profile describes work (demonstrated work or a certification) |
| `INSUFFICIENT_EVIDENCE` | the profile does not contain enough to clear the exclusion | the model says so; or the profile describes no work (the model's NOT_PRESENT is overruled); or a PRESENT claim cannot be evidenced (unverified after the one retry, or not supported by its quote); or the model gave no answer |

**INSUFFICIENT_EVIDENCE is never silently turned into NOT_PRESENT**, and an unsupported PRESENT is INSUFFICIENT_EVIDENCE (a policy, recorded as a risk), not NOT_PRESENT.

## 3f. Quote verification and the retry rule
`verify_quote` is the gate (unchanged in strength, now explicit): one **contiguous**, **exact** span of **one** supplied passage (case and whitespace only are folded); no ellipsis (`...` or the single character), no paraphrase, no fabrication, no span joined from two places; at least 3 characters. Failure reasons: `ellipsis`, `quote_not_found`, `quote_too_short`, `no_passage`.

**One narrow retry.** After the first pass, only the checks whose claimed verdict failed the gate for one of those reasons are re-asked, once, with an exact-quote instruction in the payload (same prompt, same model). A check that succeeded is never re-asked; a binding discard is not a quote failure and is never retried; there is no third attempt. For exclusions a PRESENT that still fails after the retry is INSUFFICIENT_EVIDENCE. `JudgeOutcome.retries` records, per check, the first-pass failure, whether it recovered and the final failure.

## 4. The path contract
A candidate can satisfy Path A, Path B, both, or neither. The Judge is run against **each path's own** checklist (`search_intents_from_contexts(contexts, base)` gives one `SearchIntent` per path). `attribute_path(path_id, checklist, judgments)` → `PathAttribution(met, partly, not_evidenced, satisfies_required)`: `satisfies_required` is true iff every judged must-have item **of that path** has a verified `met`. It is a flag for attribution, **not a score**: no path is ranked above another, no path weight exists, and the attribution is not used by ranking or admission. A requirement stated by only one path never appears in the other path's Judge input (tested), and a global atom reaches every path that inherits it, marked `inherited`. `merge_path_results` (runtime contract §6) is unchanged and carries each contributing path's own obligations.

## 5. Semantic provenance contract (the complete constraint, not only the value)
A provider hard filter, or a hard downstream requirement, needs provenance for the **complete semantic constraint**: the value, its requiredness and its temporal scope (and, where claimed, its depth, its accepted alternatives, its leadership kind, its distance and its work arrangement). A source-supported value with a model-inferred qualifier is **not** a hard constraint on that qualifier: the claim is not used, the atom keeps the value, and the claim and the reason are kept in `AtomRecord.unsupported_qualifiers` and travel to the context and the checklist. Generic, lexical, role-agnostic (no role, title or example is named in code); checked only for an atom whose provenance state is `source` (a quote is verified against the supplied JD / brief).

| test | qualifier claimed | not supported when the text about the value … | effect |
|---|---|---|---|
| A | `current` | has no present-use cue | relationship becomes unspecified (a company falls back to `any`); not a current-role filter |
| B | `past` | has no past-use cue | same |
| C | `required` | says it is only preferred / a plus | strength becomes `preferred`; not a hard filter |
| D | proficiency | states no depth at least as strong | the depth atom is `UNRESOLVED` (kept visible), never handed to the Judge as a requirement |
| E | an alternative level / leadership kind | does not state that level / kind | `UNRESOLVED`; not an accepted level; not required |
| F | a radius, remote, or work mode | does not state the distance / arrangement | `UNRESOLVED`; no `geo_distance`; never converted to another mode |
| (experience) | a bound | does not contain the number | that bound is `UNRESOLVED`, not a floor |

A generic test asserts that over all 15 frozen intents no `ENFORCED` / `NORMALIZED` atom carries an unsupported qualifier.

## 6. Unspecified is not current (kept through the Judge and admission)
`relationship = None` (the extractor omitted it) is carried as `None` in the context entry and in the `ChecklistItem`, is rendered without a time scope, and is never defaulted. The set of production files that read a relationship is pinned by a test (`consumer_input.py` joined it, as a CARRIER); `requirement_judge.py`, `candidate_evidence_builder.py`, `admission.py` and `search_pipeline.py` never read one.

## 7. Admission facts (`AdmissionFacts`): only the SOURCE changes
Admission's rules are untouched (`evaluate_eligibility`, the level ladder, `_classify_*`, the experience-floor arithmetic, all thresholds; `admission.py` and `candidate_ranker.py` are pinned by content hash). What changes is where the inputs come from:

| fact | legacy source | compiled source |
|---|---|---|
| target level | `intent.role.seniority` | the `seniority.value` atom, **only** when its fate is a requirement (known level, required strength) |
| accepted levels | (none) | `seniority.alternatives` atoms with a requirement fate |
| experience floor | `intent.experience.minimum_years` | the `experience.min` atom, when it is enforced / required and its number is supported by the source |
| title facts | `role.title`, `titles.include_titles` | the `role_family` atom's value and its approved equivalent titles (`components`) |

* **Unresolved is never invented:** a level with no approved mapping (`Staff`, `Principal`, `Senior Manager`, …), an unsupported alternative or an unsupported bound is **not gated on**; it is kept in `AdmissionFacts.ungated` with its fate and reason.
* **A preferred requirement never gates (decision 1):** a preferred level, accepted level or experience range is `ungated` and visible. (The legacy path gated on it; tested: a `Director` is not excluded by a *preferred* Senior level, and a candidate with too few years is not excluded by a *preferred* range.)
* **Accepted alternative levels are OR (decision 2)** and use the **unchanged** level rule once per accepted level: `aligned` at any accepted level is `aligned`; `above` / `below` stands only if every accepted level agrees; otherwise `unclear` (admission never gates on it). With no alternatives (always so for a legacy intent) this is exactly the old rule.

## 8. Known limits (recorded, not hidden)
1. **What a `PRESENT` exclusion does is undefined.** The Judge evaluates exclusions (§3e) but no consumer acts on the verdict: not ranking, not admission, not the recruiter view. Whether it demotes, flags or excludes is an architecture decision (and, per decision 1, an exclusion is a requirement-side fact, not an admission threshold).
2. **Per-path pipeline execution is not wired** (§9). Nothing is deployed and the seam stays dormant in production: `compiled_context` is `None` until the pipeline sets it.
3. `MatchedSignal.provenance` and `CandidateEvidence.contributing_path_ids` are not added; provenance and path are on the Judge interface and in the outcome.
4. The depth / alternative / leadership / mode / distance checks are lexical and deliberately conservative (decision 3).
5. `JudgeChecklist` groups leadership kinds; `to_judge_signals` lists them separately. They agree on everything else (tested).
6. **Quote-gate collapse (existing production behaviour, measured in `RESULTS_REAL_JUDGE_VALIDATION.md`).** When the real model writes an ellipsis inside quotes for every claim, the unchanged verified-quote gate discards them all and the run reads as "nothing evidenced". Not part of this contract; a decision is needed (re-ask on mass-discard, or verify the fragments around an ellipsis).
7. What the model is shown is requirement and exclusion TEXT. Provenance, path, proficiency (beyond its wording), work mode and unresolved items live on the interface and in the outcome; the model is never given them to reconcile, which is also why it cannot reconstruct them. Unresolved items are never sent to the model at all.

## 9. Pipeline connection map (prepared, NOT enabled)
Today (legacy, live): `raw_input` (one text) → intake (`IntakeResult`) → `build_confirmed_hiring_intent` → `to_search_intent` → **legacy `SearchIntent`** → `SearchPlanner.build` → `QueryExpander.expand` → `CapabilityMapper.map` → `mapped_plan` (`api.py` `_confirmed_intent` / `_build_plan` / `start_cycle`) → `run_search_pipeline(intent, mapped_plan, jd_text=…, recruiter_brief=…)` → shadow hook → `run_adaptive_discovery` (provider) → merge → rank → `partition_by_eligibility` (admission) → harvest → `requirement_judge.judge_detailed(candidate, intent, harvest)` → evidence.

| step | today | where the compiled flow connects | status |
|---|---|---|---|
| 1. sources | `snapshot["raw_input"]` is ONE text; the snapshot has no separate brief | the intake must capture the recruiter / HM brief as its own field (`snapshot["recruiter_brief"]`); `api.py` already forwards `snapshot.get("recruiter_brief")` to the pipeline and stores it on the record | **plumbing done; intake capture not done** (a UI/intake change, out of scope) |
| 2. shadow | `run_shadow(search_id, jd_text, mapped_plan, recruiter_brief=…)` (JD + brief; the shadow record notes which sources it had) | — | **done** |
| 3. intent | the shadow calls `extract_structured_intent(jd, brief)` (an extra model call, default off) | the live flow needs the `StructuredHiringIntent` as a first-class product of intake, extracted once from JD + brief and stored with the confirmation | not done |
| 4. compile | `compile_intent(si, SourceTexts(jd, brief))` runs only inside the shadow | run it in `start_cycle` (after the confirmation, before `_build_plan`), keep the `CompiledPlan` with the record | not done |
| 5. provider plan | `mapped_plan` is built by the LEGACY planner / capability mapper from the legacy intent | each path's `CompiledPath.filter_tree` must become the provider request. **No adapter from the compiled filter tree to the provider payload exists** (the shadow never sends it) | **gap** |
| 6. contexts | — | `build_downstream_contexts(plan)` → one `DownstreamContext` per path; `search_intents_from_contexts(contexts, base=legacy_intent)` | adapters exist; not called |
| 7. discovery | one `run_adaptive_discovery` per search | one per path with that path's plan; how N → 50 → 25 is split across paths is **undecided** | **decision needed** |
| 8. merge | `CandidateMerger` | `merge_path_results` first, so a candidate keeps every contributing path id | contract only |
| 9. admission | `partition_by_eligibility(…, alignment_of)` with `build_candidate_evidence(candidate, intent)` | the same call with the candidate's contributing path intent(s); which path's facts apply to a candidate found by several is **undecided** | **decision needed** |
| 10. Judge | `judge_detailed(candidate, intent, harvest)` once | once per contributing path intent (cost scales with paths); the outcome's `checklist` / `exclusion_judgments` stored per path | not done |
| 11. persistence | `candidate.raw_data["__requirement_judgments"]` | add `__exclusion_judgments`, the contributing path ids and the checklist | not done |
| 12. UI | unchanged | none in this phase | out of scope |

Connection order when authorised: (4) compile in `start_cycle` behind a flag → (6) contexts → (10) Judge on the context intent for the legacy-planned search (path-less global context, no provider change) → only then (5), (7)–(9) for per-path provider execution.

## 10. Real-Judge validation (summary; the evidence is `RESULTS_REAL_JUDGE_VALIDATION.md`)
The production Judge model (gpt-4o-mini, temperature 0; requirement and review prompts unchanged and hash-pinned) was run on **synthetic** candidates against the frozen Role 1-3 compiled contexts, 6 runs per scenario, no tuning between runs: 186 runs (+114 for the one documented exclusion-prompt revision), no CrustData, no retrieval.

| contract property | result with the real model |
|---|---|
| nothing provider-shaped, compiler-internal or legacy reaches the model | **holds**: 0 hits over every request received (2157 calls) |
| unresolved items, exclusions and context-only preferences are never asked as positives | **holds**: 0 violations over 162 compiled-context runs |
| path obligations (Path A waives Power Query; Path B requires it; the domain is Path A's only) | **holds**: 13/13 expectations on every run, nothing leaks between paths |
| unsupported `current` not invented; unsupported depth never asked; analogy title not a target | **holds**: 7/7 on every run |
| compiled meaning beats a conflicting legacy meaning (Python required + current, vs unspecified; a company hard line vs a preference) | **holds**: 7/7 on every run, and the legacy-only control arm shows the outcome really changed |
| admission: preferred never gates; alternatives are OR; an unresolved level is not invented | **holds** (deterministic gate, compiled facts) |
| negatives are evaluated | **does NOT yet hold reliably**: the qualified Role 3 audit/tax exclusion works (not broadened), the Role 1 "X is not equivalent to Y" exclusion is read inconsistently (v1 0/6, v2 3/6 on Path A, 0/6 on Path B) |
| proficiency is interpreted correctly | **not strictly**: advanced vs basic Excel and hands-on vs familiar are separated, but the production review pass downgraded `hands-on Java` on a quote that passes for `hands-on Python`, and several borderline verdicts flip between runs |
| work mode / preferred company do not change a requirement verdict | strictly fails (the model flips single items between runs); indistinguishable from the model's own noise once quote-gate-damaged runs are set aside (supplementary) |

Two causes sit outside this contract and are recorded in §8: the existing verified-quote gate discards a whole run when the model writes an ellipsis in its quotes, and a `present` exclusion has no downstream consumer. The results do not show that the Judge is accurate on real profiles.


## 11. Evidence Check validation (summary; the evidence is `RESULTS_EVIDENCE_CHECK_VALIDATION.md`)
72 real runs (3 scenarios, 6 runs each, synthetic candidates, production model, requirement and review prompts unchanged), plus an exploratory diagnostic that is not part of the validation. **Not all scenarios reach 6/6**: B (Role 2 proficiency) 6/6; A (Role 1 negative) 5/6; C (Role 3 proficiency) 0/6.

| property | result |
|---|---|
| every verdict maps to a known check_id; no verdict without one | **holds** (0 violations) |
| evidence cannot be cross-assigned (Java vs Python, Excel vs Power BI) | **holds** (0 accepted quotes outside the subject; the four cross-assignment expectations 6/6) |
| exact quote verification stays active | **holds** (0 accepted quotes fail the gate; 110 of 1054 first-pass claims carried an ellipsis and none was accepted) |
| the narrow retry re-asks only failed checks, once | **holds** (0 violations; 134 checks re-asked, 121 recovered) |
| INSUFFICIENT_EVIDENCE stays distinct | **holds** (6/6) |
| no provider syntax / check_id / recruiter wording reaches the model | **holds** (0 hits in 1053 calls) |
| hands-on Python vs Java (the earlier review-pass failure) | **fixed**: 6/6 on every Role 2 expectation |
| SOC exclusion PRESENT / cyber-incident NOT_PRESENT / security-company analyst NOT broadened | 6/6, 5/6, 6/6 (the miss: an unsupported PRESENT caught by the indicator binding, so INSUFFICIENT_EVIDENCE) |
| advanced Excel vs working-knowledge Power BI, independently | **not reliable**: a stronger statement is not accepted as meeting a weaker depth (0/6), borderline evidence is `partly`, explicit advanced evidence flips 2 in 6 (model capability; the wording hypothesis was tested and refuted) |

Open items for review: a depth-comparison design that does not rely on the small model (classify the depth, compare in code) or a larger model; the over-reaching lexical binding on category skills (47 legitimate verdicts discarded); the policy for an unsupported PRESENT.
