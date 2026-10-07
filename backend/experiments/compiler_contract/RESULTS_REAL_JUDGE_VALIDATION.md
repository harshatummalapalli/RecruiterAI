# RESULTS — the REAL Judge on the downstream contract (synthetic candidates only)

Phase: validate the new downstream Judge contract with the **real Judge model** and **synthetic candidate evidence only**. **Not called:** CrustData, Harvest, any provider, any retrieval; **no real candidate data; not deployed.** The only external call is the Judge's own model (OpenAI, through the sandbox's proxy). Contract: `backend/services/DOWNSTREAM_CONSUMER_CONTRACT.md`. Raw outputs (every request and every verdict): `results/real_judge/`. Reproduce: `python -m backend.experiments.compiler_contract.real_judge_run run --runs 6`, then `analyze`, `admission`, and `build_real_judge_report`.

## Verdict
**NOT ALL ACCEPTANCE CRITERIA PASS STRICTLY; some fail even noise-adjusted.** Criteria not passing strictly: negatives are evaluated; proficiency is interpreted correctly (advanced != hands-on != working knowledge; unsupported depth is never asked); work mode is preserved (unresolved, distinct from geography, never asked, no candidate penalised); preferences stay preferences. See section 9 for each criterion and section 10 for what remains. The Judge's requirement and review prompts are unchanged (pinned by content hash); the only Judge change is the NEW exclusion pass the contract requires (negatives).

## 1. Configuration (what actually ran)
| | |
|---|---|
| model | gpt-4o-mini (the production `JUDGE_MODEL`), temperature 0 |
| requirement + review prompts | unchanged (sha256-pinned in `tests/test_real_judge_validation.py`) |
| exclusion pass | new (`_EXCLUSION_PROMPT`), same verified-quote gate; see the revision note in section 6 |
| judge runs | 186 (each scenario run the same number of times, same config, **no tuning between runs**) |
| model calls / tokens / estimated cost | 2157 / 1,094,001 in, 193,742 out / about $0.28 (list price assumption) |
| API failures / retried jobs | 0 / 6 (infrastructure retries only; a verdict is never retried) |
| input source | compiled, legacy (`compiled` = the context drove the Judge; `legacy` = the control arm) |

## 2. What the model is, and is not, given
* The model receives numbered **profile passages** and numbered **requirement texts** (and, in the exclusion pass, **exclusion texts**). Nothing else.
* **Interface-facing, not model-facing:** the sourcing path, provenance, strength, proficiency (beyond its wording, e.g. "hands-on Python"), the unresolved items, work mode, and the checklist itself. They live on the `JudgeChecklist` and in `JudgeOutcome`. The model is not asked to reconcile them, which is also why it cannot reconstruct or override them. **Unresolved items and context-only preferences are never sent to the model at all.**
* Leak scan over **every request the model received** (2157 calls): provider syntax / provider field names / compiler details (0 hits) and the legacy sentences of the conflict scenarios (0 hits). Asked-text audit over 162 compiled runs: 0 violations (an unresolved item, an exclusion, or a context-only preference asked as a positive requirement).

## 3. Synthetic scenarios
Every profile is invented text, labelled `SYNTHETIC PROFILE`, written once by hand before any run (`real_judge_scenarios.py`), and not edited between runs. The frozen compiled contexts are Role 1 run 3 (the run with real requirements exclusive to Path A and to Path B), Role 2 run 1, Role 3 run 1.

| group | cand. | title | designed to show |
|---|---|---|---|
| R1 (frozen run 3, real Path A / Path B) | A | Lead Data Analyst | satisfies Path A (domain), not Path B (no Power Query) |
| R1 (frozen run 3, real Path A / Path B) | B | Lead Data Analyst | satisfies Path B (Power Query), not Path A (no domain) |
| R1 (frozen run 3, real Path A / Path B) | C | Lead Data Analyst | satisfies both paths |
| R1 (frozen run 3, real Path A / Path B) | D | Lead Data Analyst | satisfies neither path (common obligations only) |
| R1 (frozen run 3, real Path A / Path B) | E | Lead Data Analyst | security-operations (SOC) background: the semantic exclusion |
| R1 (frozen run 3, real Path A / Path B) | F | Director of Legal Operations | preferences only (Relativity / Canopy / legal tech), no required skills |
| R2 (frozen run 1) | P1 | Software Engineer | hands-on Python and Java in production; working-level Jira and Azure DevOps |
| R2 (frozen run 1) | P2 | Graduate Trainee | only familiar with Python and Java (coursework), never shipped |
| R2 (frozen run 1) | P3 | Engineering Manager | LLM / RAG / agentic work in a PAST role that ended; now a manager who no longer builds |
| R2 (frozen run 1) | P4 | Forward Deployed Engineer | analogy title only: a Forward Deployed Engineer title, no engineering evidence |
| R3 (frozen run 1) | Q1 | FP&A Manager | advanced Excel + working-knowledge Power BI + full FP&A |
| R3 (frozen run 1) | Q2 | FP&A Manager | basic Excel + working-knowledge Power BI + full FP&A |
| R3 (frozen run 1) | Q3 | FP&A Manager | Q1 + fully remote (work mode) |
| R3 (frozen run 1) | Q4 | FP&A Manager | Q1 + a preferred-company background |
| R3 (frozen run 1) | Q5 | Statutory Auditor | exclusively audit / tax / bookkeeping, no FP&A: the exclusion |
| R3 (frozen run 1) | Q6 | FP&A Manager | early-career audit and tax, then substantive FP&A (qualified exclusion must NOT apply) |
| R3 (frozen run 1) | Q7 | FP&A Manager | FP&A with tax-planning inputs (adjacent, must NOT be excluded) |
| conflict (synthetic intent) | PY_PAST | Delivery Manager | used Python extensively in the PAST; no longer codes |
| conflict (synthetic intent) | PY_NOW | Backend Developer | uses Python today |
| conflict (synthetic intent) | PY_NONE | Accountant | no Python at all |
| conflict (synthetic intent) | NO_QUUX | Backend Developer | no Quuxcorp background |

## 4. Results per expectation (every run must agree for PASS; UNSTABLE = the runs disagree; N = runs)
An expectation is a statement of what a correct reading of the contract looks like for ONE candidate and ONE item (a verdict other than `met` counts as not met, as everywhere in the Judge). "asked / not asked" checks what the model was actually sent.

### Role 1 (Path A / Path B)
| expectation | cand. | context | check | item | status | runs passed | observed | why it must hold |
|---|---|---|---|---|---|---|---|---|
| R1-A-domain | A | PATH A | req_met | Cyber Incident Review and/or Data Breach Analysis | PASS | 6/6 | met | A states the domain; Path A requires it |
| R1-C-domain | C | PATH A | req_met | Cyber Incident Review and/or Data Breach Analysis | PASS | 6/6 | met |  |
| R1-B-no-domain | B | PATH A | req_not_met | Cyber Incident Review and/or Data Breach Analysis | PASS | 6/6 | not_evidenced | B has no domain evidence: Path A is not satisfied by B |
| R1-D-no-domain | D | PATH A | req_not_met | Cyber Incident Review and/or Data Breach Analysis | PASS | 6/6 | not_evidenced |  |
| R1-B-pq | B | PATH B | req_met | Power Query | PASS | 6/6 | met |  |
| R1-B-pq-wk | B | PATH B | req_met | working knowledge of Power Query | PASS | 6/6 | met |  |
| R1-C-pq | C | PATH B | req_met | Power Query | PASS | 6/6 | met |  |
| R1-A-no-pq | A | PATH B | req_not_met | Power Query | PASS | 6/6 | not_evidenced | A has no Power Query: Path B is not satisfied by A |
| R1-D-no-pq | D | PATH B | req_not_met | Power Query | PASS | 6/6 | not_evidenced |  |
| R1-PQ-waived-in-A | A | PATH A | not_asked | Power Query | PASS | 6/6 | not asked | Path A waives Power Query: it must not be asked |
| R1-PQ-asked-in-B | A | PATH B | asked | Power Query | PASS | 6/6 | asked | Path B requires Power Query |
| R1-domain-not-asked-in-B | A | PATH B | not_asked | Cyber Incident Review and/or Data Breach Analysis | PASS | 6/6 | not asked | the domain is Path A's obligation only |
| R1-domain-asked-in-A | A | PATH A | asked | Cyber Incident Review and/or Data Breach Analysis | PASS | 6/6 | asked |  |
| R1-E-soc-present | E | PATH A | excl_present | Generic cybersecurity or security-operations backgrounds are not equiv | FAIL | 0/6 | not_present | a SOC background is the excluded profile |
| R1-E-soc-present-B | E | PATH B | excl_present | Generic cybersecurity or security-operations backgrounds are not equiv | FAIL | 0/6 | not_present |  |
| R1-E-domain-not-met | E | PATH A | req_not_met | Cyber Incident Review and/or Data Breach Analysis | PASS | 6/6 | not_evidenced | cyber operations wording is not the domain |
| R1-A-soc-absent | A | PATH A | excl_not_present | Generic cybersecurity or security-operations backgrounds are not equiv | PASS | 6/6 | not_present | a candidate with the real domain is not the excluded profile |
| R1-C-soc-absent | C | PATH A | excl_not_present | Generic cybersecurity or security-operations backgrounds are not equiv | PASS | 6/6 | not_present |  |
| R1-B-soc-absent | B | PATH B | excl_not_present | Generic cybersecurity or security-operations backgrounds are not equiv | PASS | 6/6 | not_present |  |
| R1-D-soc-absent | D | PATH A | excl_not_present | Generic cybersecurity or security-operations backgrounds are not equiv | PASS | 6/6 | not_present |  |
| R1-F-pref-met | F | PATH A | pref_met | Relativity | UNSTABLE | 4/6 | met, partly | the preference IS evidenced |
| R1-F-pref-not-enough | F | PATH A | req_not_met | hands-on SQL | PASS | 6/6 | not_evidenced | a preference does not stand in for a requirement |
| R1-F-pref-not-enough-B | F | PATH B | req_not_met | hands-on Python | PASS | 6/6 | not_evidenced |  |
| R1-A-pref-missing-still-A | A | PATH A | req_met | Cyber Incident Review and/or Data Breach Analysis | PASS | 6/6 | met | A lacks Relativity / Canopy: it still meets Path A's requirement |
| R1-A-handson-sql | A | PATH A | req_met | hands-on SQL | PASS | 6/6 | met |  |
| R1-F-handson-sql-B | F | PATH B | req_not_met | hands-on SQL | PASS | 6/6 | not_evidenced |  |

### Role 2
| expectation | cand. | context | check | item | status | runs passed | observed | why it must hold |
|---|---|---|---|---|---|---|---|---|
| R2-P1-handson-python | P1 | ctx | req_met | hands-on Python | PASS | 6/6 | met | production Python every day is hands-on |
| R2-P1-handson-java | P1 | ctx | req_met | hands-on Java | FAIL | 0/6 | partly |  |
| R2-P2-handson-python | P2 | ctx | req_not_met | hands-on Python | PASS | 6/6 | not_evidenced | familiar != hands-on: depths are distinct |
| R2-P2-handson-java | P2 | ctx | req_not_met | hands-on Java | PASS | 6/6 | not_evidenced |  |
| R2-P1-wk-jira | P1 | ctx | req_met | working knowledge of Jira | UNSTABLE | 2/6 | met, not_evidenced |  |
| R2-no-invented-depth-llm | P3 | ctx | not_asked | hands-on Large Language Models | PASS | 6/6 | not asked | the source states no depth: never required |
| R2-no-invented-depth-rag | P3 | ctx | not_asked | hands-on Retrieval-Augmented Generation | PASS | 6/6 | not asked |  |
| R2-no-invented-depth-ai | P3 | ctx | not_asked | hands-on AI/ML Implementation | PASS | 6/6 | not asked |  |
| R2-plain-llm-asked | P3 | ctx | asked | Large Language Models | PASS | 6/6 | asked |  |
| R2-P3-llm-past-ok | P3 | ctx | req_met | Large Language Models | PASS | 6/6 | met | the relationship is unspecified: past use counts, current is not invented |
| R2-P3-rag-past-ok | P3 | ctx | req_met | Retrieval-Augmented Generation | PASS | 6/6 | met |  |
| R2-P3-agentic-past-ok | P3 | ctx | req_met | Agentic AI | PASS | 6/6 | met |  |
| R2-no-current-text | P3 | ctx | not_asked | Currently | PASS | 6/6 | not asked | no requirement text asks for present use |
| R2-analogy-not-asked | P4 | ctx | not_asked | Forward Deployed Engineer | PASS | 6/6 | not asked | a comparison title is not a requirement |
| R2-analogy-no-engineering | P4 | ctx | req_not_met | hands-on Python | PASS | 6/6 | not_evidenced | a matching analogy title does not evidence anything |

### Role 3
| expectation | cand. | context | check | item | status | runs passed | observed | why it must hold |
|---|---|---|---|---|---|---|---|---|
| R3-Q1-adv-excel | Q1 | ctx | req_met | advanced proficiency in Microsoft Excel | UNSTABLE | 4/6 | met, not_evidenced | advanced evidence meets an advanced requirement |
| R3-Q2-adv-excel | Q2 | ctx | req_not_met | advanced proficiency in Microsoft Excel | PASS | 6/6 | not_evidenced | basic Excel does not meet advanced |
| R3-Q2-excel-plain | Q2 | ctx | req_met | Microsoft Excel | UNSTABLE | 5/6 | met, partly | the plain skill (no depth) is met by use of Excel |
| R3-Q2-powerbi-wk | Q2 | ctx | req_met | Working knowledge of Power BI or a similar business intelligence/repor | UNSTABLE | 2/6 | met, partly | working knowledge is the weaker requirement: light Power BI use meets it where it does not meet advanced Excel |
| R3-Q1-powerbi-wk | Q1 | ctx | req_met | Working knowledge of Power BI or a similar business intelligence/repor | UNSTABLE | 3/6 | met, partly |  |
| R3-workmode-not-asked | Q3 | ctx | not_asked | hybrid | PASS | 6/6 | not asked | work mode is unresolved: never asked, never judged |
| R3-workmode-not-asked-2 | Q3 | ctx | not_asked | Working arrangement | PASS | 6/6 | not asked | and never rewritten into a requirement |
| R3-Q3-same-as-Q1 | Q3 | ctx | same_verdicts_as | Q1 | FAIL | 0/6 | 1 requirement item(s) differ: Microsoft Excel, 1 requirement item(s) differ: SAP\|Oracle\|Comparable ERP platfor | a remote candidate is not penalised on the requirements: work mode is not geography |
| R3-company-not-asked | Q4 | ctx | not_asked | Unilever | PASS | 6/6 | not asked | a preferred company is not a requirement |
| R3-Q4-same-as-Q1 | Q4 | ctx | same_verdicts_as | Q1 | FAIL | 0/6 | 1 requirement item(s) differ: SAP\|Oracle\|Comparable ERP platforms, 14 requirement item(s) differ: Budgeting; C | a preferred-company background does not change a requirement verdict |
| R3-Q5-excluded | Q5 | ctx | excl_present | Experience exclusively in statutory audit | PASS | 6/6 | present | exclusively audit / tax / bookkeeping, no FP&A |
| R3-Q6-not-broadened | Q6 | ctx | excl_not_present | Experience exclusively in statutory audit | PASS | 6/6 | not_present | audit history plus substantive FP&A: the qualification does not hold |
| R3-Q7-not-broadened | Q7 | ctx | excl_not_present | Experience exclusively in statutory audit | PASS | 6/6 | not_present | tax-adjacent FP&A is not the excluded profile |
| R3-Q1-not-excluded | Q1 | ctx | excl_not_present | Experience exclusively in statutory audit | PASS | 6/6 | not_present |  |

## 5. Legacy-vs-compiled conflict
The SearchIntent carries a conflicting legacy meaning together with the compiled context; the control arm gives the Judge ONLY the legacy sentence. Legacy: `Currently works with Python (required)`. Compiled: Python required, relationship **unspecified**. Second case: legacy `Works at Quuxcorp` (a hard requirement) against a compiled company **preference**.

| expectation | cand. | context | check | item | status | runs passed | observed | why it must hold |
|---|---|---|---|---|---|---|---|---|
| CF-compiled-asks-plain-python | PY_PAST | compiled_vs_legacy | asked | Python | PASS | 6/6 | asked | the compiled meaning is what is asked |
| CF-legacy-sentence-never-sent | PY_PAST | compiled_vs_legacy | not_asked | Currently | PASS | 6/6 | not asked | the legacy 'current' sentence never reaches the model |
| CF-past-python-meets-compiled | PY_PAST | compiled_vs_legacy | req_met | Python | PASS | 6/6 | met | past Python meets an UNSPECIFIED relationship: current is not reconstructed from the legacy intent |
| CF-current-python-meets-compiled | PY_NOW | compiled_vs_legacy | req_met | Python | PASS | 6/6 | met |  |
| CF-no-python-fails-compiled | PY_NONE | compiled_vs_legacy | req_not_met | Python | PASS | 6/6 | not_evidenced |  |
| CF-control-legacy-would-reject-past | PY_PAST | legacy_only_control | req_not_met | Currently works with Python (required) | PASS | 6/6 | not_evidenced | CONTROL: with only the legacy sentence the same candidate is rejected: the compiled path is what changed the outcome |
| CF-control-legacy-accepts-current | PY_NOW | legacy_only_control | req_met | Currently works with Python (required) | PASS | 6/6 | met |  |
| CO-compiled-company-not-asked | NO_QUUX | compiled_vs_legacy | not_asked | Quuxcorp | PASS | 6/6 | not asked | a preferred company is not a requirement: the legacy hard line is not asked |
| CO-control-legacy-asks-company | NO_QUUX | legacy_only_control | asked | Quuxcorp | PASS | 6/6 | asked | CONTROL: the legacy intent would have asked it as a requirement |

## 6. Negatives: the exclusion pass

### Exclusion pass: v1 and the v2 revision
The first exclusion prompt (v1, below) was written before any run. Its result on the Role 1 SOC exclusion is the failure recorded in the v1 table. **This is a documented revision made AFTER seeing v1, not a blind result**: the root cause (below) was fixed with a generic clarification, the same scenarios were re-run unchanged, and both tables are kept. The held-out checks (the Role 3 exclusions, which v1 already passed) show whether the revision broadened the exclusion.

**Probable cause (a hypothesis: the model returns a verdict, never a reason).** The Role 1 exclusion is worded as a statement of what does NOT count (`Generic cybersecurity or security-operations backgrounds are not equivalent to ...`), not as a profile, and v1 answered `not_present` for a SOC analyst on every run. v2 adds one generic rule for that wording. **v2 helped but did not fix it** (Path A: unstable; Path B, the same exclusion text: still never `present`), and on the held-out Role 3 exclusions it did not broaden anything (Q6, Q7, Q1 stay `not_present` on every run) but the true positive Q5 slipped from 6/6 to 5/6. No further revision was made: another prompt change on these same scenarios would be tuning to them, and the open question (single-claim exclusion calls, a bigger model, or rewording at the compiler) is for architecture review. The requirement prompt is not involved (unchanged, pinned by hash).

**v1 (as run, N=6):**

| expectation | cand. | context | check | item | status | runs passed | observed | why it must hold |
|---|---|---|---|---|---|---|---|---|
| R1-E-soc-present | E | PATH A | excl_present | Generic cybersecurity or security-operations backgrounds are not equiv | FAIL | 0/6 | not_present | a SOC background is the excluded profile |
| R1-E-soc-present-B | E | PATH B | excl_present | Generic cybersecurity or security-operations backgrounds are not equiv | FAIL | 0/6 | not_present |  |
| R1-A-soc-absent | A | PATH A | excl_not_present | Generic cybersecurity or security-operations backgrounds are not equiv | PASS | 6/6 | not_present | a candidate with the real domain is not the excluded profile |
| R1-C-soc-absent | C | PATH A | excl_not_present | Generic cybersecurity or security-operations backgrounds are not equiv | PASS | 6/6 | not_present |  |
| R1-B-soc-absent | B | PATH B | excl_not_present | Generic cybersecurity or security-operations backgrounds are not equiv | PASS | 6/6 | not_present |  |
| R1-D-soc-absent | D | PATH A | excl_not_present | Generic cybersecurity or security-operations backgrounds are not equiv | PASS | 6/6 | not_present |  |
| R3-Q5-excluded | Q5 | ctx | excl_present | Experience exclusively in statutory audit | PASS | 6/6 | present | exclusively audit / tax / bookkeeping, no FP&A |
| R3-Q6-not-broadened | Q6 | ctx | excl_not_present | Experience exclusively in statutory audit | PASS | 6/6 | not_present | audit history plus substantive FP&A: the qualification does not hold |
| R3-Q7-not-broadened | Q7 | ctx | excl_not_present | Experience exclusively in statutory audit | PASS | 6/6 | not_present | tax-adjacent FP&A is not the excluded profile |
| R3-Q1-not-excluded | Q1 | ctx | excl_not_present | Experience exclusively in statutory audit | PASS | 6/6 | not_present |  |

**v2 (N=6):**

| expectation | cand. | context | check | item | status | runs passed | observed | why it must hold |
|---|---|---|---|---|---|---|---|---|
| R1-E-soc-present | E | PATH A | excl_present | Generic cybersecurity or security-operations backgrounds are not equiv | UNSTABLE | 3/6 | not_present, present | a SOC background is the excluded profile |
| R1-E-soc-present-B | E | PATH B | excl_present | Generic cybersecurity or security-operations backgrounds are not equiv | FAIL | 0/6 | not_present |  |
| R1-A-soc-absent | A | PATH A | excl_not_present | Generic cybersecurity or security-operations backgrounds are not equiv | PASS | 6/6 | not_present | a candidate with the real domain is not the excluded profile |
| R1-C-soc-absent | C | PATH A | excl_not_present | Generic cybersecurity or security-operations backgrounds are not equiv | PASS | 6/6 | not_present |  |
| R1-B-soc-absent | B | PATH B | excl_not_present | Generic cybersecurity or security-operations backgrounds are not equiv | PASS | 6/6 | not_present |  |
| R1-D-soc-absent | D | PATH A | excl_not_present | Generic cybersecurity or security-operations backgrounds are not equiv | PASS | 6/6 | not_present |  |
| R3-Q5-excluded | Q5 | ctx | excl_present | Experience exclusively in statutory audit | UNSTABLE | 5/6 | not_present, present | exclusively audit / tax / bookkeeping, no FP&A |
| R3-Q6-not-broadened | Q6 | ctx | excl_not_present | Experience exclusively in statutory audit | PASS | 6/6 | not_present | audit history plus substantive FP&A: the qualification does not hold |
| R3-Q7-not-broadened | Q7 | ctx | excl_not_present | Experience exclusively in statutory audit | PASS | 6/6 | not_present | tax-adjacent FP&A is not the excluded profile |
| R3-Q1-not-excluded | Q1 | ctx | excl_not_present | Experience exclusively in statutory audit | PASS | 6/6 | not_present |  |

**Every exclusion verdict, every candidate (present in how many runs), v1 vs v2.** Only the SOC exclusion for candidate E (Role 1) and the audit exclusion for Q5 (Role 3) are meant to be `present`; every other cell should be 0. The other two Role 1 exclusions are sub-profile statements ("A strong SQL/Python analyst working at a security firm", "Cyber or incident wording alone without relevant substantive evidence") that are not self-contained; they were not given pre-declared expectations, and their verdicts are reported as measured.

| group | candidate | context | exclusion | v1 present | v2 present |
|---|---|---|---|---|---|
| R1 | A | PATH A | A strong SQL/Python analyst working at a security firm | 5/6 | 4/6 |
| R1 | A | PATH A | Cyber or incident wording alone without relevant substantive e | 6/6 | 5/6 |
| R1 | A | PATH A | Generic cybersecurity or security-operations backgrounds are n | 0/6 | 0/6 |
| R1 | B | PATH A | A strong SQL/Python analyst working at a security firm | 0/6 | 0/6 |
| R1 | B | PATH A | Cyber or incident wording alone without relevant substantive e | 0/6 | 0/6 |
| R1 | B | PATH A | Generic cybersecurity or security-operations backgrounds are n | 0/6 | 0/6 |
| R1 | C | PATH A | A strong SQL/Python analyst working at a security firm | 1/6 | 6/6 |
| R1 | C | PATH A | Cyber or incident wording alone without relevant substantive e | 5/6 | 0/6 |
| R1 | C | PATH A | Generic cybersecurity or security-operations backgrounds are n | 0/6 | 0/6 |
| R1 | D | PATH A | A strong SQL/Python analyst working at a security firm | 0/6 | 0/6 |
| R1 | D | PATH A | Cyber or incident wording alone without relevant substantive e | 0/6 | 0/6 |
| R1 | D | PATH A | Generic cybersecurity or security-operations backgrounds are n | 0/6 | 0/6 |
| R1 | E | PATH A | A strong SQL/Python analyst working at a security firm | 0/6 | 0/6 |
| R1 | E | PATH A | Cyber or incident wording alone without relevant substantive e | 6/6 | 0/6 |
| R1 | E | PATH A | Generic cybersecurity or security-operations backgrounds are n | 0/6 | 3/6 |
| R1 | F | PATH A | A strong SQL/Python analyst working at a security firm | 6/6 | 0/6 |
| R1 | F | PATH A | Cyber or incident wording alone without relevant substantive e | 0/6 | 0/6 |
| R1 | F | PATH A | Generic cybersecurity or security-operations backgrounds are n | 0/6 | 0/6 |
| R3 | Q1 | ctx | Experience exclusively in statutory audit, tax, bookkeeping, o | 0/6 | 0/6 |
| R3 | Q2 | ctx | Experience exclusively in statutory audit, tax, bookkeeping, o | 0/6 | 0/6 |
| R3 | Q3 | ctx | Experience exclusively in statutory audit, tax, bookkeeping, o | 0/6 | 0/6 |
| R3 | Q4 | ctx | Experience exclusively in statutory audit, tax, bookkeeping, o | 0/6 | 0/6 |
| R3 | Q5 | ctx | Experience exclusively in statutory audit, tax, bookkeeping, o | 6/6 | 5/6 |
| R3 | Q6 | ctx | Experience exclusively in statutory audit, tax, bookkeeping, o | 0/6 | 0/6 |
| R3 | Q7 | ctx | Experience exclusively in statutory audit, tax, bookkeeping, o | 0/6 | 0/6 |

v1 exclusion system prompt, verbatim (recorded in every raw request):

```
You check whether a candidate's profile shows an EXCLUDED profile.

You get numbered PASSAGES copied from the candidate's profile and numbered EXCLUSIONS from the job. An exclusion describes a kind of
profile the hiring team does NOT want. For every exclusion decide:
- "present": the passages clearly show the candidate IS the excluded kind of profile, exactly as the exclusion words it.
- "not_present": they do not.

Rules:
1. Apply the exclusion as worded; never broaden it. A qualified exclusion (for example "exclusively X without Y", or "X alone") applies
   only when the whole qualification holds: a candidate with X AND Y, or with X plus other substantive experience, is "not_present".
2. Related, adjacent or partly overlapping experience is "not_present". Only the excluded profile itself is "present".
3. For "present" you MUST give the passage number and a quote copied EXACTLY, character for character, from that passage (at most 220
   characters). If you cannot quote it, answer "not_present".
4. Do not use outside knowledge about the person or their employers.

Return only JSON: {"results":[{"x":<exclusion number>,"verdict":"present|not_present","p":<passage number or null>,"quote":"<exact quote or empty>"}]}
Include every exclusion exactly once.
```

v2 (as run; recorded in every raw v2 request):

```
You check whether a candidate's profile shows an EXCLUDED profile.

You get numbered PASSAGES copied from the candidate's profile and numbered EXCLUSIONS from the job. An exclusion describes a kind of
profile the hiring team does NOT want. For every exclusion decide:
- "present": the passages clearly show the candidate IS the excluded kind of profile, exactly as the exclusion words it.
- "not_present": they do not.

Rules:
1. Apply the exclusion as worded; never broaden it. A qualified exclusion (for example "exclusively X without Y", or "X alone") applies
   only when the whole qualification holds: a candidate with X AND Y, or with X plus other substantive experience, is "not_present".
2. An exclusion is worded either as the profile itself ("experience exclusively in X") or as a statement of what does NOT count ("X
   backgrounds are not equivalent to Y", "X alone is not enough", "X wording without substantive evidence"). Read the second form as:
   a candidate whose relevant background is X, with no substantive evidence of Y itself, IS the excluded profile ("present"); a
   candidate who shows Y itself is "not_present".
3. Otherwise related, adjacent or partly overlapping experience is "not_present". Only the excluded profile itself is "present".
4. For "present" you MUST give the passage number and a quote copied EXACTLY, character for character, from that passage (at most 220
   characters). If you cannot quote it, answer "not_present".
5. Do not use outside knowledge about the person or their employers.

Return only JSON: {"results":[{"x":<exclusion number>,"verdict":"present|not_present","p":<passage number or null>,"quote":"<exact quote or empty>"}]}
Include every exclusion exactly once.
```


## 7. Model stability (semantic disagreement, not JSON differences)
Per (candidate, context, item): the verdict is compared across the runs and counted as a **semantic disagreement** only when the `met` / not-`met` category differs (a `partly` vs `not_evidenced` swap is minor and counted separately).

| | |
|---|---|
| (candidate, context, item) cells compared | 928 |
| semantic disagreements (met vs not met) | 104 |
| minor disagreements (partly vs not_evidenced) | 9 |
| exclusion-verdict disagreements | 5 |

Where the disagreements concentrate (top):

| group | candidate | context | items that flip |
|---|---|---|---|
| R3 | Q4 | ctx | 27 |
| R3 | Q3 | ctx | 24 |
| R3 | Q6 | ctx | 11 |
| R3 | Q7 | ctx | 11 |
| R3 | Q1 | ctx | 8 |
| R3 | Q2 | ctx | 8 |
| R2 | P1 | ctx | 4 |
| R1 | B | PATH B | 3 |
| R1 | F | PATH A | 3 |
| R1 | C | PATH A | 2 |
| R1 | C | PATH B | 2 |
| R1 | D | PATH B | 1 |

**Collapse events.** 4 of 186 runs produced ZERO verified `met` while the other runs of the same candidate produced many (post-hoc, objective definition: zero verified `met` while a majority of the other runs have 5 or more): R3/Q3/ctx/run2, R3/Q4/ctx/run3, R3/Q4/ctx/run4, R3/Q4/ctx/run6. For the 2 of these whose raw response was kept, the model said `met` for 52 claims and 52 of those quotes contained an ellipsis; the existing verified-quote gate discarded them, so the run read as nothing evidenced. A collapse is not a verdict about the candidate.

**Invariance baseline (collapsed runs excluded; supplementary and post-hoc, the strict expectation above is unchanged).** "Same verdicts as Q1" is judged against the model's own run-to-run noise: if two runs of the SAME candidate already differ on about as many items as two different candidates do, the invariance test cannot show an effect of the work mode or the preferred company.

| expectation | runs used (cand., other) | items that differ between two runs of the same candidate | items that differ between the two candidates | same-run pairs | pairs with zero difference |
|---|---|---|---|---|---|
| R3-Q3-same-as-Q1 | [5, 6] | 2.8 | 2.33 | 2.6 | 4/30 |
| R3-Q4-same-as-Q1 | [2, 6] | 2.8 | 2.67 | 1.5 | 0/12 |

Met count per run (first-pass verdicts after the verified-quote gate and the review pass) for every compiled-context candidate:

| group | context | cand. | runs | met per run | items asked | exclusions present |
|---|---|---|---|---|---|---|
| R1 | PATH A | A | 6 | 19/19/19/19/19/19 | 29 | A strong SQL/Python analyst working at a security firm; Cyber or incident wording alone wi |
| R1 | PATH A | B | 6 | 17/17/17/17/17/17 | 29 |  |
| R1 | PATH A | C | 6 | 20/20/19/20/18/19 | 29 | A strong SQL/Python analyst working at a security firm; Cyber or incident wording alone wi |
| R1 | PATH A | D | 6 | 17/17/17/17/17/17 | 29 |  |
| R1 | PATH A | E | 6 | 17/17/17/17/17/17 | 29 | Cyber or incident wording alone without relevant substantive |
| R1 | PATH A | F | 6 | 2/2/0/3/0/2 | 29 | A strong SQL/Python analyst working at a security firm |
| R1 | PATH B | A | 6 | 17/17/17/17/17/17 | 29 | A strong SQL/Python analyst working at a security firm; Cyber or incident wording alone wi |
| R1 | PATH B | B | 6 | 19/19/16/19/19/19 | 29 |  |
| R1 | PATH B | C | 6 | 19/19/19/19/19/19 | 29 | Cyber or incident wording alone without relevant substantive |
| R1 | PATH B | D | 6 | 17/16/16/16/16/17 | 29 |  |
| R1 | PATH B | E | 6 | 16/16/16/16/16/16 | 29 | Cyber or incident wording alone without relevant substantive |
| R1 | PATH B | F | 6 | 2/2/2/2/2/2 | 29 | A strong SQL/Python analyst working at a security firm |
| R2 | ctx | P1 | 6 | 6/7/9/9/7/7 | 82 |  |
| R2 | ctx | P2 | 6 | 0/0/0/0/0/0 | 82 |  |
| R2 | ctx | P3 | 6 | 5/5/5/5/5/5 | 82 |  |
| R2 | ctx | P4 | 6 | 0/0/0/0/0/0 | 82 |  |
| R3 | ctx | Q1 | 6 | 18/22/14/18/14/19 | 35 |  |
| R3 | ctx | Q2 | 6 | 13/13/17/13/18/14 | 35 |  |
| R3 | ctx | Q3 | 6 | 19/0/22/17/19/18 | 35 |  |
| R3 | ctx | Q4 | 6 | 22/7/0/0/23/0 | 35 |  |
| R3 | ctx | Q5 | 6 | 0/0/0/0/0/0 | 35 | Experience exclusively in statutory audit, tax, bookkeeping, |
| R3 | ctx | Q6 | 6 | 27/27/17/22/26/17 | 35 |  |
| R3 | ctx | Q7 | 6 | 16/20/18/22/20/21 | 35 |  |

## 8. Admission (deterministic gate, fed the compiled facts; thresholds and level rules unchanged)
**R1 PATH A: Lead (+Senior alternative) are PREFERRED** (target level `None`, accepted `[]`, floor `None`, ungated: ['Lead (PREFERENCE_CONTEXT)', 'Senior (PREFERENCE_CONTEXT)']). a preferred level never gates admission: every candidate is admitted; the legacy reading of the same level would have excluded some.

| cand. | title | start | level_fit | experience_floor | compiled facts | the same fact read as required (legacy) |
|---|---|---|---|---|---|---|
| lead | Lead Data Analyst | 2016 | None | None | admitted | admitted |
| senior | Senior Data Analyst | 2016 | None | None | admitted | excluded: level_below_target |
| director | Director of Legal Operations | 2016 | None | None | admitted | excluded: level_above_target |
| junior | Junior Data Analyst | 2016 | None | None | admitted | excluded: level_below_target |
| no_level | Data Analyst | 2016 | None | None | admitted | admitted |
| short_tenure | Lead Data Analyst | 2024 | None | None | admitted | excluded: below_experience_floor |

**R1 PATH B: Lead is REQUIRED, 6+ years** (target level `Lead`, accepted `[]`, floor `6`, ungated: none). the required level and floor gate, with the unchanged rule.

| cand. | title | start | level_fit | experience_floor | compiled facts | the same fact read as required (legacy) |
|---|---|---|---|---|---|---|
| lead | Lead Data Analyst | 2016 | aligned | True | admitted | admitted |
| senior | Senior Data Analyst | 2016 | below | True | EXCLUDED: level_below_target | excluded: level_below_target |
| director | Director of Legal Operations | 2016 | above | True | EXCLUDED: level_above_target | excluded: level_above_target |
| junior | Junior Data Analyst | 2016 | below | True | EXCLUDED: level_below_target | excluded: level_below_target |
| no_level | Data Analyst | 2016 | unclear | True | admitted | admitted |
| short_tenure | Lead Data Analyst | 2024 | aligned | False | EXCLUDED: below_experience_floor | excluded: below_experience_floor |

**synthetic: Senior required, Lead accepted as an alternative (OR)** (target level `Senior`, accepted `['Lead']`, floor `None`, ungated: none). OR semantics: a Lead is aligned (not 'above'); a Senior is aligned; a Director is above both and is excluded; a Junior is below both.

| cand. | title | start | level_fit | experience_floor | compiled facts | the same fact read as required (legacy) |
|---|---|---|---|---|---|---|
| lead | Lead Engineer | 2012 | aligned | None | admitted | excluded: level_above_target |
| senior | Senior Engineer | 2012 | aligned | None | admitted | admitted |
| director | Director of Engineering | 2012 | above | None | EXCLUDED: level_above_target | excluded: level_above_target |
| junior | Junior Engineer | 2012 | below | None | EXCLUDED: level_below_target | excluded: level_below_target |
| no_level | Engineer | 2012 | unclear | None | admitted | admitted |

**synthetic: Senior is PREFERRED** (target level `None`, accepted `[]`, floor `None`, ungated: ['Senior (PREFERENCE_CONTEXT)']). preferred never rejects.

| cand. | title | start | level_fit | experience_floor | compiled facts | the same fact read as required (legacy) |
|---|---|---|---|---|---|---|
| lead | Lead Engineer | 2012 | None | None | admitted | excluded: level_above_target |
| senior | Senior Engineer | 2012 | None | None | admitted | admitted |
| director | Director of Engineering | 2012 | None | None | admitted | excluded: level_above_target |
| junior | Junior Engineer | 2012 | None | None | admitted | excluded: level_below_target |
| no_level | Engineer | 2012 | None | None | admitted | admitted |

**synthetic: Staff (no approved level mapping) is UNRESOLVED** (target level `None`, accepted `[]`, floor `None`, ungated: ['Staff (UNRESOLVED)']). an unresolved level is not invented: nobody is gated on it, and it stays visible (ungated).

| cand. | title | start | level_fit | experience_floor | compiled facts | the same fact read as required (legacy) |
|---|---|---|---|---|---|---|
| lead | Lead Engineer | 2012 | None | None | admitted | admitted |
| senior | Senior Engineer | 2012 | None | None | admitted | excluded: level_below_target |
| director | Director of Engineering | 2012 | None | None | admitted | excluded: level_above_target |
| junior | Junior Engineer | 2012 | None | None | admitted | excluded: level_below_target |
| no_level | Engineer | 2012 | None | None | admitted | admitted |


## 8b. Reading the failures (computed from the runs above; what each is, and what it is not)
| expectation(s) | what the runs show | cause |
|---|---|---|
| R2-P1-handson-java | the SAME quote that makes `hands-on Python` met is the evidence for `hands-on Java`; the verdict is `partly` in 6/6 runs and the review pass downgraded it in 6 | the production REVIEW pass (a second model reading only the requirement and the quote) disagreeing with the first pass on a proficiency-prefixed requirement; not the downstream context |
| R1-F-pref-met, R2-P1-wk-jira, R3-Q1-adv-excel, R3-Q2-excel-plain, R3-Q2-powerbi-wk, R3-Q1-powerbi-wk | the verdict flips between runs on borderline evidence (a light statement of tool use, or a long passage) | likely model noise at temperature 0 and quote-gate discards (section 7); the cause was not isolated per item |
| R3-Q3-same-as-Q1, R3-Q4-same-as-Q1 | strictly FAIL (a single differing requirement item in any run fails it); against the model's own noise the candidates are indistinguishable (section 7) | consistent with model noise and quote-gate discards rather than an effect of the work mode or of the preferred company (a supplementary reading, section 7) |
| R1-E-soc-present | v1 0/6; v2 3/6 (Path A) and 0/6 (Path B, the same exclusion text) | the exclusion pass is unreliable for an exclusion worded as 'X backgrounds are not equivalent to Y' (probable cause; section 6); the other two Role 1 exclusions (sub-profile fragments, no pre-declared expectation) are also read inconsistently |

## 9. Acceptance
Strict = every run of every expectation agrees. Noise-adjusted differs only for the two "same requirement verdicts as Q1" invariance expectations, judged against the model's own run-to-run noise (supplementary, post-hoc; section 7). An UNSTABLE expectation is never adjusted.

| criterion | strict | noise-adjusted | evidence |
|---|---|---|---|
| the real Judge consumes the downstream context correctly (path obligations preserved, nothing reconstructed) | PASS | PASS | 13/13 expectations pass on every run |
| negatives are evaluated | FAIL | FAIL | 7/10 expectations pass on every run (exclusions: after the v2 revision) |
| proficiency is interpreted correctly (advanced != hands-on != working knowledge; unsupported depth is never asked) | FAIL | FAIL | 9/15 expectations pass on every run |
| work mode is preserved (unresolved, distinct from geography, never asked, no candidate penalised) | FAIL | PASS | 2/3 expectations pass on every run |
| unsupported `current` is not invented; an analogy title is not a target | PASS | PASS | 7/7 expectations pass on every run |
| preferences stay preferences | FAIL | UNSTABLE | 6/8 expectations pass on every run |
| compiled meaning beats legacy meaning | PASS | PASS | 7/7 expectations pass on every run |
| no provider syntax, compiler detail or legacy sentence reaches the Judge | PASS | PASS | 0 provider/compiler-token hits and 0 legacy-sentence hits over every request the model received (2157 calls) |
| unresolved items remain unresolved (never asked, never judged) | PASS | PASS | 162 compiled-context runs: 0 unresolved / exclusion / context-only items were asked as positives |
| a preferred requirement does not gate admission | PASS | PASS | every candidate admitted under Path A (Lead / Senior preferred); the same facts read as required would have excluded 4 of 6 |
| accepted alternative levels are OR | PASS | PASS | level_fit by candidate: {'lead': 'aligned', 'senior': 'aligned', 'director': 'above', 'junior': 'below', 'no_level': 'unclear'} |
| unresolved seniority is not invented | PASS | PASS | Staff: no candidate gated, level_fit None, the level kept visible as UNRESOLVED |

## 10. Remaining integration gaps
1. **The real Judge's quote gate collapses a run when the model writes an ellipsis in a quote.** The production gate (a quote must appear verbatim in the cited passage) correctly discards a quote containing `...`; when the model does this for every claim, the whole run reads as "nothing evidenced". Seen in this phase on the unchanged requirement prompt (see section 7). This is existing production behaviour, not the new contract, and it makes a single run unreliable as an exclusion; a decision is needed (re-ask on mass-discard, or verify the fragments around an ellipsis).
2. **What a `present` exclusion does is undefined.** The verdict exists and is evidenced, but nothing in ranking, admission or the recruiter view reads it.
3. **Pipeline wiring is not done** (contract section 9): the compiled filter tree has no provider adapter, the budget N -> 50 -> 25 across paths and the admission rule for a candidate found by several paths are undecided, and the intake does not capture a separate recruiter / HM brief (the shadow now accepts it).
4. **Real-model verdicts are not deterministic** even at temperature 0 (section 7); an expectation that must hold on every run is a strict bar for a 30-80 item prompt.
5. The scenarios are synthetic and small; they prove the contract is consumed, not that the Judge is accurate on real profiles.

## 11. Hard stop
No CrustData. No live retrieval. No deployment. Waiting for architecture review.
