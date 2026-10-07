# COMPILER CONTRACT — `StructuredHiringIntent` → deterministic compiler

Contract version `compiler-contract-1`, implemented by `COMPILER_VERSION v2-2026-10-07` (`backend/services/search_compiler.py`, audit in `compiler_audit.py`).
Status: implemented and verified offline against the frozen Role 1, 2 and 3 intents. The extended fields are read by duck typing; the production schema is NOT promoted.

## 1. The contract

> **If intent means X, the compiler must either ENFORCE X, route X to downstream verification or context, NORMALIZE X deterministically, or declare X UNRESOLVED. It must never silently discard X.**

Intake preserves meaning. The compiler translates it. Taxonomy and the capability map supply knowledge. The compiler contains no model, no provider call, and no semantic judgment: it looks up a capability, applies the one approved transformation, and records what it did.

## 2. Fates (exactly one per meaningful atom)

| fate | meaning |
|---|---|
| `ENFORCED` | a provider-executable filter, correctly enforced |
| `NORMALIZED` | enforced, after a meaning-preserving deterministic normalization (a city alias, a degree surface form, an approved taxonomy title expansion) |
| `VERIFIED_DOWNSTREAM` | not safely provider-enforceable; preserved, at its tier, for the Judge / admission gate |
| `PREFERENCE_CONTEXT` | a preference or context item, intentionally not a hard constraint, preserved and audited |
| `UNRESOLVED` | the compiler cannot yet determine safe execution semantics; preserved verbatim, never remapped, with a reason, and a plan warning |
| `DROPPED_WITH_JUSTIFICATION` | deliberately set aside, with an audit reason (a model-supplied sub-value the source does not state; a JD atom a reconciliation retired; a decision record; classification metadata) |

`SILENTLY_DROPPED` is not a fate. It is the name of the failure: an atom the output does not depend on at all. The compiler may not produce it, and the verification below counts it.

## 3. The per-atom audit

`CompiledPlan.atom_audit` (and `build_audit_record(...)["atom_audit"]`) has one `AtomRecord` per atom:

`atom_id`, `concept`, `scope` (`global` or `path:<id>`), `value`, `provenance` (`state`: `source` | `knowledge` | `model_only` | `unrecorded`; `sources`; `quote`), `strength`, `proficiency`, `relationship`, `fate`, `destination`, `justification`, `components` (sub-values with their own fate, e.g. a location's state), `kind` (`MEANING` | `RECORD` | `METADATA`).

`destination` says where the atom went (`provider filter: …`, `downstream checklist`, `audit row '…'`, `paths[ID].filter_tree`, …). `justification` is mandatory for every record. The older `CompiledPlan.audit` rows (`CompiledConstraint`) are unchanged in shape and still drive `judge_checklist` and `build_audit_record`; they gained `scope` and `semantic` (the checklist text).

## 4. Provenance gate

A provider hard filter is emitted only when the underlying value is **explicitly supported by the JD or recruiter brief** (`basis.sources` contains `jd` or `recruiter_brief`), or by **approved versioned knowledge** (`approved_knowledge`, or a deterministic table such as the city aliases and degree surface forms, or the role-family taxonomy). **Model-only inference is never a hard provider filter**, and a model-supplied component of a supported value is not enforced either.

- Atom level: an atom whose only source is `inferred` never produces a leaf (skill, group, company, experience, education, location, explicit exclusion). A skill or group stays `VERIFIED_DOWNSTREAM`; a company stays `PREFERENCE_CONTEXT` (never a filter); the others are `UNRESOLVED`.
- Component level (location): for a `City, State, Country` entry the city is the stated place; the state and the country are each enforced only if the cited `basis.quote` contains them. JD says `Hyderabad, India`, the model wrote `Hyderabad, Telangana, India`: the compiler emits `country = India` and `city = Hyderabad`, and records `state = Telangana` as `DROPPED_WITH_JUSTIFICATION` ("not in the cited source text and no approved normalization"). There is no approved city→state table, so none is invented.
- **Updated in the runtime-integration phase (see `RUNTIME_INTEGRATION_CONTRACT.md` §1):** the gate is generic over every hard-filter-capable field. `compile_intent(intent, sources=None)` takes the JD / brief; a cited quote is verified against it; an atom with no carrier for provenance (a `role_family` title, a `CompanyScale`) or no basis is classified from the source text (a title is a target, only a comparison, or absent); and an atom without provenance in an intent that records provenance is `absent` and never a hard filter. `unrecorded` (an intent that records provenance nowhere, i.e. a production-shaped intent) keeps its legacy behaviour, and the audit says so. A title the source mentions only as a comparison ("more like a ...") can therefore never reach a title filter, with no role-specific logic.
- The compiler trusts `basis` as verified by the intake validators (verbatim quote checks). It does not re-read the JD.
- Nothing is invented: no company, radius, seniority, title alternative, experience bound, or provider semantic that the intent does not carry.

## 5. Relationship semantics (`UNSPECIFIED != CURRENT`)

`SkillReq.relationship`, `SkillAnyOf.relationship` and `CompanyScale.relationship` default to `None` (the source did not say). `CompanyReq.relationship` keeps its `any` default. An explicit `current`, `past` or `any` keeps its exact meaning.

| relationship | skill / group | company scale |
|---|---|---|
| `current` | required: provider hard filter over the current role's description, headline, summary (`ENFORCED`) | required: hard filter on the current employer's headcount |
| `past` | required: hard filter over past description and title (`ENFORCED`) | `UNRESOLVED` |
| `any` | required: `VERIFIED_DOWNSTREAM` (no verified any-time provider field) | `UNRESOLVED` |
| **`None` (unspecified)** | **`VERIFIED_DOWNSTREAM`, capability `unspecified_relationship`; no current-role filter is invented** | **`UNRESOLVED`** |

(`company_scale` is only provider-verified for the CURRENT employer, so a scale stated as past, any or unspecified is not turned into a current-employer filter.) The production extractor's group-collapse no longer writes `"current"` when the relationship was absent.

## 6. Strength semantics

`required` is a candidate-selection requirement, subject to capability. `preferred` and `context` are **never** hard: for skills, groups, companies, company scale, education, experience and location the compiler emits no filter, keeps the stated strength in the audit, and records the atom as `PREFERENCE_CONTEXT` (a preferred or context skill, domain or evidence signal also stays in the Judge checklist at its tier: supporting / differentiator). `context` is no longer treated as `required`; experience and location no longer ignore strength; a non-required education is no longer invisible. There is no invented ranking boost: where no provider preference mechanism exists the preference is an audited context item. `seniority` strength is recorded and never routes to the provider.

## 7. Sourcing paths

When the intent has `sourcing_paths`, **each path is compiled independently** from its effective view: `CompiledPlan.paths` has one `CompiledPath` (`path_id`, `label`, `strategy`, `filter_tree`, `audit`, `retrieval_title_family`, warnings) per path. The plans are **alternatives** (an OR), never cumulative ANDs; `CompiledPlan.filter_tree` is `{"op": "or", ...}` over the path trees and consumers should execute `paths` independently. Audit rows carry `scope = path:<id>`. A path has no single checklist: `judge_checklist(plan, path_id)` is per path and raises without one. Result merging and deduplication are not implemented.

Inheritance (explicit, identical to the frozen `effective_view`): a path inherits the whole global intent. A singleton it states (`seniority`, `experience`, `location`) **replaces** the global one; a skill or domain with the same case-folded name **replaces** the global entry; everything else it states is **added**. Nothing a path states is visible to another path. A global atom has ONE record: its fate where it applies, naming the paths that inherit it; if every path overrides it, `DROPPED_WITH_JUSTIFICATION` ("overridden by a path-scoped value in every path"). A path atom has one record scoped to its path. Each path is itself an atom (`sourcing_path`, `ENFORCED`, destination `paths[ID].filter_tree`).

## 8. Routing table (by concept)

| concept | fate and destination |
|---|---|
| `role_family` | `ENFORCED` title filter; `NORMALIZED` where an approved taxonomy entry expands it; otherwise the source title verbatim. It carries no provenance field (see §12) |
| `seniority.value` | known level (`seniority.json`) `VERIFIED_DOWNSTREAM` (admission); **unknown level `UNRESOLVED`, kept verbatim, never remapped** (Staff, Senior Manager, Principal …) |
| `seniority.alternatives` | each level as above, in the same admission row |
| `seniority.leadership` | `VERIFIED_DOWNSTREAM`: a checklist item "people leadership or technical leadership" |
| `skill`, `skill_any_of` | §5 and §6; model-only → `VERIFIED_DOWNSTREAM` |
| `skill.proficiency` | `VERIFIED_DOWNSTREAM` (a preferred skill's: `PREFERENCE_CONTEXT`): a checklist item `hands-on X` / `working knowledge of X` / `advanced proficiency in X`, carried verbatim, never provider-filtered |
| `company` | required `ENFORCED`; preferred or context `PREFERENCE_CONTEXT` (never a company filter) |
| `company_scale` | §5 |
| `education.degree` / `.stream` | required `ENFORCED` (`NORMALIZED` for approved degree forms); otherwise `PREFERENCE_CONTEXT` with an audit row. Literal strings are unchanged (a taxonomy item) |
| `experience.min` / `.max` | required `ENFORCED`; otherwise `PREFERENCE_CONTEXT` |
| `location.entry` | required `ENFORCED` / `NORMALIZED` (§4 for components); otherwise `PREFERENCE_CONTEXT`. A multi-entry or 2-part place compiles to its cities only (existing rule); the other components are recorded `DROPPED_WITH_JUSTIFICATION` |
| `location.country` | required `ENFORCED` (a country filter; OR with `entries` if both are present) |
| `location.radius` | required `ENFORCED` (`geo_distance`) |
| `location.remote` | `allowed`: `PREFERENCE_CONTEXT` (an allowance; it does not relax a place filter); `not_allowed`: `VERIFIED_DOWNSTREAM` |
| `location.work_mode` | capability map: no work-mode filter, not verifiable from the profile → **`UNRESOLVED`** (route `disclose`), the typed value preserved and never mapped to another mode; a non-required work mode is `PREFERENCE_CONTEXT`. Never part of geography |
| `exclusions` (company / title) | `ENFORCED`; an unsupported kind is `UNRESOLVED` |
| `semantic_exclusions` | `VERIFIED_DOWNSTREAM` as an **exclusion** row (`downstream_exclusion`), listed by `exclusion_checklist`, **never** a company or title NOT-IN filter and never a positive requirement |
| `domain` | required `VERIFIED_DOWNSTREAM`; preferred or context `PREFERENCE_CONTEXT`; never a keyword or company filter |
| `evidence_signals` | required `VERIFIED_DOWNSTREAM`; otherwise `PREFERENCE_CONTEXT`; all in the Judge checklist at their tier |
| `sourcing_paths` | §7 |
| `reconciliations` | §9 |
| `role_archetype` | `DROPPED_WITH_JUSTIFICATION` (`METADATA`: classification, no execution meaning) |
| `basis` (provenance) | carried as the `provenance` column of every atom record; not an atom with a fate |

## 9. Reconciliations

A reconciliation is a decision record (`kind = RECORD`): `DROPPED_WITH_JUSTIFICATION` (the final meaning is carried by the surviving atoms), or `UNRESOLVED` if its action is `unresolved` (surfaced, a plan warning, no side enforced). The record is kept in full in the audit. A JD atom a reconciliation retired must not stay active: a **required atom that rests on the JD alone, whose quoted text overlaps the reconciliation's `jd_quote`, and whose value the reconciliation's `topic` names** is retired in the reconciliation's scope (that path, or everywhere if `path_id` is null): `DROPPED_WITH_JUSTIFICATION`, no filter, no checklist item, the other paths unaffected. For `unresolved` the atom is `UNRESOLVED` and enforced on neither side. The match is deliberately conservative (precision over recall): an atom the brief also supports, an atom at a lower strength, and an atom the topic does not name (several atoms often share one JD sentence) are never retired, because retiring the wrong atom would silently weaken the search.

## 10. Verification (how "never silently discarded" is checked)

Not by trusting `atom_audit`. `backend/experiments/compiler_contract/hardened_verify.py` re-enumerates the atoms from the schema, removes each one, recompiles with the live compiler and diffs the whole output (provider plan, every audit row, the checklists, the per-atom audit, the paths, warnings). An empty diff is a silent drop; a declared fate the diff does not bear out (an `ENFORCED` atom whose leaf does not move) is an inconsistency. It also audits the provenance gate independently and has a test proving it catches a planted drop. Tests: `tests/test_compiler_contract.py` (matrix A–O).

## 11. Backward compatibility

A production-shaped `StructuredHiringIntent` (no extension fields, no `basis`) compiles to the same filter tree, the same audit rows and the same checklist as before for the two anchors, and the existing compiler, audit, shadow, capability and intent tests pass unchanged. Deliberate behaviour changes: unspecified relationship is no longer `current`; `context` strength is no longer hard; experience / location / education honour strength; a non-required education has an audit row; an explicit `past`/`any` company scale is `UNRESOLVED` instead of a current-employer filter; `proficiency` has a checklist item (the provider plan is unchanged by it); `COMPILER_VERSION` is `v2-2026-10-07`.

## 12. Known limits (not solved here; recorded)

- An explicit `current` the source does not support is still enforced as stated (an explicit meaning is never altered); the intake validator `unsupported_current_relationship` is not run at the compiler boundary. (The analogy-title limit recorded in the first version of this file is closed by the source-text classification above.)
- The capability map has no entry for the any-time description field, so required `any` and unspecified skills are never provider-enforced; `work_mode` has no provider or profile capability.
- Taxonomy: two role families; degree surface forms for three technical degrees; the approved level list is `seniority.json` only.
- The compiled plan is built in shadow mode only; path results are not merged or deduplicated; the Judge does not yet consume `exclusion_checklist`.
