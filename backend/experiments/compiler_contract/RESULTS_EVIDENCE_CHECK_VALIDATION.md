# RESULTS — Evidence Check validation (real Judge model; synthetic candidates only)

Phase: harden the downstream Evidence Check contract. **Not called:** CrustData, Harvest, any provider, any retrieval; **no real candidate data; not deployed; `StructuredHiringIntent` unchanged (hash-pinned); ranking and admission unchanged (hash-pinned).** The only external call is the Judge's own model (OpenAI, through the sandbox proxy), gpt-4o-mini at temperature 0, with the requirement and review prompts unchanged (hash-pinned). Contract: `backend/services/DOWNSTREAM_CONSUMER_CONTRACT.md` (§3b-3f). Raw outputs: `results/evidence_check/raw/`. Reproduce: `python -m backend.experiments.compiler_contract.evidence_check_run run --runs 6` then `analyze`, then `build_evidence_check_report`.

## Verdict
**NOT 6/6 on every scenario: see the target table and the classification of each failure below.**

## 1. What changed (the Evidence Check)
* An **Evidence Check** (`backend/services/evidence_check.py`) is the semantic unit the Judge evaluates: `check_id`, `path_id`, `concept`, `criterion`, `positive|negative`, `strength`, `proficiency`, `relationship`, `provenance`, plus the deterministic binding fields (`subject_terms`, `requires_work_evidence`) and, for negatives, an explicit `predicate`. It is a downstream execution artifact built from the compiled checklist; it is not part of `StructuredHiringIntent`.
* **Binding.** A verdict binds to exactly one `check_id` (an id answered twice is unanswered). A `met` / `partly` / `PRESENT` stands only if its quote passes the gate **and** supports THIS check: a named skill's quote must name that skill; a depth claim (skill + depth is ONE claim) needs demonstrated work or a certification, never a skills-list entry, a title or a headline; a PRESENT exclusion's quote must contain an indicator of its own predicate.
* **Exclusions** are explicit predicates (`must_not_indicate`, `not_sufficient`, `unless_candidate_also_shows`, `exclusive`, the recruiter's `qualifier`), answered `PRESENT` / `NOT_PRESENT` / `INSUFFICIENT_EVIDENCE`. The recruiter prose is never sent to the model. A PRESENT that cannot be evidenced, and a NOT_PRESENT on a profile that describes no work, are INSUFFICIENT_EVIDENCE, never NOT_PRESENT.
* **Quote gate** unchanged in strength, now explicit: one contiguous exact span of ONE passage, no ellipsis (`...` or the single character), no paraphrase. **One narrow retry**: only the checks whose quote failed the gate are re-asked, once, with an exact-quote instruction; a successful check is never re-asked and a binding discard is final.

## 2. Scenarios (synthetic, hand-written before any run, unchanged between runs)
| candidate | designed to show |
|---|---|
| E | SOC / security-operations work |
| A | cyber incident review and data breach analysis; no security-operations evidence |
| G | data analyst at a security-software company: security is the employer's field, not the candidate's work |
| H | no description of work at all (title and headline only) |
| B0 | hands-on Python and Java in ONE sentence (the case the earlier review pass downgraded) |
| B1 | hands-on Python and hands-on Java, stated separately |
| B2 | hands-on Python; Java only from a university course |
| B3 | hands-on Java; Python only from a university course |
| C1 | advanced Excel + working-knowledge Power BI |
| C2 | basic Excel + working-knowledge Power BI |
| C3 | basic Excel + ADVANCED Power BI (a deeper tool still meets the weaker depth) |
| C4 | advanced Excel, no Power BI at all |

## 3. Target: 6/6 semantic correctness on each scenario
A run is correct only if EVERY gating expectation of the scenario holds in that run.

| scenario | what | runs fully correct | target |
|---|---|---|---|
| A | Role 1 negative | 5/6 | NOT 6/6 |
| B | Role 2 proficiency | 6/6 | PASS |
| C | Role 3 proficiency | 0/6 | NOT 6/6 |

## 4. Results per expectation (6 runs each)
| expectation | cand. | check | item | expected | status | runs correct | observed | why |
|---|---|---|---|---|---|---|---|---|
| A-E-present | E | excl_state | Generic cybersecurity or security-operations backgrounds are | PRESENT | PASS | 6/6 | PRESENT | explicit SOC / security-operations work |
| A-A-not-present | A | excl_state | Generic cybersecurity or security-operations backgrounds are | NOT_PRESENT | UNSTABLE | 5/6 | INSUFFICIENT_EVIDENCE, NOT_PRESENT | cyber incident / breach review is the domain, not security operations |
| A-G-not-broadened | G | excl_state | Generic cybersecurity or security-operations backgrounds are | NOT_PRESENT | PASS | 6/6 | NOT_PRESENT | works for a security company / mentions security / has security-adjacent duties is NOT the exclusion |
| A-H-insufficient | H | excl_state | Generic cybersecurity or security-operations backgrounds are | INSUFFICIENT_EVIDENCE | PASS | 6/6 | INSUFFICIENT_EVIDENCE | a profile with no description of work cannot clear the exclusion; it must not read as NOT_PRESENT |
| A-G-firm-info | G | excl_state | A strong SQL/Python analyst working at a security firm | PRESENT | PASS | 6/6 | PRESENT | informational: this exclusion names the security-firm analyst |

| expectation | cand. | check | item | expected | status | runs correct | observed | why |
|---|---|---|---|---|---|---|---|---|
| B0-java | B0 | req_met | hands-on Java | met | PASS | 6/6 | met | Java is named in the quote and used in production |
| B0-python | B0 | req_met | hands-on Python | met | PASS | 6/6 | met |  |
| B1-java | B1 | req_met | hands-on Java | met | PASS | 6/6 | met | Java evidence is the Java passage |
| B1-python | B1 | req_met | hands-on Python | met | PASS | 6/6 | met | Python evidence is the Python passage |
| B2-python | B2 | req_met | hands-on Python | met | PASS | 6/6 | met |  |
| B2-java | B2 | req_not_met | hands-on Java | not met | PASS | 6/6 | not_evidenced | familiar != hands-on; Python evidence cannot be reused for Java |
| B3-java | B3 | req_met | hands-on Java | met | PASS | 6/6 | met |  |
| B3-python | B3 | req_not_met | hands-on Python | not met | PASS | 6/6 | not_evidenced | familiar != hands-on; Java evidence cannot be reused for Python |

| expectation | cand. | check | item | expected | status | runs correct | observed | why |
|---|---|---|---|---|---|---|---|---|
| C1-excel | C1 | req_met | advanced proficiency in Microsoft Excel | met | PASS | 6/6 | met | advanced evidence meets advanced |
| C1-pbi | C1 | req_met | Working knowledge of Power BI or a similar business intellig | met | PASS | 6/6 | met |  |
| C2-excel | C2 | req_not_met | advanced proficiency in Microsoft Excel | not met | PASS | 6/6 | not_evidenced | basic Excel is not advanced |
| C2-pbi | C2 | req_met | Working knowledge of Power BI or a similar business intellig | met | FAIL | 0/6 | partly | working knowledge is the weaker depth |
| C3-excel | C3 | req_not_met | advanced proficiency in Microsoft Excel | not met | PASS | 6/6 | not_evidenced | Power BI depth cannot be assigned to Excel |
| C3-pbi | C3 | req_met | Working knowledge of Power BI or a similar business intellig | met | FAIL | 0/6 | not_evidenced |  |
| C4-excel | C4 | req_met | advanced proficiency in Microsoft Excel | met | UNSTABLE | 4/6 | met, not_evidenced |  |
| C4-pbi | C4 | req_not_met | Working knowledge of Power BI or a similar business intellig | not met | PASS | 6/6 | not_evidenced | Excel depth cannot be assigned to Power BI |

(`A-G-firm-info` is informational and not part of the acceptance.)

## 5. Acceptance
| criterion | status | evidence |
|---|---|---|
| each verdict maps to the correct check_id | PASS | 0 verdicts without a known check_id over 72 runs; every expectation was read through its check_id |
| evidence cannot be cross-assigned between skills | PASS | 0 accepted verdicts whose quote does not name the check's subject; the four cross-assignment expectations: PASS, PASS, PASS, PASS; the validator discarded 61 proposed verdicts |
| proficiency is evaluated separately | FAIL | scenario B 6/6, scenario C 0/6 runs fully correct |
| exclusion semantics are reliable | FAIL | A-E-present: 6/6, A-A-not-present: 5/6, A-G-not-broadened: 6/6 |
| insufficient exclusion evidence remains distinct | PASS | A-H-insufficient 6/6: observed ['INSUFFICIENT_EVIDENCE'] |
| exact quote verification remains active | PASS | 0 accepted quotes fail the gate; of 1054 first-pass claims, 110 contained an ellipsis and none was accepted |
| successful checks are not retried | PASS | 0 violations; 23 retry calls re-asked 134 checks (121 recovered) |
| no provider syntax reaches the Judge | PASS | 0 hits over 1053 calls (provider syntax, compiler detail, check_id, recruiter wording, evidence terms) |

## 6. The mechanisms, measured
|  |  |
|---|---|
| model calls / tokens / cost | 1053 / 586,006 in, 132,716 out / about $0.168 |
| first-pass claims carrying a quote | 1054 |
| ... of which contained an ellipsis (all rejected by the gate) | 110 |
| checks retried (only those that failed the quote gate) | 134 in 23 retry calls; 121 recovered |
| proposed verdicts discarded by deterministic binding | 61 |
| verdicts downgraded by the (unchanged) review pass | 5 |
| API failures | 0 |

### What the deterministic binding discarded
| check | kind | subject tokens | why discarded | times | example quote the model cited |
|---|---|---|---|---|---|
| Financial modeling | skill | financial, modeling | subject_not_in_quote | 24 | builds financial models, scenario analysis and sensitivity analysis for revenue, |
| Data Engineering | skill | data, engineering | subject_not_in_quote | 13 | maintains the team's Python data pipelines. |
| hands-on Solution Design | proficiency | solution, design | work_evidence_required | 12 | Backend Engineer |
| API Development | skill | api, development | subject_not_in_quote | 6 | ships APIs to customers |
| Service Development | skill | service, development | subject_not_in_quote | 4 | Writes production Python and Java services every day and ships APIs to customers |
| Generic cybersecurity or security-operations backgrounds are | exclusion | - | indicator_not_in_quote | 1 | reviewed documents from data breach incidents for several clients to identify af |
| hands-on Data Engineering | proficiency | data, engineering | subject_not_in_quote | 1 | Writes production Python services every day |

Of the proposed verdicts the deterministic binding discarded, the ones on a DEPTH claim or on a PRESENT exclusion are correct discards (a title cited for a skill-at-a-depth claim; a Python sentence cited for 'hands-on Data Engineering'; a breach-review sentence cited as security operations). **But 47 of the discards are VALIDATION over-reach**: plain, multi-word CATEGORY skills (`Financial modeling` with 'builds financial models', `Data Engineering` with 'maintains the team's Python data pipelines', `API Development` with 'ships APIs to customers', `Service Development`) were bound lexically on all their tokens, so legitimate evidence was thrown away. None of the gating expectations depends on them, which is why they do not show in section 3, but they are lost recall and they are a defect of this implementation (class VALIDATION). Recommended fix, not applied here (it would change the validated code): bind plain skill checks only when the subject is a single named tool (Java, Python, SQL, Excel ...), keep the two-token binding for depth claims (where it did its job), and fold plural / -ing stems.

### Exploratory diagnostic (NOT part of the validation, NOT adopted)
One hypothesis for C3 was tested separately from the validation: that the depth clause names a level without saying a deeper level also satisfies it. Scenario C was re-run 6 times per candidate with the clause worded 'at least ... (a deeper level also satisfies it)' (production wording unchanged, nothing adopted). The Power BI check on C3 went from 0/6 to 1/6 met; C2 stayed `partly` on 5 of 6; C4's Excel stayed 3/6. The wording is not the cause.

| candidate | with the depth clause worded 'at least' (6 runs) |
|---|---|
| C1 | excel_advanced: 6/6 met, powerbi_working_knowledge: 6/6 met |
| C2 | excel_advanced: 0/6 met, powerbi_working_knowledge: 1/6 met |
| C3 | excel_advanced: 0/6 met, powerbi_working_knowledge: 1/6 met |
| C4 | excel_advanced: 4/6 met, powerbi_working_knowledge: 0/6 met |

## 7. Failures, classified
| expectation | runs correct | observed | class | note |
|---|---|---|---|---|
| A-A-not-present | 5/6 | INSUFFICIENT_EVIDENCE, NOT_PRESENT | MODEL CAPABILITY | One run in six the model answered PRESENT for the cyber-incident / breach-review candidate, citing a data-breach sentence that contains no security-operations indicator. The deterministic indicator binding rejected it, so the wrong PRESENT never reached the result; the state became INSUFFICIENT_EVIDENCE (never NOT_PRESENT), which is why the run is not 'correct'. Open design question: whether an unsupported PRESENT claim on an otherwise rich profile should be INSUFFICIENT_EVIDENCE (current, conservative) or NOT_PRESENT. |
| C2-pbi | 0/6 | partly | MODEL CAPABILITY | The profile says the candidate 'assembled three dashboards from templates in Power BI (working knowledge of Power BI)'. The model answers `partly` on every run (consistent, not noise). The scenario evidence is borderline ('from templates'); this is not a contract or validation defect. C1 (dashboards for monthly management reporting) is `met` on every run. |
| C3-pbi | 0/6 | not_evidenced | MODEL CAPABILITY | The profile states 'Builds advanced Power BI solutions: DAX measures, star-schema semantic models, incremental refresh ...'. The model answers `not_evidenced` on the working-knowledge check on every first pass: it does not accept a stronger statement as meeting a weaker named depth. The exploratory diagnostic below tested the contract wording ('at least ... a deeper level also satisfies it') and it did not fix it, so this is not a PROMPT/CONTRACT wording defect. The alternative is a REPRESENTATION change (see risks). |
| C4-excel | 4/6 | met, not_evidenced | MODEL CAPABILITY | 'Advanced Microsoft Excel user: builds dynamic driver-based financial models with VBA macros ...' is `not_evidenced` on the first pass in 2 of 6 runs and `met` in 4: instability on explicit evidence (the same behaviour as the previous phase). The quote gate and binding were not involved (no discard). |

Classes: PROMPT/CONTRACT (what the model was asked), MODEL CAPABILITY (the model cannot do it reliably as asked), VALIDATION (the deterministic checks), REPRESENTATION (the check is mis-built). The classification is the analyst's reading of the evidence above; the verdicts are measured.

## 8. Remaining risks
1. **The small model is not reliable on depth comparison.** It does not consistently accept a stronger statement as meeting a weaker depth (C3), is unstable on explicit advanced evidence (C4) and borderline working-knowledge evidence (C2), and once in six runs asserted a PRESENT exclusion on an unrelated sentence (A). The structural parts of the contract held; this part is a model-capability limit. Options for review: a larger model for the depth and exclusion passes, or a REPRESENTATION change (ask the model to CLASSIFY the depth the evidence shows, none / mention / working / hands-on / advanced, with a quote, and compare it deterministically with the check's depth, so "advanced meets working knowledge" is code, not a judgment).
2. **Binding over-reach (VALIDATION).** 47 legitimate verdicts on multi-word category skills were discarded (section 6). Narrow it before the Evidence Check is relied on for recall.
3. **An unsupported PRESENT is INSUFFICIENT_EVIDENCE.** Conservative and distinct, but a policy: a profile that clearly describes other work, with a wrong PRESENT from the model, could arguably be NOT_PRESENT.
4. **Exclusion predicates rest on one knowledge anchor.** The security-operations identity is approved, versioned knowledge (the same status as the role-family taxonomy); every other exclusion phrase gets a structural predicate (its own words, the recruiter's qualifier, no expansion). The structural form is exercised on the Role 3 audit exclusion and the other two Role 1 exclusions, but it is unproven across phrasings.
5. **Category skills are not bound lexically**, so a category check still relies on the model and the review pass (the previous phase's reviewer inconsistency did not recur on Java: the Java depth claims passed 6/6 with the complete claim as the review input).
6. **Depth is lifted from prose only from an explicit leading phrase** ('Working knowledge of ...'); the compiler's structured proficiency is used otherwise. Nothing is inferred from a verb.
7. **The quote retry works but costs calls**: it recovered most failed quotes; the unrecovered ones stay discarded and visible.
8. **A PRESENT exclusion still has no downstream consumer**, path allocation and result merging are unchanged, and everything is synthetic.

## 9. Hard stop
No CrustData. No retrieval. No deployment. Paths, path allocation and result merging are unchanged. Waiting for architecture review.
