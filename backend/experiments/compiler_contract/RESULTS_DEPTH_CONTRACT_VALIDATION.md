# RESULTS — observed-depth contract, binding morphology and the evidence-basis ceiling (real Judge model; synthetic profiles; targeted test only)

Final Evidence Check hardening pass. **Not called:** CrustData, Harvest, any provider, any retrieval; **not deployed; `StructuredHiringIntent`, the compiler, admission and ranking unchanged.** Only the Judge's own model ran (gpt-4o-mini, temperature 0) on 30 synthetic judge runs (125 calls, about $0.0152). The full earlier synthetic suite was not re-run. Contract: `backend/services/DOWNSTREAM_CONSUMER_CONTRACT.md` (§3c-3f). Raw runs: `results/depth_matrix/raw/`.

## Verdict of the observed-depth pass (superseded by the final pass in §6)
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

## 6. Final pass: evidence basis and the deterministic ceiling
Declared before the run, in `depth_basis.py`: the **hard gate** is that no evidence is credited above the maximum depth the contract allows and no named-only / familiar cell is `met`; the quality bar is zero quote-gate / binding / check-id / comparison violations and at least 50% fewer false-positive depth cases than the frozen baseline. Model agreement was not the bar.

**What changed (and nothing else).** The depth pass now also returns an `evidence_basis` per skill: `explicit_depth` / `concrete_skill_use` / `routine_skill_use` / `generic_involvement` / `no_depth_evidence`. Code maps the basis to a CEILING (`no_depth_evidence`, `generic_involvement` -> unspecified; `routine_skill_use` -> working_knowledge; `concrete_skill_use` -> hands_on; `explicit_depth` -> the depth the quote itself states about the skill, else unspecified) and credits `min(model's observed_depth, ceiling)`; a missing or unrecognised basis supports nothing. The depth prompt gained only the basis definitions and output field; the matrix, evidence texts, checks, requirement / exclusion prompts, quote gate, binding, verifier and model (gpt-4o-mini, temperature 0) are the same (30 runs, 126 calls, about $0.0167). Raw runs: `results/depth_matrix/raw_basis/`; baseline: `results/depth_matrix/raw/`.

| measure | result |
|---|---|
| A. evidence_basis in the acceptable set for its level | 66/90 |
| B. observed_depth: model's own report / credited after the ceiling | 78/90 / 63/90 |
| C. maximum_supported_depth equals the evidence level | 63/90 |
| D. deterministic comparison right given the credited depth | 90/90 |
| E. final verdict: met / not met correct / three-way correct | 81/90 / 80/90 |
| F. quote gate: credited depths failing the gate / first-pass claims failing it / retried and recovered | 0 / 5 of 60 / 9 and 7 |
| G. binding: unknown or duplicate check_id / credited quote not naming its skill / not demonstrated work / discarded by binding | 0 / 0 / 0 / 4 |
| payload violations / provider or compiler tokens in any request / failed runs | 0 / 0 / 0 |

**The gate.**
| check | result | note |
|---|---|---|
| credited above the ceiling of its own evidence basis | 0 | 0 required |
| `met` on a named-only or familiar profile (36 cells) | 0 | 0 required |
| named-only / familiar verdicts | not_evidenced×36 | all insufficient |
| false-positive `met` (requirement not met by the evidence): baseline -> now | 6 -> 0 | unspecified\|Power BI\|required working_knowledge (baseline) |
| credited above the evidence's true level: baseline -> now | 18 -> 6 | working_knowledge\|Microsoft Excel\|credited hands_on |
| model claimed a depth above the evidence: baseline -> now (the model's own report) | 18 -> 12 |  |
| of today's model over-claims: capped by the ceiling / still credited too deep | 6 / 6 |  |
| of the baseline's 18 too-deep cells (same profile, skill, run): now credited at or below the evidence / not credited at all / still too deep | 12 / 12 / 6 |  |
| stronger-than-required cells met | 17/18 |  |

**Acceptance: ACCEPTED.** No evidence was credited above the ceiling (0), no named-only or familiar profile satisfied a depth requirement (0 of 36; every one is `not_evidenced`, i.e. insufficient evidence), structural violations 0, and false-positive depth cases fell 6 -> 0 (100% fewer). The depth contract is therefore accepted and is not to be tuned further.

Per cell (6 runs each; every column is a distribution over the 6 runs):

| evidence level | skill | required | evidence_basis | model's observed depth | ceiling | credited | verdicts | truth |
|---|---|---|---|---|---|---|---|---|
| unspecified (none) | Java | hands_on | no_depth_evidence×6 | unspecified×6 | unspecified×6 | unspecified×6 | not_evidenced×6 | not_evidenced |
| unspecified (none) | Microsoft Excel | advanced | no_depth_evidence×6 | unspecified×6 | unspecified×6 | unspecified×6 | not_evidenced×6 | not_evidenced |
| unspecified (none) | Power BI | working_knowledge | generic_involvement×6 | working_knowledge×6 | unspecified×6 | unspecified×6 | not_evidenced×6 | not_evidenced |
| unspecified (familiar) | Java | hands_on | no_depth_evidence×6 | unspecified×6 | unspecified×6 | unspecified×6 | not_evidenced×6 | not_evidenced |
| unspecified (familiar) | Microsoft Excel | advanced | no_depth_evidence×6 | unspecified×6 | unspecified×6 | unspecified×6 | not_evidenced×6 | not_evidenced |
| unspecified (familiar) | Power BI | working_knowledge | no_depth_evidence×6 | unspecified×6 | unspecified×6 | unspecified×6 | not_evidenced×6 | not_evidenced |
| working_knowledge (working_knowledge) | Java | hands_on | explicit_depth×1, routine_skill_use×5 | working_knowledge×6 | unspecified×1, working_knowledge×5 | unspecified×1, working_knowledge×5 | not_evidenced×1, partly×5 | partly |
| working_knowledge (working_knowledge) | Microsoft Excel | advanced | concrete_skill_use×6 | hands_on×6 | hands_on×6 | hands_on×6 | partly×6 | partly |
| working_knowledge (working_knowledge) | Power BI | working_knowledge | explicit_depth×2, routine_skill_use×4 | working_knowledge×6 | unspecified×2, working_knowledge×4 | unspecified×2, working_knowledge×4 | met×4, not_evidenced×2 | met |
| hands_on (hands_on) | Java | hands_on | concrete_skill_use×6 | hands_on×6 | hands_on×6 | hands_on×6 | met×6 | met |
| hands_on (hands_on) | Microsoft Excel | advanced | concrete_skill_use×6 | hands_on×6 | hands_on×6 | hands_on×6 | partly×6 | partly |
| hands_on (hands_on) | Power BI | working_knowledge | concrete_skill_use×6 | hands_on×6 | hands_on×6 | hands_on×6 | met×6 | met |
| advanced (advanced) | Java | hands_on | concrete_skill_use×6 | advanced×6 | hands_on×5, unspecified×1 | hands_on×5, unspecified×1 | met×5, not_evidenced×1 | met |
| advanced (advanced) | Microsoft Excel | advanced | concrete_skill_use×6 | advanced×6 | hands_on×6 | hands_on×6 | partly×6 | met |
| advanced (advanced) | Power BI | working_knowledge | concrete_skill_use×6 | advanced×6 | hands_on×6 | hands_on×6 | met×6 | met |

**What the ceiling did.** 23 of 90 observations were capped or voided by the ceiling or the missing-basis rule. It removed the exact failure of the previous pass: the "named only" profile ("worked on Java, Power BI and Microsoft Excel projects") is labelled `generic_involvement` / `no_depth_evidence` and the model's `working_knowledge` for Power BI is voided (6 of 6), and "advanced" claims resting on concrete use are limited to hands_on.

**What it did not fix, and what it costs (9 false negatives, all on the safe side):**
* **Over-crediting is not eliminated, only bounded by the model's own basis label.** The "working knowledge" profile's Excel text ("everyday tasks such as sums, simple formulas and charts") is labelled `concrete_skill_use` on 6 of 6 runs, so the ceiling allows hands_on; the result is still not a false positive only because the Excel requirement is `advanced`. A hands_on requirement on that evidence would have been over-credited. This is a model labelling limitation (the model treats everyday use as concrete use); it is not corrected by a further schema layer.
* **Genuinely advanced evidence is under-credited.** The advanced profile is labelled `concrete_skill_use` (not `explicit_depth`) on 18 of 18 observations although it contains "Advanced Java expert" / "Advanced Microsoft Excel user", so the ceiling is hands_on: the advanced Excel requirement is `partly` (6 of 6), not `met`. Under the contract an `advanced` requirement is satisfiable only when the model labels the evidence `explicit_depth` AND the quote itself states advanced proficiency ("advanced", "expert", "highly proficient", "mastery"); sophisticated concrete work alone is capped at hands_on by design.
* **Conservative voiding.** 4 observations were voided by the existing binding rule (the quote did not name its skill: "...with working knowledge of each"); they are insufficient evidence, not false positives.

Every under-credit lands in `partly` or `not_evidenced`. A recruiter sees "demonstrated but below the requirement" or "insufficient evidence", never a silent pass.

## 7. Hard stop
No CrustData. No retrieval. No deployment. Live retrieval is not to run until this is reviewed.
