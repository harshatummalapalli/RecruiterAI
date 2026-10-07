# COMPILER CONTRACT EXPERIMENT — pre-registered expectations (written BEFORE the baseline capture)

Offline, measurement only. No model call, no CrustData, no Harvest, no retrieval, no production/provider/compiler change, no schema change.
The unchanged `backend.services.search_compiler.compile_intent` (COMPILER_VERSION `v1-2026-10-02`) is run on the frozen Role 1, 2 and 3 experimental
intents. Everything below was decided from reading the compiler, the capability map and the schema, **before** any compile output was looked at.

Frozen inputs (read-only, never modified):
- Role 1: `intake_strategy/results/experimental_v3/experimental_run{1..5}.json` (the accepted Role 1 representation, prompt_v3)
- Role 2: `intake_strategy/results/role2/role2_run{1..5}.json` (prompt_v3; produced BEFORE `advanced` and `work_mode` existed)
- Role 3: `intake_strategy/results/role3/role3_run{1..5}.json` (prompt_v4)
- ground truths: `DESIGN.md` FROZEN section (Role 1), `ROLE2_GROUND_TRUTH.md`, `ROLE3_GROUND_TRUTH.md`

Pinned compiler-side files (a test fails if any changes): `search_compiler.py` sha256 `38d0fc14…81cd`, `compiler_audit.py` `ccda5898…b86d`,
`crustdata_capabilities.py` `c2038c57…6148`, `role_family_taxonomy.py` `8d828121…eca25`, `structured_intent.py` `fe765fd1…b924`, `seniority.json` `106b5521…4534`.

## 1. Method (deterministic; no model)

**Destination of an atom = the output delta when the atom is ablated.** For every meaning atom in an intent (a skill, one location entry, one
degree stream, a proficiency value, a work mode, a sourcing path, a semantic exclusion, …) the experiment removes (or, for a qualifier, resets)
that single atom, recompiles with the unchanged compiler, and diffs the whole output (provider filter leaves, every audit row, retrieval titles,
warnings, normalizations, downstream checklist). The delta IS where the atom went. **An empty delta means the compiler output does not depend on
the atom: it has no destination.** This is a counterfactual proof, not a text match, so it cannot be fooled by a similar string appearing elsewhere.

A second, independent mechanism: a read-set tracer wraps the intent and records every field path the compiler reads. A field path in the schema
that is never read cannot influence the output. The two must agree (a test asserts it).

**Fate** of an atom, from its destination delta:
| fate | rule |
|---|---|
| ENFORCED | the delta contains a provider filter leaf |
| NORMALIZED | enforced, and the provider value differs from the intent value by a deterministic mapping (city alias, degree surface form, taxonomy title expansion) |
| VERIFIED_DOWNSTREAM | the delta is an audit row routed `downstream_evidence` or `admission_level_fit` (preserved for the Judge / admission gate) |
| PREFERENCE_CONTEXT | the delta is an audit row routed `context_or_evidence` (a preference kept as context, intentionally not a hard filter) |
| UNRESOLVED | an audit row says execution semantics cannot be determined (none is expected to exist) |
| DROPPED_WITH_JUSTIFICATION | no delta, but the compiler output carries an explicit audit reason (none is expected to exist) |
| SILENTLY_DROPPED | empty delta and no audit reason: **a compiler-contract failure** |

Atoms are classed MEANING, DECISION RECORD (`reconciliations`) or METADATA (`basis`, `role_archetype`, path labels). The drop count that decides
the acceptance criterion is over MEANING atoms; the other two classes are reported separately so a reviewer can re-count with them.

**Deviation** is independent of fate and is what "strengthening / weakening" means here:
- STRENGTHENED: the atom's strength is `preferred`/`context` (or its scope is a path, or its relationship is not `current`) but the output enforces it as a provider hard filter on the whole intent.
- WEAKENED: the atom is `required` but its destination is only context (or its provider enforcement is narrower than stated, for example a multi-entry location losing state and country).
- SCOPE_CHANGED: a path-scoped atom is applied globally, or a global atom is applied to a path that overrides it.
- Path semantics are compared by compiling each path's effective view (global + that path's overrides, via `effective_view`) with the SAME unchanged compiler and diffing the filter-leaf sets against the plan compiled from the whole intent. A path-aware plan is OR over paths; a flat plan is the AND of the global atoms.

## 2. Expected fate per concept (what a healthy compiler does; fixed now)
A concept does not have to be a provider filter. The acceptance criterion is "no meaningful intent is silently lost or silently strengthened".

| concept | expected fate |
|---|---|
| `role_family` | ENFORCED (title filter), NORMALIZED where a taxonomy entry exists, source title kept verbatim otherwise; a comparison title must never be a target title |
| `seniority.value` | VERIFIED_DOWNSTREAM (admission). An unknown level (Staff, Senior Manager) is carried exactly as written and never mapped to another level |
| `seniority.leadership` | VERIFIED_DOWNSTREAM (evidence text) |
| `seniority.alternatives` | VERIFIED_DOWNSTREAM (an OR over levels at admission) |
| skill, `required`, relationship `current` | ENFORCED only where the source states current use |
| skill, `required`, relationship `any` / `past` | routed by the capability map; if not provider-verifiable, VERIFIED_DOWNSTREAM |
| skill, `preferred` / `context` | PREFERENCE_CONTEXT or VERIFIED_DOWNSTREAM with its tier; never a hard filter |
| `skill.proficiency` | VERIFIED_DOWNSTREAM (the depth must travel with the skill requirement; no provider field states depth) |
| `skill_any_of` | as a skill, as an OR group |
| `companies` `preferred` | PREFERENCE_CONTEXT, never a company filter; `required` ENFORCED |
| `exclusions` (company / title) | ENFORCED |
| `semantic_exclusions` | VERIFIED_DOWNSTREAM (a negative check by the Judge); **never** converted to a company or title filter |
| `domain` `required` | VERIFIED_DOWNSTREAM; `preferred` / `context` PREFERENCE_CONTEXT |
| `evidence_signals` | VERIFIED_DOWNSTREAM with their tier |
| `education` `required` | ENFORCED, NORMALIZED; `preferred` PREFERENCE_CONTEXT (and it must still be visible in the audit) |
| `experience` | `required` ENFORCED; `preferred` PREFERENCE_CONTEXT; a path-scoped value stays scoped to its path |
| `location.entries` | ENFORCED (OR over entries) |
| `location.countries` | ENFORCED (a country filter); an `India`-wide path must not vanish |
| `location.remote` | an allowance that widens a path: audited (PREFERENCE_CONTEXT or VERIFIED_DOWNSTREAM), never silent |
| `location.work_mode` | VERIFIED_DOWNSTREAM (the capability map says there is no work-mode filter on person search: "disclose context-only") |
| `sourcing_paths` | provider-supported parts ENFORCED as an OR over per-path plans, the rest VERIFIED_DOWNSTREAM; at minimum UNRESOLVED with an audit row. **Flattening paths into one AND is a semantic compiler failure** |
| `reconciliations` | DROPPED_WITH_JUSTIFICATION where the result lives in surviving atoms (with an audit reason); `unresolved` ones surfaced |
| `basis` (provenance) | the audit row carries the claiming source, or the record is bound to the intent by `intent_hash` |
| `role_archetype` | DROPPED_WITH_JUSTIFICATION (classification metadata, no execution meaning) |

## 3. Predictions (recorded before the run; each is a falsifiable claim about the unchanged compiler)
1. `compile_intent` reads none of: `sourcing_paths`, `domain`, `semantic_exclusions`, `reconciliations`, `skill.proficiency`, `seniority.leadership`,
   `seniority.alternatives`, `location.countries`, `location.remote`, `location.work_mode`, `basis`, `role_archetype`. Every atom of those is SILENTLY_DROPPED.
2. Because Role 1's geography lives in `countries` and in path locations, the Role 1 plans will carry **no geography filter at all**.
3. The compiler never reads `strength` for `experience` or `location`: a `preferred` value would still be a provider hard filter (STRENGTHENED).
4. A `preferred` education leaves no audit row and no leaf: SILENTLY_DROPPED, in production intents too.
5. `SkillReq.relationship` defaults to `current` in the production model. The compiler treats `current` as a hard OR over current-role description, headline and summary for a required skill. `any` and `past` are routed differently, so an omitted relationship becomes a hard filter.
6. A multi-entry location keeps only the city and loses state and country.
7. Required `any` skills route to `downstream_evidence` because their probe field (`experience.employment_details.description`) is not in the capability map: a CAPABILITY MAP gap, not a Judge decision.
8. Role 2's `Forward Deployed Engineer` title (in the stored prompt_v3 intents) reaches the title filter, because the compiler has no way to know a title is an analogy: PROVENANCE / VALIDATION.
9. "Senior Manager" and "Staff" are carried verbatim by the compiler (no mapping), but the downstream level marker may read "Senior Manager" as "senior": recorded as a downstream consumer observation, not changed.
10. No concept is converted into a company or title filter (no `(!)` or `not_in` leaf) and no preferred company becomes a hard filter.

## 4. Critical checks (what is verified per role; each is judged conditionally)
Each check records (a) whether the stored intent CARRIES the concept (so an extraction miss is not blamed on the compiler), (b) what the compiler did with it,
(c) PASS / FAIL / NOT_TESTABLE and the gap type.
- **Role 1:** Path A vs Path B structure; path-specific geography; path-specific requirements; Power Query waiver on Path A; Path B 6+ years; semantic security/SOC exclusion; the security-firm qualifier; leadership people OR technical; domain preference; India country; remote allowed; whether path logic is flattened into one AND.
- **Role 2:** advanced proficiency; working/hands-on distinction; hybrid; semantic role/work-type requirements; unknown "Staff" seniority; title analogy not a target title; relationship semantics. The stored Role 2 intents pre-date `advanced` and `work_mode`, so those two are exercised by (i) the real Role 3 intents and (ii) one **labelled synthetic overlay** on the Role 2 intents (Python/Java `advanced`, `work_mode=hybrid`, seniority `Staff`), applied from `ROLE2_GROUND_TRUTH.md`, not an extraction result.
- **Role 3:** Hyderabad; hybrid; 8–12 years; advanced Excel; working-knowledge Power BI; companies are preferences and never hard company filters; the audit/tax/bookkeeping exclusion; "Senior Manager" identity.

## 5. Temporal relationship safety (section 8 of the brief)
Probe matrix over {skill, skill group, company, company scale} × {`current`, `past`, `any`, omitted} × {`required`, `preferred`, `context`}, using the unchanged
compiler and the production models. It answers: A explicit current; B explicit any/past; C omitted; D does omission default to current; E can that create an
unintended hard filter. **Rule fixed now:** if the compiler (or the stored intent) cannot distinguish "source did not specify" from "source explicitly requires
current", that is a HIGH PRIORITY DESIGN GAP. The raw model outputs of all 15 runs are checked for how often `relationship` was actually omitted.

## 6. Gap-type assignment (fixed now)
| type | used when |
|---|---|
| COMPILER LOGIC | the intent carries the information and `compile_intent` does not read it, reads it wrongly, or ignores its strength / scope |
| CAPABILITY MAP | the provider capability or an unmapped field is wrongly represented in `crustdata_capabilities` |
| TAXONOMY | a role / title equivalence or level is missing |
| PROVENANCE / VALIDATION | the compiler cannot tell whether an atom is authoritative (an analogy title, an unsupported `current`) |
| INTENT REPRESENTATION | the intent genuinely cannot say it (for example, omitted and explicit `current` are the same value after validation) |

## 7. What this experiment will not do
No compiler, schema, prompt, capability-map, taxonomy or provider change; no model run; no retrieval. "Smallest compiler changes" in the report are
RECOMMENDATIONS with the evidence that motivates them, not implementations. If an unchanged-compiler call is used to show what a path-aware or
downstream-routing compiler could do (compiling each path's effective view separately), that is measurement, not a change.
