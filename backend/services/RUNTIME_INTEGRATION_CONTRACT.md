# RUNTIME INTEGRATION CONTRACT — compiled plan → downstream context

Companion to `COMPILER_CONTRACT.md`. That contract says the compiler must never silently discard meaning. This one says the meaning must also **survive the compiler boundary**: the compiled plan is for the provider and the audit; everything the compiler did not make a provider filter must reach a downstream consumer as an explicit, per-path, provenance-bearing entry, or be recorded as a gap. Offline, structural, no provider, no model, no scoring.

```
StructuredHiringIntent (+ the JD / brief it was extracted from)
        │  compile_intent(intent, sources)         provenance gate (§1)
        ▼
CompiledPlan  ── plan.paths[]  one independent plan per sourcing path (alternatives)
        │  build_downstream_contexts(plan)
        ▼
DownstreamContext[]   one per path (or one global)   ── to_judge_signals(ctx)  → legacy Judge input shape (adapter)
        │                                             ── legacy_consumer_gaps(ctx) → what today's consumers cannot accept
        ▼
Judge / admission / recruiter UI      (today: still the legacy `SearchIntent`; see §7)
        ▲
merge_path_results(per-path results)   one record per candidate, all contributing path ids (§6)
```

## 1. Provenance gate (generic)
A provider hard filter requires provenance: **source-supported** (the JD or recruiter brief states it) or **approved normalization** (versioned knowledge: the city aliases, degree surface forms, the role-family taxonomy). Nothing role-specific is in the code.

| provenance state | meaning | may be a hard filter |
|---|---|---|
| `source` | the atom's `basis` cites the JD / brief (its quote is verified against the supplied text), OR the source text itself states it (classified: `classified: source_text`) | yes |
| `knowledge` | the basis cites approved knowledge | yes |
| `unrecorded` | the intent records provenance NOWHERE (a legacy, production-shaped intent) | yes, only in a legacy intent; the audit says so |
| `model_only` | the only source is `inferred` | **no** |
| `absent` | the intent records provenance but this atom has none, and the source text does not state it (or no text was supplied) | **no** |
| `comparison` | the source mentions a title only as a comparison ("more like", "similar to", "resembles", "akin to", "comparable to", "reminiscent of", "someone like", "like a") | **no** |
| `unverified_quote` | the cited quote is not in the supplied source text | **no** |

Rules. (a) Atoms with a `basis` use it; a `source` quote is verified against the supplied text (punctuation- and case-insensitive). (b) Atoms with no carrier for one (a `role_family` title, a `CompanyScale`) or no basis are classified from the source text with the intake's own stated-in-one-sentence check (`requirement_provenance.stated_evidence`; a headcount by its number). (c) A title is `target` if any sentence that states it does not introduce it with a comparison cue; `comparison` if every such sentence does; else `absent`. (d) With no source text, an atom without provenance is `unrecorded` in a legacy intent and `absent` in an intent that records provenance. (e) A blocked atom is never dropped: it keeps a fate (`UNRESOLVED`, `VERIFIED_DOWNSTREAM` for a skill, `PREFERENCE_CONTEXT` for a company) and the reason. (f) Location components (a state, a country) are enforced only if the cited quote contains them. **The runtime must pass the source text** (`compile_intent(intent, SourceTexts(jd=..., recruiter_brief=...))`); the shadow audit does.

## 2. Relationship semantics (unchanged by this phase)
`None` (unspecified) is never `current`. Explicit `current`, `past`, `any` keep their meaning in the model, extractor, compiler, atom audit, downstream context and Judge adapter. The set of production files that read a relationship is pinned by a test.

## 3. The downstream context (`DownstreamContext`)
One per sourcing path, built from that path's OWN atoms (`CompiledPath.atom_audit`), or one global context when there are no paths. **Never merged across paths.** Fields: `path_id`, `strategy`, `label`, `provider_plan` (this path's own filter tree), `entries`, `provenance_mode`, `sources_supplied`, `warnings`. Views: `inherited` (stated globally, applied here), `path_specific` (stated in this path), `requirements`, `exclusions`, `preferences`, `unresolved`, `location` (entries, countries, remote and work mode, kept separate).

One `ContextEntry` per atom that applies in the context: `atom_id`, `concept`, `value`, `kind`, `scope` (where it was stated), `inherited`, `text` (the recruiter-meaning text), `tier`, `strength`, `proficiency`, `relationship`, `fate`, `destination`, `justification`, `route`, `provenance` (`state`, `sources`, `quote`), `components`.

| fate | entry `kind` | what a consumer does with it |
|---|---|---|
| `ENFORCED` / `NORMALIZED` | `provider_enforced` | already applied by the provider; kept for audit |
| `VERIFIED_DOWNSTREAM` (route `downstream_evidence`) | `judge_requirement` | the Judge checks it, at its tier (a proficiency, leadership kind, domain, required skill, evidence signal) |
| `VERIFIED_DOWNSTREAM` (route `downstream_exclusion`) | `judge_exclusion` | the Judge checks the candidate does NOT have this profile (a semantic exclusion) |
| `VERIFIED_DOWNSTREAM` (route `admission_level_fit`) | `admission` | the admission gate's level input (a known seniority level and its alternatives) |
| `PREFERENCE_CONTEXT` | `preference` | preserved as a preference: a company, an education, a place, a context domain. Never required, never ranked |
| `UNRESOLVED` | `unresolved` | visible and not decided: an unknown level, a work mode no provider can filter, an analogy title |
| `DROPPED_WITH_JUSTIFICATION` | `record` / `justified_drop` | a decision record, classification metadata, or a model-supplied sub-value, with its reason |
| (the path itself) | `path` | the path's own identity |

Guarantees (tested over the 15 frozen intents): every `VERIFIED_DOWNSTREAM` atom has an entry in every context it applies to; a global atom reaches EVERY path that inherits it (decided independently from the frozen inheritance rule); a path atom reaches ONLY its own path; every entry carries provenance; preferences are never hardened; unresolved values stay visible; nothing is scored (no entry, context or merged record has a score, rank, weight or boost field).

## 4. The existing-consumer adapter
`to_judge_signals(ctx)` renders a context as the existing Judge's input shape: `{"core": [...], "supporting": [...], "differentiator": [...]}` (positive signals by tier, exactly the entries the compiler routed `downstream_evidence`). It adds nothing and scores nothing, and per path it equals `judge_checklist(plan, path_id)` (the checklist holds the leadership kinds as one item, the context as one entry per kind). It cannot carry negatives, unresolved items, provenance or the path.

## 5. Legacy consumer gaps (DOWNSTREAM CONTRACT GAP)
`legacy_consumer_gaps(ctx)` lists, atom by atom, what the CURRENT consumer interface cannot accept. The entry stays in the context; the gap is recorded, never swallowed.

| code | meaning |
|---|---|
| `NO_NEGATIVE_SLOT` | the Judge's input cannot say "must NOT have this profile" |
| `NO_UNRESOLVED_SLOT` | no consumer has a place for an unresolved item |
| `ADMISSION_READS_LEGACY_INTENT` | admission reads `intent.role.seniority` / `experience`, not the compiled plan |
| `PREFERENCE_NOT_FORWARDED` | a preference kept as context is not forwarded to any Judge signal or ranking input |
| `NO_PROVENANCE_FIELD` (structural) | signals are bare strings |
| `NO_PATH_CONTEXT` (structural) | `SearchIntent` is one search; it has no path |

## 6. Path merge contract (`merge_path_results`; data contract only, nothing is merged live)
Input: per-path candidate lists. Output: one `MergedCandidateEvidence` per candidate: `identity`, `identity_resolved`, `contributing_path_ids` (all of them, in plan path order), `per_path` (each path's own, unmodified payload), `obligations_by_path` (each contributing path's own context entries, kept apart). Identity is the pipeline's existing deduplication key (candidate id, else profile URL, else email, else normalized name+company). A candidate with no identity key is kept and flagged, never silently merged or dropped. **No path is ranked above another, no path score exists, no provider score is merged or chosen**, and the output order (sorted by identity) does not depend on the order the paths were given. A candidate found by Path A and Path B is checked against A's context and B's context separately, never against a union.

## 7. What the current Judge, admission and pipeline consume (LEGACY DOWNSTREAM CONSUMER)
| consumer | reads | does NOT read |
|---|---|---|
| `RequirementJudge._judge` | `SearchIntent.core_signals`, `supporting_signals`, `differentiator_signals` (strings) | the compiled plan, a path, an exclusion, provenance, proficiency (except as text), work mode, unresolved items |
| `candidate_evidence_builder` → `RoleAlignment` | `intent.role.seniority`, `experience.minimum_years` | the compiled `seniority` / `alternatives` / `leadership` atoms |
| `admission.evaluate_eligibility` | `RoleAlignment.level_fit` / `experience_floor` (already computed) | the compiled plan |
| `search_pipeline` | `mapped_plan` (legacy); calls `run_shadow(search_id, jd_text, mapped_plan)` | the recruiter brief is not passed to the shadow; the compiled plan never leaves the shadow |

A test fails the day any of these starts referencing the compiled plan, so this table cannot silently go stale.

## 8. Smallest interface changes for the compiled plan to become the source of truth (NOT made here)
1. **Pipeline hook.** `run_shadow` already compiles with the source text; pass the recruiter brief too, keep the compiled plan beyond the shadow, and run the existing search once per `DownstreamContext` (per path) with that path's `provider_plan`.
2. **Judge input.** Build a per-path `SearchIntent` from the context with `to_judge_signals` (no Judge change). Add one field for the missing slot: `SearchIntent.exclusion_signals: List[str]` (from `judge_exclusion` entries) and teach the Judge one more verdict, "has the excluded profile".
3. **Admission input.** Fill `intent.role.seniority` and the experience floor from the context's `admission` entries; an `UNRESOLVED` level stays ungated (admission already never gates on an unclear level) and visible.
4. **Carry provenance and path.** Optional `provenance` on `MatchedSignal`, and `contributing_path_ids` on `CandidateEvidence`, filled from `MergedCandidateEvidence`.
5. **Merge.** Replace nothing: call `merge_path_results` on the per-path results before `CandidateMerger`, so a candidate keeps every contributing path id; the existing score handling stays as is (no path score).
6. **Persist.** Store `atom_audit` and the contexts in the search record (the shadow audit record already includes them).

## 9. Unresolved by design
`Staff`, `Senior Manager`, `Principal`, `Director` (no approved level mapping: `UNRESOLVED`, kept verbatim); work mode (no provider filter, not verifiable from the profile); the any-time skill field (not in the capability map); education literals; the two-entry role-family taxonomy. None of these is mapped here to make a test pass.
