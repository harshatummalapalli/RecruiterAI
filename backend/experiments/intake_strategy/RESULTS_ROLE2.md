# RESULTS — Role 2 cross-role validation

**NEW REPRESENTATION GAP FOUND**

Two meanings the Role 2 sources state cannot be expressed by the frozen schema: an "advanced" depth of proficiency, and a "Hybrid"
working basis. Both were predicted from the schema before the run (`ROLE2_GROUND_TRUTH.md`, committed in `c15a734`) and the model
could not state them in any run. Separately, the model showed **structural** discipline but not **content-level** discipline
(details below). Two roles still do not prove generality; nothing here is "architecture proven".

Frozen inputs: `prompt_v3.txt` (sha256 `480a2448…691a`, pinned by a test), the frozen schema and validators, same model
(`gpt-6.1-sol`, medium), streamed, five runs, no prompt change, no retry needed (5/5 parsed). 24.2k input / 28.4k output tokens,
72-78 s per run. Role 1 files, ground truth and prompt are untouched (a test pins their hashes). Evidence: `results/role2/`,
`results/role2_analysis.json`. Reproduce the tables offline with `python -m backend.experiments.intake_strategy.compare_role2`.

## What to distrust (read first)
1. **I wrote the ground truth and the evaluator, and you have not reviewed them.** They were committed before any model call, but
   if you disagree with a decision below the verdicts move. The ones that matter most: "Forward Deployed Engineer" is an analogy
   and not a title (drives `fidelity_role_family`, `no_preference_hardened`); `domain` at required strength is over-application
   (`no_role1_concepts`); proficiency is allowed only where the JD states a depth (`no_invented_proficiency`); a JD responsibility
   hardened into a required atom is PARTIAL.
2. **One evaluator bug, found after the run and corrected.** The pre-registered `fidelity_brief_profile` matched "proof of concept"
   but not the plural "proofs of concept" that all five runs wrote, so it scored PARTIAL x5 for a fact that was present. The fix is
   in the repo with a regression test. Both columns are shown. No other assertion changed.
3. **Post-hoc observations are labelled and are not assertions** (AKS+EKS, responsibility-sourced signals, the hands-on breakdown,
   the depth-cue check, the compiler observations). They were found by reading the intents.
4. **The proficiency rule is strict and I tested a lenient reading** (section E). The verdict does not change.
5. **Two roles, one model, five runs.** The errors were identical in all five runs, so this is a stability of errors, not noise.

## A. New-role ground truth (summary; the full file is `ROLE2_GROUND_TRUTH.md`)
One sourcing strategy, **no paths**. Hard requirements: 12+ years; Bachelor's/Master's in CS/IT/SE/related; Python AND Java
("advanced proficiency"); production GenAI (hands-on); LLM/RAG/Agentic AI/Prompt Engineering/MCP/A2A; TensorFlow/PyTorch/
scikit-learn "or similar" (OR); Azure and/or AWS (OR); DevOps/CI-CD examples; React/Bootstrap; Snowflake/Databricks; data integration
topics; API integration. "Familiarity" (weaker): Azure DevOps, Jira, metadata/governance. Brief: IC engineer, client-problem solution
design, POCs, existing teams/products; Hyderabad; Hybrid. Title: Staff Software Engineer / Solution Architect. **No preference wording
anywhere, no exclusion, no company, no conditional anything, no JD-vs-brief contradiction.**

## B. The five extracted intents
All five parse and share the same shape (`results/role2/role2_run{1..5}.json`; run 1 is representative):
- `sourcing_paths` [], `exclusions` [], `semantic_exclusions` [], `companies` [], `reconciliations` [] in **5/5**.
- `role_family` = Software Engineer, Solution Architect, **Forward Deployed Engineer** (5/5). `seniority` null (5/5); "Staff-level…" lives
  in an evidence signal. `experience` 12 required, `education` required, `location` Hyderabad / `remote` null / "hybrid" in an evidence signal.
- 36-43 skills, 2 OR groups (Azure/AWS; TensorFlow/PyTorch/scikit-learn/similar) kept correctly, 21-27 evidence signals (all `required`),
  2-3 required `domain` atoms plus 0-1 `context` ("Enterprise-scale applications", "Enterprise data integration across SaaS applications", "Production
  generative AI solutions"). 15-20 skills carry `hands_on`.
- Provenance: every atom `verified`, 0 unsupported, 0 misattributed, 0 validator errors.

## C. Five-run stability
Stable 5/5: paths (0), exclusions (0), companies (0), role family, seniority (null), experience, education, location (+ remote null),
both OR groups kept, 28/28 stated facts present, no reconciliations, 0 validator errors, **and the identical set of failing assertions**.
Not stable: `domain` atoms 2-4 per run; skills 36-43; evidence signals 21-27; `hands_on` skills 15-20; and (outside the gated
components, found in the compiler observation) required skills with `relationship: current`: **10, 10, 5, 1, 6** (runs 1-5). That last one is a
cross-role instability that reaches the compiler (D2).

## D. Gold assertions (27; pre-registered evaluator vs corrected)
| assertion | as run | corrected | class |
|---|---|---|---|
| experience 12+ required / education / Python AND Java / GenAI + AI concepts / DevOps-UI-data-APIs / familiarity items / soft + engineering | PASS x5 each | same | |
| `fidelity_cloud_or`, `fidelity_ml_libraries_or` | PASS x5 | PASS x5 | |
| `fidelity_geography_hyderabad`, `strength_requirements_not_weakened` | PASS x5 | PASS x5 | |
| `no_second_path`, `no_invented_exclusion`, `no_company_filter` | PASS x5 | PASS x5 | |
| `reconciliation_discipline`, `provenance_preserved`, `provenance_location_from_brief`, `generic_validators_clean` | PASS x5 | PASS x5 | |
| `fidelity_brief_profile` | PARTIAL x5 | **PASS x5** (evaluator bug) | |
| `fidelity_role_family` | FAIL x5 | FAIL x5 | EXTRACTION |
| `no_preference_hardened` | FAIL x5 | FAIL x5 | EXTRACTION (same fact: the analogy became a title) |
| `no_role1_concepts` | FAIL x5 | FAIL x5 | EXTRACTION (`domain` at required) |
| `no_invented_proficiency` | FAIL x5 | FAIL x5 | EXTRACTION |
| `seniority_staff` | PARTIAL x5 | PARTIAL x5 | EXTRACTION (typed level dropped; **no stronger level was invented**) |
| `no_hard_seniority_from_responsibilities` | PARTIAL x5 | PARTIAL x5 | EXTRACTION (responsibility hardened to a required atom; no seniority or `leadership` invented) |
| `advanced_proficiency` | PARTIAL x5 | PARTIAL x5 | **REPRESENTATION** (schema, by construction) |
| `hybrid_work_mode` | PARTIAL x5 | PARTIAL x5 | **REPRESENTATION** (schema, by construction) |

## E. Failure classification ("could the current schema represent the correct meaning?")
| finding | schema can express the right answer? | class | note |
|---|---|---|---|
| "Advanced proficiency" (Python, Java) | **No**: enum is `hands_on` / `working_knowledge` | REPRESENTATION | the model used `hands_on`, the nearest value (5/5); nothing lost silently, but "advanced" is gone |
| "Hybrid" working basis | **No**: `remote` is `allowed` / `not_allowed` | REPRESENTATION | the model did the right thing under the gap: `remote` null (not `allowed`, not invented) and "hybrid" kept in an evidence signal (5/5) |
| Forward Deployed Engineer in `role_family` (5/5) | Yes (leave it out; evidence signal) | EXTRACTION | an analogy ("more like") hardened into a title family; it reaches the compiler's title filter (D1) |
| `domain` at required: enterprise-scale apps, enterprise data integration across SaaS, production GenAI (2-3 required per run) | Yes (leave `domain` empty) | EXTRACTION | the content duplicates skills/evidence, except "enterprise data integration across SaaS" which is JD *responsibility* context promoted to a required domain. Prompt rule 17 ("environment a candidate's evidence should show") invites exactly this |
| `hands_on` on 15-20 skills | Yes (null where no depth is stated) | EXTRACTION | breakdown below |
| Staff not typed (seniority null) | Yes (`value` is free text) | EXTRACTION, **TAXONOMY** note | the production prompt's level list is `Junior/Mid/Senior/Lead/Principal/Director` and `knowledge/seniority.json` has no `staff`. The model did not substitute a wrong level, which is the discipline we wanted |
| Responsibility "Provide technical leadership, mentor team members…" as a required atom (5/5) | Yes (`context`) | EXTRACTION | same pattern as Role 1's leadership PARTIAL |
| 13-16 required signals per run come only from the JD's *Responsibilities* section | Yes (`context`) | EXTRACTION | post-hoc count; see G3 |
| AKS and EKS both required as separate skills (5/5) | Yes (they are "including" examples) | EXTRACTION | post-hoc; sits beside "Azure and/or AWS" as an OR |

**The hands-on breakdown (post-hoc, descriptive).** Of the 15-20 `hands_on` skills per run: 3 are where the JD states a depth (Python, Java,
Generative AI); 2-5 are arguably supported by the JD's "hands-on engineering role" framing (full stack, APIs, services, distributed
systems); **8-12 have no depth wording at all** (React, Bootstrap, UI frameworks, Solution Design, Data Engineering, AI/ML Implementation, LLMs,
RAG, Agentic AI, Prompt Engineering, Data Integration…). The lenient reading still leaves 8-12 per run. A quote-based check (does the cited quote
contain a depth cue?) would pass only 4-9 of 15-20, so it is **deterministically detectable**.

## F. Field-by-field reuse comparison with Role 1
| field | Role 1 | Role 2 | classification |
|---|---|---|---|
| `sourcing_paths` + path overrides + `strategy` | essential | unused 5/5, correctly | **REUSED BUT NOT NEEDED** (the key discipline test: passed) |
| `semantic_exclusions` | essential | unused 5/5, correctly | REUSED BUT NOT NEEDED |
| `seniority.leadership`, `seniority.alternatives` | needed | unused 5/5, correctly | REUSED BUT NOT NEEDED |
| `location.countries` | needed | unused 5/5, correctly (a city) | REUSED BUT NOT NEEDED |
| `reconciliations` | needed | 0 records 5/5, correctly (the brief only adds) | REUSED BUT NOT NEEDED |
| `basis` (provenance) | needed | all atoms verified, 0 errors | **REUSED CORRECTLY** |
| generic validators | needed | silent, no false errors | REUSED BUT NOT NEEDED (none fired; leakage was not exercisable: no paths) |
| `skill_any_of`, `education`, `experience`, `location.entries` (production fields) | used | Azure/AWS and ML libraries kept as ORs 5/5; 12 / degrees / Hyderabad correct | **REUSED CORRECTLY** |
| `skill.proficiency` | needed (2 values) | right where stated, **over-applied** elsewhere; "advanced" inexpressible | REUSED partly correctly + **MISSING GENERAL CONCEPT** (ordinal depth) |
| `location.remote` | `allowed` needed | `null` 5/5; "hybrid" inexpressible | **MISSING GENERAL CONCEPT** (work mode); `allowed/not_allowed` is the Role-1-shaped part |
| `domain` | essential: it carried Path A's identity | used 5/5 as a required context bucket duplicating skills/evidence | **ROLE-1-SPECIFIC: reconsider** |
| `evidence_signals` (production) | used | 21-27 per run, all `required` | reused; strength vocabulary is applied badly (G3) |

## G. New representation gaps
**G1. Ordinal proficiency (REPRESENTATION).** The JD uses at least five depth wordings: *advanced proficiency*, *hands-on experience*, *strong
understanding*, *familiarity*, and plain *experience with*. The enum has two values, minted from Role 1's two observations. It cannot state
"advanced", and it has no way to say that "understanding" (knowledge) differs from "hands-on" (doing). The schema also pressures
over-application: the only "doing" value is `hands_on`, so the model uses it widely. Not a decision here; see I.
**G2. Work mode (REPRESENTATION).** Hybrid / on-site / remote is a general recruiter concept; `allowed/not_allowed` was a Role-1 shape. The
model coped correctly (null + evidence text) but the typed fact is lost, and the compiler has nothing to route (D3).
**G3. Not a schema gap, but a recurring discipline failure across both roles: responsibility vs qualification.** `context` exists and the model
rarely uses it: Role 1 left a people-leadership responsibility required (1/5); Role 2 hardened 13-16 responsibilities per run. The JD's
Requirements section is clean; the Responsibilities section is what gets promoted. That is EXTRACTION (prompt rule 3 pushes plain
statements to `required`), and a candidate for a deterministic check, since the JD sections are detectable.
**Observation, not a gap:** "IC engineer" has no typed track; it was kept as an evidence signal in 5/5 runs and is representable. Nothing
demonstrates a typed field is needed.

## H. Fields that appear unnecessary or Role-1-specific
- **`domain`**: its justification was "Path A is domain-led". Without a path it only attracts content that belongs in skills or evidence
  signals. Reconsider: fold into evidence signals, or restrict it (a domain strategy exists, or `context` only).
- **`location.remote` as `allowed/not_allowed`**: Role-1-shaped; superseded by G2.
- **Everything else structural** (paths, semantic exclusions, leadership, alternatives, countries, reconciliations) was correctly **not**
  used when the sources did not call for it. That is evidence the structures are not over-eager, not evidence they are unnecessary
  (they remain justified by Role 1).

## DOWNSTREAM FOLLOW-UPS (recorded, not fixed; the unmodified compiler applied offline to each intent, no provider call)
| id | intent representation involved | expected compiler behaviour | observed/current behaviour (5/5 intents) | why downstream |
|---|---|---|---|---|
| D1 | `role_family` containing "Forward Deployed Engineer" | an analogy never reaches a title filter; role families expand only through approved taxonomy | one hard `current.title` OR of `Software Engineer, Backend Engineer, Backend Developer, Python Developer, Solution Architect, Forward Deployed Engineer` | the expansion and the filter are compiler/taxonomy; the root cause is intake (EXTRACTION) |
| D2 | required skills with `relationship: current` | a documented, bounded policy for which required skills are hard filters and which are evidence | every required `current` skill becomes a hard OR-group (3 text fields) AND-ed: 11, 11, 6, 2, 7 hard groups in runs 1-5 of the *same* role, because 10, 10, 5, 1, 6 required skills were marked `current` | the policy is the compiler's; the instability of `relationship` is intake's |
| D3 | `location.remote` null + "hybrid" in text | work mode is either routed or explicitly marked semantic-only | dropped silently: no audit row; Hyderabad compiles to country + state + city hard ANDs | no provider field; a compiler/judge contract, blocked by G2 |
| D4 | `seniority` null (the level is in text) | a stated level reaches admission logic | no seniority audit row at all | would be a taxonomy gap too: no `staff` in `seniority.json` |
| D5 | `skill.proficiency` | `hands_on` / `working_knowledge` route to evidence verification, not a filter | the compiler never reads `proficiency` (0 references) | not built yet; also blocked by G1 |

## I. Architecture recommendation
**Do not promote the experimental schema into the production `StructuredHiringIntent` yet.** Two roles still do not prove generality; this
second one found two representation gaps and one field to reconsider. Recommended, in order, none of it done here:
1. **Owner decisions on the two gaps** (G1, G2), made as design decisions: an ordinal depth with a value above `hands_on` and a way to tell
   knowledge from doing, or a restriction to source-stated depth only; a work-mode value that includes hybrid. Smallest change each; no
   new field if a value suffices.
2. **Reconsider `domain`** (H). If it stays, define when it must be left empty.
3. **Candidate generic validators** (deterministic, no role content): *depth stated* (a proficiency requires a depth cue in its cited quote;
   it would flag ~65% of Role 2's `hands_on`); *analogy to title* (a `role_family` entry whose only source mention follows "more like" /
   "similar to" / "like a"); *responsibility-only required atom* (needs JD section detection). Each should be argued before it is built.
4. **Prompt-level issues stay prompt-level** until a schema reason appears: responsibilities as `context`, "including" lists as examples,
   `relationship` assignment (10/10/5/1/6), the level vocabulary lacking "Staff".
5. **Record D1-D5 for the compiler phase.** The compiler is the next consumer of this contract, and D2 shows intake instability becoming
   retrieval instability, so intake stability of `relationship` should be settled before compiler work, not after.
6. **A third, differently shaped role** before any promotion decision (for example one with named company/background preferences and a
   non-engineering function), with its ground truth written and committed first, as here.

What held up: no invented path, exclusion, company, remote, leadership, alternative, country or reconciliation in 5/5 runs; OR groups kept
correctly; every atom's provenance verified; the model declined to invent a seniority when "Staff" was outside its vocabulary. The
structural discipline generalised. The content-level discipline did not.
