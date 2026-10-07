# RESULTS — Role 3 cross-role validation (JD-only)

**THREE-ROLE VALIDATION FOUND EXTRACTION/VALIDATION ISSUES ONLY**

Caveat attached to that verdict, stated up front because it is the one place a reasonable reviewer could go the other way: the Power BI
"working knowledge of X **or similar**" meaning was kept as an untyped required evidence-signal text in 5/5 runs, with no typed depth. I classed it
EXTRACTION because a lossless single-atom form exists in the frozen schema (pre-registered in `ROLE3_GROUND_TRUTH.md` section 11 and 19, committed
before any model call). If you count "a depth cannot ride on an OR group" as a representation gap, the conclusion line becomes
**THREE-ROLE VALIDATION FOUND A REPRESENTATION GAP**. Everything needed to make that call is in sections E and G.

This is not "architecture proven". Three roles, one model, five runs each, and one author for ground truth and evaluators.

Frozen inputs: `prompt_v4.txt` (sha256 `27f79f50c94fb0b7584b84ebbf01b3e92f096d2230c3af9b78950dbbabc71c5d`), the experimental schema, `validators.py`,
`validators_cross_role.py`, the same model (`gpt-6.1-sol`, reasoning effort medium), streamed, same JD (`inputs/role3_jd.txt`, sha256 `5df08994…b8eb`),
**no brief** (none exists, none was created), five runs, no prompt change, 5/5 parsed, **0 transient retries**. 25,680 input / 17,926 output tokens,
51.3-55.4 s per run. Evidence: `results/role3/`, `results/role3_analysis.json`. Reproduce offline with
`python -m backend.experiments.intake_strategy.compare_role3`.

## What to distrust (read first)
1. **I wrote the ground truth and the evaluator, and you have not reviewed them.** They were committed before any model call (`c0afe07` ground truth,
   `6896246` evaluator, runner and tests). If you disagree with a decision the verdicts move. The decisions that matter most: the Power BI classification
   (above); "Hyderabad, Telangana, India" is an acceptable normalisation (INFERRED, G2); any `seniority.leadership` entry is invented (S2); `domain` is optional.
2. **One billing failure preceded the run.** My first attempt had 5/5 calls fail with `429 insufficient_quota` and produced no output. After you added OpenAI
   credit I ran the five runs once. The five runs analysed here are the only ones that produced output. Nothing was selected from several attempts.
3. **One evaluator correction after seeing results, both columns shown.** The pre-registered `no_role_shape_structure` counted a *required* `domain` atom as
   over-application. That exceeded my own ground truth: the atom restates the JD's required experience field ("8–12 years … in FP&A, Business Finance, …")
   and the ground truth never forbade a domain. I removed that rule (commented in `gold_role3.py`, regression test added) and moved it to a labelled
   observation. As run: FAIL x5. Corrected: FAIL x2 (only the invented-leadership runs). No other assertion changed.
4. **Post-hoc observations are labelled and are not assertions** (domain redundancy, Telangana, the compiler observations, field-usage counts).
5. **Preservation was not re-measured under v4.** Roles 1 and 2 ran on `prompt_v3`; v4 has only ever run on Role 3. The "both complexity preservation and
   restraint" test therefore compares two prompt versions of the same rules 1-10 plus generic additions. v4 on Role 1 would be a new run and was out of scope.
6. **Two real failures are small in count but real** (invented leadership 2/5; Power BI depth 5/5). Do not read "issues only" as "clean".

## A. Ground truth (summary; the full file is `ROLE3_GROUND_TRUTH.md`)
JD-only: one sourcing strategy, **no paths, no reconciliations** (there is no second source). Hard: Bachelor's in Finance/Accounting/Economics/Business/related;
**8–12 years**; planning/budgeting/forecasting/variance; financial modeling; Excel (**"Advanced proficiency"**); Power BI "or a similar BI platform"
(**"Working knowledge"**); presenting to senior stakeholders; business partnering; ERP "such as SAP, Oracle, or comparable" (examples, not an AND);
meaningful FP&A ownership. Preferred: CA/CMA/ACCA/MBA Finance; large multinational / complex enterprise; Unilever, P&G, PepsiCo, Nestlé, Coca-Cola, Mondelez or
similar ("particularly relevant", a *preference*); commercial/operations/BU leadership support. One exclusion with a qualifier: experience *exclusively* in
statutory audit / tax / bookkeeping / transaction processing *without substantive FP&A* is not suitable. Location Hyderabad; Work Mode Hybrid (separate facts).
Level: "Senior Manager" (title; unknown to `seniority.json`). No temporal wording, so every relationship is `any`. Ten responsibilities, four of which are
not also qualifications (management packs, automation, cross-functional, ad hoc projects) and must not be required.
Provenance classes: JD, APPROVED_KNOWLEDGE (only absences: no finance role family, no "Senior Manager" level), INFERRED. **No RECRUITER_BRIEF assertion exists.**

## B. The five extracted intents (run 2 is representative; all five in `results/role3/`)
- `sourcing_paths` [], `reconciliations` [], `exclusions` [] in **5/5**. `location.countries` [], `remote` null, `seniority.alternatives` [] in 5/5.
- `role_family` "FP&A and Business Finance Manager" (4/5; run 5 "FP&A and Business Finance"). `seniority`: run 1 "Senior" (role_family keeps "Manager"), runs 2-5
  "Senior Manager" (the unknown level kept as written, as v4 rule 20 asks). **`seniority.leadership = ["technical"]` in runs 2 and 3** (the only source cited is the title).
- `experience` 8–12 required (5/5). `education` Bachelor's required, streams Finance/Accounting/Economics/Business/Related discipline, one strength (5/5).
- `location` "Hyderabad, Telangana, India", `work_mode = hybrid`, `remote` null (5/5).
- Skills (9-10): the planning/modeling skills `required`, relationship `any`, **proficiency null**; Microsoft Excel `required`, **`advanced`**. Two `skill_any_of`
  groups: ERP [SAP, Oracle, Comparable ERP platforms] (examples correctly grouped, not ANDed) and Power BI [Power BI, Similar BI/reporting platform].
- Power BI depth: the group has no proficiency; the stated depth survives only as a `required` evidence signal named "Working knowledge of Power BI or a
  similar business intelligence/reporting platform" (5/5).
- Companies: six, each `preferred`, `any`. `company_scale` null. Professional qualification: a `preferred` evidence signal (not merged into the degree).
- Evidence signals 17-19: 6 required, 2 preferred, 10-11 context (responsibilities not stated as qualifications are `context`).
- `domain` (4): one `required` (restating the experience field), two `preferred` (large multinational/complex enterprise; large consumer/industrial organisations),
  one `context` (large, complex organisation). Observed, not asserted against (see 3 above).
- One semantic exclusion with the qualifier ("exclusively … without substantive FP&A or business-finance responsibilities") and four `includes` that each keep it.
- Provenance: 44-46 atoms per run, **all verified, 0 diagnostics, 0 validator errors**, no atom cites `recruiter_brief`.

## C. Five-run stability
| component | agreement |
|---|---|
| paths 0 / reconciliations 0 / exclusions 0 / semantic exclusions 1 | 5/5 |
| experience 8–12 required | 5/5 |
| education (Bachelor's, required) | 5/5 |
| location (Hyderabad, hybrid, remote null, no countries) | 5/5 |
| companies (six, preferred, any) | 5/5 |
| proficiency (Excel `advanced`; Power BI none; nothing elsewhere) | 5/5 |
| domain strengths (context, preferred, preferred, required) | 5/5 |
| role_family | 4/5 (two spellings) |
| evidence-signal strength counts | 4/5 |
| skills count (9 or 10) | 3/5 |
| relationships (all `any`; 11 or 12 atoms) | 5/5 on value, 3/5 on count |
| **seniority (value, strength, leadership, alternatives)** | **2/5 (three distinct forms)** |

Stable: every structure the JD says nothing about stayed empty in every run. Not stable: the seniority form, and `leadership`. The two spellings of the title
and the 9/10 skill count are surface variation (not scored).

## D. Gold assertions (25; pre-registered evaluator vs corrected)
| assertion | as run | corrected | class |
|---|---|---|---|
| role family discipline; experience 8–12; Bachelor's required; Hyderabad single; **hybrid typed**; core requirements present and required | PASS x5 each | same | |
| **Excel `advanced`**; no invented proficiency; ERP examples not ANDed; professional qualification preferred | PASS x5 each | same | |
| company preference kept as preference; background preferences preferred; semantic exclusion faithful | PASS x5 each | same | |
| no path or reconciliation; no invented exclusion; no unsupported temporal relationship; no responsibility hardening; no preference hardened | PASS x5 each | same | |
| no fabricated brief source; provenance preserved; generic validators clean | PASS x5 each | same | |
| `seniority_senior_manager` | PASS x3 FAIL x2 | PASS x3 FAIL x2 | EXTRACTION (invented `leadership`, runs 2, 3) |
| `power_bi_working_knowledge` | PARTIAL x5 | PARTIAL x5 | EXTRACTION (see E) |
| `no_role_shape_structure` | FAIL x5 | PASS x3 FAIL x2 | as-run FAIL was my evaluator over-reaching (disclosure 3); the 2 remaining FAILs are the same invented leadership |

Totals (corrected): 22 assertions PASS x5; 3 not clean (leadership twice counted in two assertions, Power BI PARTIAL).

### Over-application checklist (the brief's list; counts are runs of 5)
| over-application | runs |
|---|---|
| invented sourcing path | 0 |
| invented conditional path / path-scoped structure | 0 |
| invented exclusion (company/title/industry) | 0 (one semantic exclusion, which the JD states, with its qualifier) |
| invented geography (countries, radius, second place) | 0 |
| invented work mode (anything but hybrid) / `remote` set | 0 |
| invented proficiency (anything beyond Excel) | 0 |
| company hard filter (required, current, past, scale, exclusion) | 0 |
| invented seniority (a different level, or `alternatives`) | 0 |
| **invented seniority sub-structure (`leadership`)** | **2** |
| title alternative / analogy as title | 0 |
| unsupported `current` / `past` relationship | 0 (Role 2: 10, 10, 5, 1, 6 `current`) |
| responsibility hardened into required | 0 (frozen `responsibility_only_required` count 0) |
| preference hardened into required | 0 |
| brief source fabricated | 0 |

## E. Failure classification ("could the current schema represent the correct meaning? yes → extraction/reconciliation/validation; no → representation")
| issue | class | evidence | why |
|---|---|---|---|
| Invented `seniority.leadership = ["technical"]` (runs 2, 3) | **EXTRACTION**, with a **VALIDATION coverage gap** | the cited quote is only the title "Senior Manager – FP&A and Business Finance" | the field exists and could be left empty; no frozen validator checks `leadership` against its source, so it passed with 0 diagnostics |
| Power BI "working knowledge … or similar" typed depth lost, 5/5 | **EXTRACTION** (borderline, see G) | the group form chosen carries no proficiency; the depth is only in an untyped required signal | pre-registered: ONE atom whose name carries "or similar" with `working_knowledge` is lossless and was available |
| Seniority form varies ("Senior" + Manager in the family vs "Senior Manager") | EXTRACTION (benign) | 3 forms over 5 runs | both accepted forms by the pre-registered rule; the instability is in what reaches the compiler, not a wrong meaning |
| `domain` duplicates experience/evidence meaning | EXTRACTION / redundancy, not a failure | 4 atoms, 1 required restating the experience field | the field is optional and a faithful restatement is not over-application |
| "Telangana" added to the normalised place | **TAXONOMY/KNOWLEDGE** observation | the JD says "Hyderabad, India" only; the compiler's alias table has no Hyderabad entry | model world knowledge, INFERRED (G2); no validator flags a city-complete string; not penalised |
| "Senior Manager" not in `seniority.json` | **TAXONOMY/KNOWLEDGE** (unchanged follow-up) | kept as written, as intended | knowledge file is production |
| REPRESENTATION | none confirmed | | every stated meaning had a schema form; the OR-group/depth observation is the borderline candidate (G) |
| RECONCILIATION | none | no brief, empty list in 5/5 | n/a |
| PROVENANCE | none | all atoms verified, no fabricated source | n/a |

## F. Cross-role field comparison (usage = runs of 5; Role 1 = frozen v3 runs, Role 2 = frozen v3 runs, Role 3 = v4)
| field | R1 | R2 | R3 | classification | note |
|---|---|---|---|---|---|
| `sourcing_paths` | 5 | 0 | 0 | **ROLE-SHAPE SPECIFIC** | 0/5 in both single-strategy roles; perfect restraint |
| `reconciliations` | 5 | 0 | 0 | **ROLE-SHAPE SPECIFIC** | only meaningful with two sources; Role 3 had one, so it is untested for false use beyond emptiness |
| `semantic_exclusions` | 5 | 0 | 5 | **GENERAL CONCEPT**, REUSED CORRECTLY | both uses are source-stated with their qualifier; Role 2 correctly empty |
| `exclusions` (company/title) | 0 | 0 | 0 | not exercised | unused in all three; Role 1's exclusion was semantic |
| `domain` | 5 | 5 | 5 | **GENERAL CONCEPT**, but REUSED BUT NOT NEEDED in part | used in every role; mostly restates experience/evidence; the required atom is redundant. Optionality is not what restrains it |
| `seniority.value` | | | | GENERAL CONCEPT, REUSED CORRECTLY | unknown level kept as written (v4 rule 20 worked) |
| `seniority.alternatives` | 5 | 0 | 0 | **ROLE-SHAPE SPECIFIC** | 0/5 where not stated |
| `seniority.leadership` | 5 | 0 | 2 | **ROLE-SHAPE SPECIFIC**, over-application risk | invented from a title alone in Role 3, 2/5; not caught by any validator |
| `location.countries` | 5 | 0 | 0 | **ROLE-SHAPE SPECIFIC** | 0/5 elsewhere; "Hyderabad, India" did not become a country |
| `location.remote` | 5 | 0 | 0 | **ROLE-SHAPE SPECIFIC** | stayed null where unstated |
| `location.work_mode` | 0 | 0 | 5 | **GENERAL CONCEPT**, REUSED CORRECTLY | typed `hybrid` 5/5, distinct from geography; Role 2's gap closed in this role |
| `proficiency` | | | | **GENERAL CONCEPT** | `advanced` used correctly 5/5; nothing invented (Role 2 stated `hands_on` on 19-25 atoms, Role 3 1); depth cannot ride on an OR group (G) |
| `skill_any_of` | 0 | 5 | 5 | GENERAL CONCEPT, REUSED CORRECTLY (ERP) | the ERP examples correctly grouped, not ANDed; the Power BI group lost its depth |
| `relationship` | | | | GENERAL CONCEPT, REUSED CORRECTLY | `current`: R1 [3,0,0,0,0], R2 [10,10,5,1,6], R3 [0,0,0,0,0]; v4 rule 23 plus the validator held |
| `companies` | 0 | 0 | 5 | REUSED CORRECTLY | six `preferred`/`any`, never a filter |
| `basis` (provenance) | | | | GENERAL CONCEPT, REUSED CORRECTLY | 44-46 atoms verified/run; no fabricated source when no brief exists |

The classifications use Role 1 / Role 2 usage only as already measured. NEW REPRESENTATION GAP: none confirmed (G).

### Generalization test: complexity preservation vs complexity restraint
- **Preservation** (Role 1, frozen under v3): two sourcing paths, six reconciliations, a leadership decision, countries, remote and a semantic exclusion were all kept.
  This was not re-measured under v4 (disclosure 5).
- **Restraint** (Roles 2 and 3): in Role 3 every structure the JD is silent on stayed empty in 5/5 runs, including the five that Role 1 populated every time
  (paths, reconciliations, countries, remote and alternatives). Six optional structures were populated in Role 3 (semantic exclusion, domain, work mode, companies,
  skill groups, one proficiency), five of them for a meaning the JD states. Exceptions: **`leadership` invented in 2 runs** and **`domain` redundancy**.
- Reading: the schema is not succeeding only by populating many optional structures. The discipline is imperfect in two specific places, neither of which is a
  structural one, and neither is caught by a frozen validator (leadership) or is plainly a duplicate (domain).

## G. Schema-gap assessment
| candidate | status |
|---|---|
| **Proficiency on an OR group** ("working knowledge of X or similar") | **Observation, pre-registered, not confirmed as a gap.** `skill_any_of` carries no proficiency. The lossless form is one skill atom named "Power BI or a similar BI/reporting platform" with `working_knowledge`. The model chose the typed OR group instead in 5/5 runs (prompt rule 5 conserves OR-ness) and lost the typed depth; the depth survives only as untyped text. This is the case that decides the conclusion line. Reasons it is classed EXTRACTION: the schema can say it; the prompt steers the model to the other form. Reasons it could be a gap: the single-atom form makes the OR-ness a free-text name, and a compiler that reads `skill_any_of` will never see it. **Owner decision.** |
| Professional qualification ("CA, CMA, ACCA, or MBA Finance is preferred") | Observation, pre-registered. `education` has one strength, so a preferred qualification cannot sit there beside a required degree. It was carried as a preferred evidence signal (5/5). Correct meaning, no typed home. Not a failure, not a gap by the rule (a form exists). |
| `leadership` trigger risk | Not a schema gap. A free-form list with no validator against its source; the model filled it from a title alone. A VALIDATION coverage gap (a generic check "typed seniority sub-structure must be stated by its cited text" is the analogue of the Role 2 validators). Recorded, not added. |
| `domain` | Not a gap. Redundant with `experience` and evidence signals when used; optional; the same meaning is available elsewhere. |
| Anything that needed a schema change | none |

## DOWNSTREAM FOLLOW-UPS (recorded, not fixed; the unmodified compiler, applied offline to each of the five intents, no provider call)
1. **Role family becomes one literal hard title.**
   - Intent representation: `role_family = ["FP&A and Business Finance Manager"]` (4/5).
   - Expected: a title matching the finance function (with an expansion), not one literal string.
   - Observed: the title filter and retrieval title family are the one literal string; there is no finance entry in the role-family taxonomy (I5).
   - Why downstream: the intent carried the source's own title; expansion is a taxonomy/compiler responsibility.
2. **Meanings that have no audit row are dropped silently.**
   - Intent representation: `semantic_exclusions`, `location.work_mode`, `domain`, `skill.proficiency`, `seniority.leadership`.
   - Expected: every typed meaning appears either as a filter, an evidence signal or an audit row.
   - Observed: none of the five appears in the plan or its audit (the exclusion, the hybrid mode, the Excel depth and the preference domains are not represented).
   - Why downstream: the intent preserved them; routing them is the compiler's job. (The compiler also never reads proficiency or work mode, as before.)
3. **Experience range compiles to a hard `>=8` AND `<=12`.**
   - Intent representation: `experience {8, 12, required}`.
   - Expected: confirm that a stated upper bound should be a hard filter, or an evidence gate.
   - Observed: both are hard leaves in 5/5.
   - Why downstream: the JD states the range as a hard header fact; the intent is faithful. This is a policy question for the compiler, not an extraction fault.
4. **Education compiles to literal strings.**
   - Intent representation: degree "Bachelor’s degree" (curly apostrophe) and streams including "Related discipline".
   - Expected: normalised degree and fields.
   - Observed: `degree = Bachelor’s degree` and `field_of_study = Related discipline` as literal filters (a stream "Related discipline" is not a real field of study).
   - Why downstream: the representation kept the source's words; normalisation is the compiler's.
5. **"Senior Manager" level reaches `admission_level_fit` as written.**
   - Intent representation: `seniority.value = Senior Manager` (runs 2-5; "Senior" in run 1).
   - Expected: a level the knowledge file knows, or an explicit unknown.
   - Observed: `seniority.json` has only senior/junior/mid; the audit row reads `value=Senior Manager` (run 1 `value=Senior`).
   - Why downstream: TAXONOMY/KNOWLEDGE, production file.
6. **Positive:** skill `any` relationships route to downstream evidence, so the hard filter has **12 leaves in 5/5** (Role 2: 19-46). Companies route to
   `context_or_evidence`, not a filter. This is the compiler working as designed on a faithful intent.

## H. Architecture recommendation
Against the promotion gate:
| criterion | evidence |
|---|---|
| generalization across materially different roles | three different roles (two-strategy recruiter-brief role, engineering staff role, finance JD-only role) all parsed 5/5 with all atoms verified; the two roles that were not structurally complex did not receive invented structure |
| optional fields staying optional | held for paths, reconciliations, exclusions, countries, remote, alternatives; **not for `leadership` (2/5) and partly for `domain`** |
| no major over-application pattern | none of the structural kinds; one small content kind (leadership) |
| auditable provenance / reconciliation | 44-46 atoms verified per run; reconciliations untested without a brief (empty, as correct) |
| stable temporal relationship | `current` 0 in all 5 runs; stable by v4 rule 23 and the validator |
| stable title interpretation | one title, no analogy; 4/5 spelling, benign |
| proficiency not causing false hardening | only the two stated depths; none invented |
| work mode distinct from geography | hybrid typed 5/5 and location unchanged |

My recommendation, not a decision: keep the experimental schema unpromoted until the owner has decided (1) whether proficiency on an OR group is a schema change or
a prompt/validator matter, and (2) whether to add a generic validator that a typed `seniority.leadership` / `alternatives` entry must be stated by its cited text.
Neither needs a new role. The compiler follow-ups above are independent of the schema decision. I did not add either, tune `prompt_v4`, or touch the compiler.

## Disclosures
- First attempt: 5/5 `429 insufficient_quota`, no output; confirmed with a probe, resolved by credit top-up. The five analysed runs are the only runs with output.
- Evaluator correction after seeing results (disclosure 3), both columns above. Tests pin the final evaluator.
- The ground truth and evaluators are mine and unreviewed. The pre-registered representability table and the Power BI and certification observations were committed before any run.
- No brief was created, and no assertion is RECRUITER_BRIEF.
- One model, five runs, one JD per role. Same-error stability across runs is not proof of generality.
- No retrieval, CrustData, Harvest, compiler change, provider change, production change, schema promotion or prompt change.

**THREE-ROLE VALIDATION FOUND EXTRACTION/VALIDATION ISSUES ONLY**
