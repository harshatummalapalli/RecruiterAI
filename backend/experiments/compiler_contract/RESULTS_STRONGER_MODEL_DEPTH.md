# RESULTS — stronger Judge model on the frozen depth matrix

Architecture decision applied: the Evidence Check representation, observed depth + deterministic comparison and quote binding are accepted; `working_knowledge` stays binding; the recruiter requirement is not weakened. **The only experimental variable is the Judge model.** Not called: CrustData, Harvest, any provider, any retrieval; not deployed; `StructuredHiringIntent`, the compiler, the Evidence Check schema, the verifier and quote gate, the requirement / exclusion / depth prompts, the evidence wording and the acceptance rules are unchanged (the same code and the same stored matrix). Reproduce: `python -m backend.experiments.compiler_contract.depth_compare` then `build_stronger_model_report`.

## Verdict
**EVIDENCE-INTERPRETATION CONTRACT LIMITATION.** The stronger model does NOT materially reduce the wrong observed-depth classifications: **20 -> 24** (-20% reduction), with 0 quote-gate / binding / check-id / comparison violations (before: 0). Rule applied, declared before the run: material improvement = at least a 50% relative reduction in wrong observed-depth classifications, with no increase in quote-gate, binding, check-id or comparison violations (declared before the stronger-model run). Per the instruction this stops here: no prompt tuning, no schema change, no domain-specific rule.

## 1. Exact model and configuration
| | gpt-4o-mini (frozen) | gpt-4.1 (this run) |
|---|---|---|
| model requested | `gpt-4o-mini` | `gpt-4.1` (the API resolved the alias to `gpt-4.1-2025-04-14` when probed) |
| API / format / temperature | Responses API, JSON object output, temperature 0 | identical: Responses API, JSON object output, temperature 0 (accepted without change) |
| retries / timeout | SDK max_retries 3, 120 s | identical |
| prompts, matrix, checks, evaluator | frozen | identical code, identical stored matrix (5 evidence levels x 3 skills x 6 runs = 90 cells) |
| runs / calls / tokens | 30 / 125 / 71,071 in, 7,431 out | 30 / 132 / 71,790 in, 7,746 out |
| API failures | 0 | 0 |

The two models were never used in the same request: the gpt-4o-mini numbers are the stored, frozen runs of the previous experiment; the gpt-4.1 numbers are 30 new, separate runs. The whole Judge ran on gpt-4.1 for those runs (the plain-skill checks and the review pass included); only the depth cells are scored here. Required semantics unchanged: `unspecified < working_knowledge < hands_on < advanced`; `observed >= required` satisfied; `observed < required` not satisfied (`partly`, never counted as evidence); `unspecified` insufficient evidence (`not_evidenced`); nothing is ever converted into a pass.

## 2. Headline comparison
| measure | gpt-4o-mini (frozen) | gpt-4.1 |
|---|---|---|
| A. observed-depth accuracy (the model's own report) | 70/90 (78%) | 66/90 (73%) |
| B. deterministic comparison, recomputed independently | 90/90 (100%) | 90/90 (100%) |
| C. end-to-end verdict, met / not met | 82/90 (91%) | 84/90 (93%) |
| C'. end-to-end verdict, three-way (satisfied / not satisfied / insufficient) | 76/90 (84%) | 72/90 (80%) |
| C''. stronger-than-required evidence satisfied | 18/18 (100%) | 18/18 (100%) |
| D. accepted depths whose quote fails the gate | 0 | 0 |
| D. first-pass depth claims failing the gate (retried / recovered) | 0 of 66 (5 / 5) | 0 of 72 (0 / 0) |
| E. judgments with an unknown / duplicate check_id | 0 | 0 |
| E. accepted quotes not naming their own skill / not from demonstrated work | 0 / 0 | 0 / 0 |
| E. proposals discarded by binding (cross-check attempts) | 0 (0) | 0 (0) |
| required depth sent to the model / provider or compiler tokens in any request | 0 / 0 | 0 / 0 |
| estimated cost of the 30 runs (list-price assumption) | $0.0151 | $0.2055 |

## 3. Observed-depth accuracy by skill, by evidence level and by required depth
| skill | gpt-4o-mini | gpt-4.1 |
|---|---|---|
| Power BI | 24/30 (80%) | 24/30 (80%) |
| Java | 30/30 (100%) | 24/30 (80%) |
| Microsoft Excel | 16/30 (53%) | 18/30 (60%) |

| evidence level (expected observed depth) | gpt-4o-mini | gpt-4.1 |
|---|---|---|
| none (expected unspecified) | 6/18 (33%) | 0/18 (0%) |
| familiar (expected unspecified) | 18/18 (100%) | 18/18 (100%) |
| working_knowledge (expected working_knowledge) | 12/18 (67%) | 12/18 (67%) |
| hands_on (expected hands_on) | 18/18 (100%) | 18/18 (100%) |
| advanced (expected advanced) | 16/18 (89%) | 18/18 (100%) |

| required depth of the check | gpt-4o-mini | gpt-4.1 |
|---|---|---|
| working_knowledge | 24/30 (80%) | 24/30 (80%) |
| hands_on | 30/30 (100%) | 24/30 (80%) |
| advanced | 16/30 (53%) | 18/30 (60%) |

## 4. Systematic bias and instability
|  | gpt-4o-mini | gpt-4.1 |
|---|---|---|
| wrong observations | 20 | 24 |
| ... one level too deep | 18 | 24 |
| ... one level too shallow | 2 | 0 |
| ... two or more levels off | 0 | 0 |
| mean signed error, all 90 (+ = too deep) | 0.178 | 0.267 |
| mean signed error, wrong ones only | 0.8 | 1.0 |
| cells with run-to-run disagreement (of 15) | 1 | 0 |
| cells wrong on all 6 runs | 3 | 4 |
| cells right on all 6 runs | 11 | 11 |

Both models err almost only upward, by exactly one level (gpt-4o-mini 18 of 20 errors, gpt-4.1 24 of 24), and they do it identically on every one of the 6 runs of a cell. Run-to-run instability is not the problem: gpt-4.1 removes the one unstable cell gpt-4o-mini had (explicit "Advanced Microsoft Excel user"), and it gets the "advanced", "hands-on" and "familiar" evidence levels right in every cell; but it is worse than gpt-4o-mini on the "named only" level.

## 5. The 90 cells (6 runs per cell; claimed = the model's observed depth; verdict = after the deterministic comparison)
| evidence | skill | expected depth | required | truth | 4o-mini claimed | 4o-mini verdicts | 4.1 claimed | 4.1 verdicts | 4o-mini A | 4.1 A |
|---|---|---|---|---|---|---|---|---|---|---|
| none | Power BI | unspecified | working_knowledge | not_evidenced | working_knowledgex6 | metx6 | working_knowledgex6 | metx6 | 0/6 | 0/6 |
| none | Java | unspecified | hands_on | not_evidenced | unspecifiedx6 | not_evidencedx6 | working_knowledgex6 | partlyx6 | 6/6 | 0/6 |
| none | Microsoft Excel | unspecified | advanced | not_evidenced | working_knowledgex6 | partlyx6 | working_knowledgex6 | partlyx6 | 0/6 | 0/6 |
| familiar | Power BI | unspecified | working_knowledge | not_evidenced | unspecifiedx6 | not_evidencedx6 | unspecifiedx6 | not_evidencedx6 | 6/6 | 6/6 |
| familiar | Java | unspecified | hands_on | not_evidenced | unspecifiedx6 | not_evidencedx6 | unspecifiedx6 | not_evidencedx6 | 6/6 | 6/6 |
| familiar | Microsoft Excel | unspecified | advanced | not_evidenced | unspecifiedx6 | not_evidencedx6 | unspecifiedx6 | not_evidencedx6 | 6/6 | 6/6 |
| working_knowledge | Power BI | working_knowledge | working_knowledge | met | working_knowledgex6 | metx6 | working_knowledgex6 | metx6 | 6/6 | 6/6 |
| working_knowledge | Java | working_knowledge | hands_on | partly | working_knowledgex6 | partlyx6 | working_knowledgex6 | partlyx6 | 6/6 | 6/6 |
| working_knowledge | Microsoft Excel | working_knowledge | advanced | partly | hands_onx6 | partlyx6 | hands_onx6 | partlyx6 | 0/6 | 0/6 |
| hands_on | Power BI | hands_on | working_knowledge | met | hands_onx6 | metx6 | hands_onx6 | metx6 | 6/6 | 6/6 |
| hands_on | Java | hands_on | hands_on | met | hands_onx6 | metx6 | hands_onx6 | metx6 | 6/6 | 6/6 |
| hands_on | Microsoft Excel | hands_on | advanced | partly | hands_onx6 | partlyx6 | hands_onx6 | partlyx6 | 6/6 | 6/6 |
| advanced | Power BI | advanced | working_knowledge | met | advancedx6 | metx6 | advancedx6 | metx6 | 6/6 | 6/6 |
| advanced | Java | advanced | hands_on | met | advancedx6 | metx6 | advancedx6 | metx6 | 6/6 | 6/6 |
| advanced | Microsoft Excel | advanced | advanced | met | advancedx4, hands_onx2 | metx4, partlyx2 | advancedx6 | metx6 | 4/6 | 6/6 |

## 6. Where the errors are, and what the stronger model cites
Both models make the SAME two mistakes; the stronger model makes the first one on all three skills (gpt-4o-mini on two).
| profile / skill | what gpt-4.1 cites and claims (run 1) |
|---|---|
| none / Power BI | claimed working_knowledge: "worked on Java, Power BI and Microsoft Excel projects with the technology team." |
| none / Java | claimed working_knowledge: "worked on Java, Power BI and Microsoft Excel projects with the technology team." |
| none / Microsoft Excel | claimed working_knowledge: "worked on Java, Power BI and Microsoft Excel projects with the technology team." |
| working_knowledge / Microsoft Excel | claimed hands_on: "Uses Microsoft Excel for everyday tasks such as sums, simple formulas and charts." |

1. **"worked on X projects" read as working knowledge.** The only evidence is a work passage in which the candidate "worked on Java, Power BI and Microsoft Excel projects with the technology team", beside a skills list, a title, a headline and years. The depth prompt says in so many words that a depth must not be inferred from generic verbs, titles, years or lists. The deterministic checks cannot reject it: the quote is real, contiguous, from a work description and names the skill. gpt-4.1 treats "worked on / involved in" as demonstrating for all three skills, gpt-4o-mini for two.
2. **"uses Excel for everyday tasks such as sums, simple formulas and charts" read as hands-on.** The contract separates working knowledge ("real but modest or supporting use") from hands-on ("a core part of their real work") without saying what separates them in the evidence, so frequency of use ("everyday") is read as ownership.

## 7. Interpretation
The stronger model does **not** materially improve the failure pattern: errors go from 20 to 24, every one of them is a one-level over-credit, and they are perfectly repeatable at temperature 0 (the same cells are wrong on all 6 runs). A repeatable error that a stronger model reproduces, on the same evidence and with the same outcome, is a property of the question being asked, not of the weaker model. Classification: **EVIDENCE-INTERPRETATION CONTRACT LIMITATION**. Nothing in the validation layer failed (the quote gate, the binding, the check ids and the ordinal comparison are 100% correct for both models), so it is not a VALIDATION problem, and the representation (an observed depth compared by code) is not at fault: stronger-than-required evidence is satisfied in every cell for both models.

## 8. Smallest contract change to propose (not implemented; no domain-specific rule)
The depth label asks one model judgment to do two jobs at once: decide WHAT the candidate did and place it on a four-level scale whose boundaries are described only in prose. The smallest change that keeps the representation, the comparison and the bindings is to have the model report the **evidence it relied on** in a form code can check, and let code, not the model, apply the boundary:

1. Add one field to the depth observation: `action`, the exact words of the quote that say what the candidate DID with the skill (the verb phrase and its object). Code verifies, deterministically and generically, that `action` is a contiguous part of the already-verified quote and is not only an involvement phrase from a small generic list (`worked on`, `involved in`, `responsible for`, `part of`, `exposure to`, `familiar with`, `contributed to`, `assisted with`). An observation whose action is empty or only generic is `unspecified`, whatever depth the model claimed. This closes mistake 1 without any skill-specific rule and keeps the recruiter's requirement fully binding (an unprovable depth stays insufficient, never a pass).
2. Replace the two prose boundaries with one closed-set rubric the model must cite, applied identically to every skill: working_knowledge = the candidate used the skill for routine or basic tasks (stated as such: "simple", "basic", "occasional", "everyday tasks"); hands_on = the candidate built, wrote, configured or operated the skill's own artefacts as the work product; advanced = stated expertise, or design / optimisation / architecture of non-trivial work. This addresses mistake 2 by defining the boundary on what was done and its stated scope, not on how often.
Both are contract changes (what is asked and how it is checked), not model changes and not weakening of any requirement. They should be validated on this same matrix, once, before any further model decision.

## 9. Cost note
gpt-4.1 cost about $0.2055 against about $0.0151 for the same 30 runs (list-price assumption), roughly 14x, for no reduction in depth errors.

## 10. Hard stop
No CrustData. No retrieval. No deployment. No prompt tuning. No schema change. Waiting for architecture review.
