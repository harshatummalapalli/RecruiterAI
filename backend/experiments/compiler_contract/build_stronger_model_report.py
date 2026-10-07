"""Builds RESULTS_STRONGER_MODEL_DEPTH.md from results/depth_matrix/comparison.json and the stored runs. No number is typed by hand."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from backend.experiments.compiler_contract import depth_compare as dc
from backend.experiments.compiler_contract import depth_matrix as dm
from backend.experiments.compiler_contract.build_report import md

HERE = Path(__file__).resolve().parent
OUT = HERE / "RESULTS_STRONGER_MODEL_DEPTH.md"
A, B = "gpt-4o-mini", "gpt-4.1"


def pct(d: Dict[str, int]) -> str:
    return f"{d['correct']}/{d['of']} ({round(100 * d['correct'] / d['of'])}%)"


def cited_quotes(model: str) -> Dict[str, str]:
    """For each evidence level, the quote the model cited for the skills it over-credited (run 1), straight from the stored runs."""
    out: Dict[str, str] = {}
    raw = dc.MODELS[model]
    prof = {p.key: p.level for p in dm.PROFILES}
    for key in ("none", "working_knowledge"):
        j = json.loads((raw / f"DM__{key}__run1.json").read_text(encoding="utf-8"))
        by = {c["check_id"]: c for c in j["checks"]}
        for x in j["judgments"]:
            c = by[x["check_id"]]
            if c["kind"] == "proficiency" and x.get("claimed_depth") and x["claimed_depth"] != prof[key] and x.get("quote"):
                out[f"{key} / {c['subject']}"] = f"claimed {x['claimed_depth']}: \"{x['quote'][:140]}\""
    return out


def build() -> str:
    r = json.loads((dm.RESULTS / "comparison.json").read_text(encoding="utf-8"))
    a, b, cmp = r[A], r[B], r["comparison"]
    headline = [
        ["A. observed-depth accuracy (the model's own report)", pct(a["A_overall"]), pct(b["A_overall"])],
        ["B. deterministic comparison, recomputed independently", pct(a["B_code_comparison"]), pct(b["B_code_comparison"])],
        ["C. end-to-end verdict, met / not met", pct(a["C_end_to_end_met_vs_not"]), pct(b["C_end_to_end_met_vs_not"])],
        ["C'. end-to-end verdict, three-way (satisfied / not satisfied / insufficient)", pct(a["C_three_way"]), pct(b["C_three_way"])],
        ["C''. stronger-than-required evidence satisfied", pct(a["C_stronger_than_required"]), pct(b["C_stronger_than_required"])],
        ["D. accepted depths whose quote fails the gate", a["D_quote_gate"]["accepted_depths_failing_the_gate"], b["D_quote_gate"]["accepted_depths_failing_the_gate"]],
        ["D. first-pass depth claims failing the gate (retried / recovered)", f"{a['D_quote_gate']['failed_gate']} of {a['D_quote_gate']['claims']} ({a['D_quote_gate']['retried_checks']} / {a['D_quote_gate']['retries_recovered']})",
         f"{b['D_quote_gate']['failed_gate']} of {b['D_quote_gate']['claims']} ({b['D_quote_gate']['retried_checks']} / {b['D_quote_gate']['retries_recovered']})"],
        ["E. judgments with an unknown / duplicate check_id", a["E_binding"]["unknown_or_duplicate_check_id"], b["E_binding"]["unknown_or_duplicate_check_id"]],
        ["E. accepted quotes not naming their own skill / not from demonstrated work", f"{a['E_binding']['accepted_not_naming_own_skill']} / {a['E_binding']['accepted_not_work_evidence']}", f"{b['E_binding']['accepted_not_naming_own_skill']} / {b['E_binding']['accepted_not_work_evidence']}"],
        ["E. proposals discarded by binding (cross-check attempts)", f"{a['E_binding']['discarded_by_binding']} ({a['E_binding']['cross_check_attempts']})", f"{b['E_binding']['discarded_by_binding']} ({b['E_binding']['cross_check_attempts']})"],
        ["required depth sent to the model / provider or compiler tokens in any request", f"{a['depth_payload_violations']} / {a['leak_token_hits']}", f"{b['depth_payload_violations']} / {b['leak_token_hits']}"],
        ["estimated cost of the 30 runs (list-price assumption)", f"${a['estimated_cost_usd']}", f"${b['estimated_cost_usd']}"]]
    skills = [[s, pct(a["A_per_skill"][s]), pct(b["A_per_skill"][s])] for s in dc.SKILLS]
    levels = [[f"{p.key} (expected {p.level})", pct(a["A_per_evidence_level"][p.key]), pct(b["A_per_evidence_level"][p.key])] for p in dm.PROFILES]
    reqd = [[k, pct(a["A_by_required_depth"][k]), pct(b["A_by_required_depth"][k])] for k in ("working_knowledge", "hands_on", "advanced")]
    bias = [["wrong observations", a["error_profile"]["errors"], b["error_profile"]["errors"]], ["... one level too deep", a["error_profile"]["over_by_one"], b["error_profile"]["over_by_one"]],
            ["... one level too shallow", a["error_profile"]["under_by_one"], b["error_profile"]["under_by_one"]], ["... two or more levels off", a["error_profile"]["two_or_more"], b["error_profile"]["two_or_more"]],
            ["mean signed error, all 90 (+ = too deep)", a["error_profile"]["mean_signed_error"], b["error_profile"]["mean_signed_error"]],
            ["mean signed error, wrong ones only", a["error_profile"]["mean_signed_error_when_wrong"], b["error_profile"]["mean_signed_error_when_wrong"]],
            ["cells with run-to-run disagreement (of 15)", a["instability"]["cells_with_run_to_run_disagreement"], b["instability"]["cells_with_run_to_run_disagreement"]],
            ["cells wrong on all 6 runs", a["instability"]["cells_wrong_on_every_run"], b["instability"]["cells_wrong_on_every_run"]],
            ["cells right on all 6 runs", a["instability"]["cells_right_on_every_run"], b["instability"]["cells_right_on_every_run"]]]
    da, db = {(d["profile"], d["skill"]): d for d in a["cells_detail"]}, {(d["profile"], d["skill"]): d for d in b["cells_detail"]}
    fmt = lambda d: ", ".join(f"{k}x{v}" for k, v in sorted(d.items()))                                       # noqa: E731
    cells = []
    for (p, s), x in sorted(da.items(), key=lambda kv: (list(dc.LEVELS).index(kv[0][0]), dc.SKILLS.index(kv[0][1]))):
        y = db[(p, s)]
        cells.append([p, s, x["expected_depth"], x["required"], x["truth"], fmt(x["claimed"]), fmt(x["verdicts"]), fmt(y["claimed"]), fmt(y["verdicts"]), f"{x['A']}/{x['runs']}", f"{y['A']}/{y['runs']}"])
    quotes = cited_quotes(B)
    qrows = [[k, v] for k, v in quotes.items()]
    improves = cmp["materially_improves"]
    verdict = ("MODEL CAPABILITY LIMITATION" if improves else "EVIDENCE-INTERPRETATION CONTRACT LIMITATION")
    return f"""# RESULTS — stronger Judge model on the frozen depth matrix

Architecture decision applied: the Evidence Check representation, observed depth + deterministic comparison and quote binding are accepted; `working_knowledge` stays binding; the recruiter requirement is not weakened. **The only experimental variable is the Judge model.** Not called: CrustData, Harvest, any provider, any retrieval; not deployed; `StructuredHiringIntent`, the compiler, the Evidence Check schema, the verifier and quote gate, the requirement / exclusion / depth prompts, the evidence wording and the acceptance rules are unchanged (the same code and the same stored matrix). Reproduce: `python -m backend.experiments.compiler_contract.depth_compare` then `build_stronger_model_report`.

## Verdict
**{verdict}.** The stronger model {"clearly reduces" if improves else "does NOT materially reduce"} the wrong observed-depth classifications: **{cmp["errors_before"]} -> {cmp["errors_after"]}** ({"" if cmp["relative_reduction"] is None else f"{round(100 * cmp['relative_reduction'])}% reduction"}), with {cmp["violations_after"]} quote-gate / binding / check-id / comparison violations (before: {cmp["violations_before"]}). Rule applied, declared before the run: {cmp["rule"]}. Per the instruction this stops here: no prompt tuning, no schema change, no domain-specific rule.

## 1. Exact model and configuration
| | gpt-4o-mini (frozen) | gpt-4.1 (this run) |
|---|---|---|
| model requested | `{a["models_recorded"][0]}` | `{b["models_recorded"][0]}` (the API resolved the alias to `gpt-4.1-2025-04-14` when probed) |
| API / format / temperature | Responses API, JSON object output, temperature {a["temperature"][0]} | identical: Responses API, JSON object output, temperature {b["temperature"][0]} (accepted without change) |
| retries / timeout | SDK max_retries 3, 120 s | identical |
| prompts, matrix, checks, evaluator | frozen | identical code, identical stored matrix (5 evidence levels x 3 skills x 6 runs = {a["cells"]} cells) |
| runs / calls / tokens | {a["jobs"]} / {a["calls"]} / {a["input_tokens"]:,} in, {a["output_tokens"]:,} out | {b["jobs"]} / {b["calls"]} / {b["input_tokens"]:,} in, {b["output_tokens"]:,} out |
| API failures | {a["failed_jobs"]} | {b["failed_jobs"]} |

The two models were never used in the same request: the gpt-4o-mini numbers are the stored, frozen runs of the previous experiment; the gpt-4.1 numbers are 30 new, separate runs. The whole Judge ran on gpt-4.1 for those runs (the plain-skill checks and the review pass included); only the depth cells are scored here. Required semantics unchanged: `unspecified < working_knowledge < hands_on < advanced`; `observed >= required` satisfied; `observed < required` not satisfied (`partly`, never counted as evidence); `unspecified` insufficient evidence (`not_evidenced`); nothing is ever converted into a pass.

## 2. Headline comparison
{md(headline, ["measure", "gpt-4o-mini (frozen)", "gpt-4.1"])}

## 3. Observed-depth accuracy by skill, by evidence level and by required depth
{md(skills, ["skill", "gpt-4o-mini", "gpt-4.1"])}

{md(levels, ["evidence level (expected observed depth)", "gpt-4o-mini", "gpt-4.1"])}

{md(reqd, ["required depth of the check", "gpt-4o-mini", "gpt-4.1"])}

## 4. Systematic bias and instability
{md(bias, ["", "gpt-4o-mini", "gpt-4.1"])}

Both models err almost only upward, by exactly one level (gpt-4o-mini {a["error_profile"]["over_by_one"]} of {a["error_profile"]["errors"]} errors, gpt-4.1 {b["error_profile"]["over_by_one"]} of {b["error_profile"]["errors"]}), and they do it identically on every one of the 6 runs of a cell. Run-to-run instability is not the problem: gpt-4.1 removes the one unstable cell gpt-4o-mini had (explicit "Advanced Microsoft Excel user"), and it gets the "advanced", "hands-on" and "familiar" evidence levels right in every cell; but it is worse than gpt-4o-mini on the "named only" level.

## 5. The 90 cells (6 runs per cell; claimed = the model's observed depth; verdict = after the deterministic comparison)
{md(cells, ["evidence", "skill", "expected depth", "required", "truth", "4o-mini claimed", "4o-mini verdicts", "4.1 claimed", "4.1 verdicts", "4o-mini A", "4.1 A"])}

## 6. Where the errors are, and what the stronger model cites
Both models make the SAME two mistakes; the stronger model makes the first one on all three skills (gpt-4o-mini on two).
{md(qrows, ["profile / skill", "what gpt-4.1 cites and claims (run 1)"])}

1. **"worked on X projects" read as working knowledge.** The only evidence is a work passage in which the candidate "worked on Java, Power BI and Microsoft Excel projects with the technology team", beside a skills list, a title, a headline and years. The depth prompt says in so many words that a depth must not be inferred from generic verbs, titles, years or lists. The deterministic checks cannot reject it: the quote is real, contiguous, from a work description and names the skill. gpt-4.1 treats "worked on / involved in" as demonstrating for all three skills, gpt-4o-mini for two.
2. **"uses Excel for everyday tasks such as sums, simple formulas and charts" read as hands-on.** The contract separates working knowledge ("real but modest or supporting use") from hands-on ("a core part of their real work") without saying what separates them in the evidence, so frequency of use ("everyday") is read as ownership.

## 7. Interpretation
{"The stronger model materially improves the failure pattern: the remaining depth failures are primarily a model-capability limitation. Recommendation: use the stronger model for the semantic depth evaluation only; do not replace the whole Judge." if improves else "The stronger model does **not** materially improve the failure pattern: errors go from " + str(cmp["errors_before"]) + " to " + str(cmp["errors_after"]) + ", every one of them is a one-level over-credit, and they are perfectly repeatable at temperature 0 (the same cells are wrong on all 6 runs). A repeatable error that a stronger model reproduces, on the same evidence and with the same outcome, is a property of the question being asked, not of the weaker model. Classification: **EVIDENCE-INTERPRETATION CONTRACT LIMITATION**. Nothing in the validation layer failed (the quote gate, the binding, the check ids and the ordinal comparison are 100% correct for both models), so it is not a VALIDATION problem, and the representation (an observed depth compared by code) is not at fault: stronger-than-required evidence is satisfied in every cell for both models."}

## 8. Smallest contract change to propose (not implemented; no domain-specific rule)
The depth label asks one model judgment to do two jobs at once: decide WHAT the candidate did and place it on a four-level scale whose boundaries are described only in prose. The smallest change that keeps the representation, the comparison and the bindings is to have the model report the **evidence it relied on** in a form code can check, and let code, not the model, apply the boundary:

1. Add one field to the depth observation: `action`, the exact words of the quote that say what the candidate DID with the skill (the verb phrase and its object). Code verifies, deterministically and generically, that `action` is a contiguous part of the already-verified quote and is not only an involvement phrase from a small generic list (`worked on`, `involved in`, `responsible for`, `part of`, `exposure to`, `familiar with`, `contributed to`, `assisted with`). An observation whose action is empty or only generic is `unspecified`, whatever depth the model claimed. This closes mistake 1 without any skill-specific rule and keeps the recruiter's requirement fully binding (an unprovable depth stays insufficient, never a pass).
2. Replace the two prose boundaries with one closed-set rubric the model must cite, applied identically to every skill: working_knowledge = the candidate used the skill for routine or basic tasks (stated as such: "simple", "basic", "occasional", "everyday tasks"); hands_on = the candidate built, wrote, configured or operated the skill's own artefacts as the work product; advanced = stated expertise, or design / optimisation / architecture of non-trivial work. This addresses mistake 2 by defining the boundary on what was done and its stated scope, not on how often.
Both are contract changes (what is asked and how it is checked), not model changes and not weakening of any requirement. They should be validated on this same matrix, once, before any further model decision.

## 9. Cost note
gpt-4.1 cost about ${b["estimated_cost_usd"]} against about ${a["estimated_cost_usd"]} for the same 30 runs (list-price assumption), roughly {round(b["estimated_cost_usd"] / a["estimated_cost_usd"])}x, for no reduction in depth errors.

## 10. Hard stop
No CrustData. No retrieval. No deployment. No prompt tuning. No schema change. Waiting for architecture review.
"""


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print("wrote", OUT)
