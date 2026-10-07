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
| `exclusions` | `must_not_have` | semantic exclusions (the profile the candidate must NOT have) | received and visible; **not evaluated** (the Judge has no negative verdict yet: §8) |
| `preferences` | `prefer` | `PREFERENCE_CONTEXT` atoms; never in the core tier | the ones routed to evidence are judged at their own (non-core) tier; context-only ones (a preferred company, an education) are carried, not judged |
| `unresolved` | `undecided` | `UNRESOLVED` atoms with the reason (an unknown level, a work mode no provider filters, an unsupported qualifier) | no, never; visible, never invented |
| `already_enforced` | informational | what the provider already enforced | no (not re-required independently) |

Each `ChecklistItem`: `item_id` (the compiled atom id), `concept`, `text` (recruiter meaning), `polarity`, `tier`, `judged`, `strength`, `proficiency` (`hands_on` / `working_knowledge` / `advanced`, also in the text), `relationship` (`None` = unspecified, never read as current), `fate`, `path_id`, `inherited`, `provenance` (`state`, `sources`, `quote`), `reason`, `alternatives`, `unsupported_qualifiers` (the claim the source did not support, and why). Work mode is an item with `concept == "location.work_mode"` (verified, preferred or unresolved by its fate), exposed as `JudgeChecklist.work_mode`; proficiencies as `.proficiencies`.

Two rules in the checklist: (a) leadership kinds the source accepts as alternatives ("people **or** technical") are **one** item with `alternatives`, so an OR is not turned into an AND; (b) a preference that would inherit a required strength (the "remote is acceptable" allowance inside a required place) is carried without the core tier.

`JudgeOutcome` additionally records `input_source`, the `checklist` the Judge was given, and the `disagreements`. The scripted/real model sees only requirement texts (no provenance, no path); provenance and path live on the interface and in the outcome. The verified-quote gate and the review pass are unchanged.

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
* **A preference never gates:** a preferred level is `ungated` and visible. (The legacy path gated on it. This is a documented consequence of "compiled wins", tested: a `Director` is not excluded by a *preferred* Senior level.)
* **Accepted alternative levels** use the **unchanged** level rule once per accepted level: `aligned` at any accepted level is `aligned`; `above` / `below` stands only if every accepted level agrees; otherwise `unclear` (admission never gates on it). With no alternatives (always so for a legacy intent) this is exactly the old rule.

## 8. Known limits (recorded, not hidden)
1. **No negative verdict.** The Judge receives semantic exclusions but cannot answer "has the excluded profile"; exclusions are visible on the interface and in the outcome, not evaluated. (Gap code `NO_NEGATIVE_SLOT` is closed at the input; the verdict is the open half.)
2. **Per-path pipeline execution is not wired.** `search_pipeline` still runs one search per intent and the shadow does not hand the compiled context (or the recruiter brief) to it. The seam is live in the code but dormant in production until the pipeline sets `compiled_context` once per path (runtime contract §8.1). Nothing is deployed.
3. `MatchedSignal.provenance` and `CandidateEvidence.contributing_path_ids` (runtime contract §8.4) are not added; provenance and path are on the Judge interface and the outcome.
4. The depth / alternative / leadership / mode / distance checks are lexical. They are deliberately conservative: a depth the model inferred from a verb ("build and deploy" → hands-on) is withheld as `UNRESOLVED` (visible, with the claim) rather than required.
5. `JudgeChecklist` groups leadership kinds; `to_judge_signals` (the earlier adapter) lists them separately. They agree on everything else (tested).
