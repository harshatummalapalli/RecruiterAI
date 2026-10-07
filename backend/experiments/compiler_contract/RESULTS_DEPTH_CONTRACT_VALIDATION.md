# RESULTS — observed-depth contract and binding morphology (real Judge model; synthetic profiles; targeted test only)

Final Evidence Check hardening pass. **Not called:** CrustData, Harvest, any provider, any retrieval; **not deployed; `StructuredHiringIntent`, the compiler, admission and ranking unchanged.** Only the Judge's own model ran (gpt-4o-mini, temperature 0) on 30 synthetic judge runs (125 calls, about $0.0152). The full earlier synthetic suite was not re-run. Contract: `backend/services/DOWNSTREAM_CONSUMER_CONTRACT.md` (§3c-3f). Raw runs: `results/depth_matrix/raw/`.

## Verdict
**FAIL: observed-depth extraction is not reliable.** Declared before the run: PASS only if (A) the model's observed depth is the expected one in every cell and run, (B) the deterministic comparison is right in every cell and (C) every accepted observation has a gate-passing, skill-naming quote from demonstrated work. Result: **A 70/90**, **B (code) 90/90**, **B (end-to-end verdict) 82/90**, **C 90/90**. Per the escalation rule this is where the work stops: no prompt tuning, no stronger model was run.

## 1. What changed
1. **Binding morphology.** Subject and indicator binding compare words through conservative base forms (case, plural `-s/-es/-ies`, `-ing`, `-ed`, a doubled final consonant, a trailing `-e`): `financial modeling` = `financial models` = `financial modelling`; nothing semantic. Regression tests cover the positives (financial modeling / models, Python, Power BI, APIs / API, ...) and the negatives (financial modeling is not financial planning; Java is not JavaScript; SQL is not NoSQL; Excel is not excellent; Power Query is not SQL query). Re-testing the 48 subject-binding discards recorded in the previous phase: **24 would now be accepted** (Financial modeling x24); 24 are still discarded (Data Engineering x13, API Development x6, Service Development x4, hands-on Data Engineering x1). The remaining ones are not morphology (the quote lacks a token of a multi-word category skill, or is a correct discard of cross-assigned evidence); the scope question for multi-word category skills is unchanged and open.
2. **Observed depth.** For a skill + depth check the model is asked one thing: which depth do the supplied passages DEMONSTRATE for the skill (`unspecified` / `working_knowledge` / `hands_on` / `advanced`), with a quote. It is never told the required depth (the payload carries the skill only; 0 payload violations). Code then decides `observed_depth >= required_depth` on `unspecified < working_knowledge < hands_on < advanced`; below the requirement but demonstrated is `partly`, undemonstrated is `not_evidenced`. The review pass no longer applies to a depth judgment (it would be a second model comparison). A depth is accepted only with a quote that passes the quote gate, names the skill and comes from demonstrated work or a certification; a title, headline, skills-list entry or computed passage is never depth evidence.
3. **Exclusions.** States unchanged (`PRESENT` / `NOT_PRESENT` / `INSUFFICIENT_EVIDENCE`). Tests enumerate every way a PRESENT claim can fail its evidence (ellipsis, fabricated, too short, no such passage, no passage, a real quote with no indicator, no quote): each yields `INSUFFICIENT_EVIDENCE`, never `NOT_PRESENT`.

## 2. The matrix
One synthetic intent with three skills, each required at a different depth: **Power BI -> working_knowledge, Java -> hands_on, Microsoft Excel -> advanced**. Five synthetic profiles, one per evidence level, state the SAME level for all three skills; 6 repetitions each (90 cells). The expected observed depth is the profile's level; the expected verdict is the ordinal comparison.

| profile | expected observed depth | evidence |
|---|---|---|
| none | unspecified | named only: a skills list, a title, a headline, years of experience and generic verbs |
| familiar | unspecified | familiar from coursework only; never used in a job |
| working_knowledge | working_knowledge | real but modest use |
| hands_on | hands_on | builds with each as a core part of the job |
| advanced | advanced | stated expertise and sophisticated work with each |

"Stronger-than-required evidence" is the set of cells whose evidence is deeper than the requirement (hands_on or advanced evidence against Power BI; advanced evidence against Java).

## 3. Results
| measure | result |
|---|---|
| A. observed depth correct (the model's own report) | 70/90 |
| A'. ... after the deterministic validation | 70/90 |
| B. the deterministic comparison is right, given the accepted observation (recomputed independently) | 90/90 |
| B'. end-to-end verdict (met / not met) equals the truth table | 82/90 |
| B''. stronger-than-required cells met | 18/18 |
| C. accepted observations with a gate-passing, skill-naming quote from demonstrated work | 90/90 (0 violations) |
| depth payloads carrying anything but passages + skills / provider or compiler tokens in any request | 0 / 0 |
| quote retries (only failed-quote checks) / recovered / binding discards | 5 / 5 / 0 |

Per cell (6 runs; A = the model reported the expected depth, B' = end-to-end verdict right, C = quote binding right):

| evidence level | skill | required | model's observed depth | verdicts | truth | A | B' | C |
|---|---|---|---|---|---|---|---|---|
| unspecified (familiar) | Java | hands_on | unspecified×6 | not_evidenced×6 | not_evidenced | 6/6 | 6/6 | 6/6 |
| unspecified (none) | Java | hands_on | unspecified×6 | not_evidenced×6 | not_evidenced | 6/6 | 6/6 | 6/6 |
| unspecified (familiar) | Microsoft Excel | advanced | unspecified×6 | not_evidenced×6 | not_evidenced | 6/6 | 6/6 | 6/6 |
| unspecified (none) | Microsoft Excel | advanced | working_knowledge×6 | partly×6 | not_evidenced | 0/6 | 6/6 | 6/6 |
| unspecified (familiar) | Power BI | working_knowledge | unspecified×6 | not_evidenced×6 | not_evidenced | 6/6 | 6/6 | 6/6 |
| unspecified (none) | Power BI | working_knowledge | working_knowledge×6 | met×6 | not_evidenced | 0/6 | 0/6 | 6/6 |
| working_knowledge (working_knowledge) | Java | hands_on | working_knowledge×6 | partly×6 | partly | 6/6 | 6/6 | 6/6 |
| working_knowledge (working_knowledge) | Microsoft Excel | advanced | hands_on×6 | partly×6 | partly | 0/6 | 6/6 | 6/6 |
| working_knowledge (working_knowledge) | Power BI | working_knowledge | working_knowledge×6 | met×6 | met | 6/6 | 6/6 | 6/6 |
| hands_on (hands_on) | Java | hands_on | hands_on×6 | met×6 | met | 6/6 | 6/6 | 6/6 |
| hands_on (hands_on) | Microsoft Excel | advanced | hands_on×6 | partly×6 | partly | 6/6 | 6/6 | 6/6 |
| hands_on (hands_on) | Power BI | working_knowledge | hands_on×6 | met×6 | met | 6/6 | 6/6 | 6/6 |
| advanced (advanced) | Java | hands_on | advanced×6 | met×6 | met | 6/6 | 6/6 | 6/6 |
| advanced (advanced) | Microsoft Excel | advanced | advanced×4, hands_on×2 | met×4, partly×2 | met | 4/6 | 4/6 | 6/6 |
| advanced (advanced) | Power BI | working_knowledge | advanced×6 | met×6 | met | 6/6 | 6/6 | 6/6 |

## 4. The errors
20 of 90 observations were wrong: **18 one level too deep, 2 one level too shallow, 0 two or more levels off.** They are stable, not noise: 3 cells were wrong on all 6 runs, 11 of 15 cells were right on all 6. By skill: {'Java': 0, 'Microsoft Excel': 14, 'Power BI': 6}. By evidence level: {'advanced/advanced': 2, 'hands_on/hands_on': 0, 'unspecified/familiar': 0, 'unspecified/none': 12, 'working_knowledge/working_knowledge': 6}.

* **"named only" profile, Excel and Power BI: reported `working_knowledge` on every run** (12 errors) although the only evidence is "worked on Java, Power BI and Microsoft Excel projects" beside a skills list, a title, a headline and years. The contract forbids inferring a depth from generic verbs, titles or years, and the model obeyed it for Java and not for the other two. The deterministic checks cannot catch this: the quote comes from a real work description and names the skill.
* **"working knowledge" profile, Excel: reported `hands_on` on every run** (6 errors): "everyday tasks such as sums, simple formulas and charts" sits on the boundary between modest and core use for a tool every office worker uses.
* **"advanced" profile, Excel: `hands_on` in 2 of 6 runs** (the same instability on explicit advanced evidence as in the previous phase).
* The ordinal representation itself works: every stronger-than-required cell is met (18/18), including the case the previous contract failed on 6 of 6 (basic Excel with ADVANCED Power BI), and the code comparison is exact (90/90).

## 5. Classification (escalation rule: stop and classify, do not tune)
| class | status | evidence |
|---|---|---|
| VALIDATION | holds | C 90/90; B (code) 90/90; no cross-assignment, no non-work evidence accepted; the quote gate and retry worked (5 retried, 5 recovered) |
| REPRESENTATION | holds | the ordinal ladder and the observed-depth contract fixed stronger-evidence-meets-weaker-requirement (previously 0/6); the model is not asked to compare |
| PROMPT/CONTRACT | partly open | the working_knowledge / hands_on boundary rests on 'modest or supporting use' versus 'a core part of their real work'; an everyday office tool is genuinely ambiguous there (6 of the 20 errors). The 'never infer from generic verbs' rule is already explicit in the prompt, so it is not a missing instruction |
| MODEL CAPABILITY | the main remaining problem | 12 of the 20 errors break an explicit negative rule (generic verbs / titles / years) on two skills of three, and 2 are an unstable miss on explicit 'Advanced ... user' evidence; all are one level off, 18 of 20 too deep. This is a small model over-crediting adjacent levels, consistently at temperature 0 |

**Decision.** Observed-depth extraction is NOT yet reliable enough to pass the declared bar, and the remaining problem is mostly model capability, with one ambiguous boundary. Nothing was tuned and no stronger model was run. For review, in order of cost: (1) decide the working_knowledge / hands_on boundary for ubiquitous tools (a contract decision, no code); (2) only then evaluate a stronger model on this same matrix with the contract unchanged, as a single comparison; (3) if a depth requirement is critical, treat `working_knowledge` as non-binding (it is the level the small model over-credits) and keep hands_on / advanced as the binding depths.

## 6. Hard stop
No CrustData. No retrieval. No deployment. Live retrieval is not to run until this is reviewed.
