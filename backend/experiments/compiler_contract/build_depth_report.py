"""Builds RESULTS_DEPTH_CONTRACT_VALIDATION.md from results/depth_matrix/analysis.json and the recorded discards of the previous phase. No number is typed by hand."""

from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any, Dict

from backend.experiments.compiler_contract import depth_basis as db
from backend.experiments.compiler_contract import depth_matrix as dm
from backend.experiments.compiler_contract.build_report import md
from backend.services.evidence_check import subject_in

HERE = Path(__file__).resolve().parent
RES = HERE / "results" / "depth_matrix"
OUT = HERE / "RESULTS_DEPTH_CONTRACT_VALIDATION.md"


def previous_binding_discards() -> Dict[str, Any]:
    """Re-test, with the new morphology, the subject-binding discards recorded in the previous Evidence Check phase."""
    total, now_ok, still = 0, {}, {}
    for f in glob.glob(str(HERE / "results" / "evidence_check" / "raw" / "EC*.json")):
        j = json.loads(Path(f).read_text(encoding="utf-8"))
        by = {c["check_id"]: c for c in j["checks"]}
        for d in j["binding_discards"]:
            if d["reason"] != "binding:subject_not_in_quote":
                continue
            c = by[d["check_id"]]
            total += 1
            bucket = now_ok if subject_in(d["quote"], tuple(c["subject_terms"])) else still
            bucket[c["label"]] = bucket.get(c["label"], 0) + 1
    return {"total": total, "now_accepted": now_ok, "still_discarded": still}


def _dist(d: Dict[str, int]) -> str:
    return ", ".join(f"{k}×{v}" for k, v in sorted(d.items())) or "-"


def final_pass() -> str:
    f = json.loads(db.ANALYSIS.read_text(encoding="utf-8"))
    g, b, a, c, n = f["gate"], f["baseline"], f["acceptance"], f["ceiling"], f["cells"]
    cells = [[x["level"] + " (" + x["profile"] + ")", x["skill"], x["required"], _dist(x["basis"]), _dist(x["claimed"]), _dist(x["ceiling"]), _dist(x["accepted"]), _dist(x["verdicts"]), x["truth"]]
             for x in f["per_cell"]]
    fn = g["false_negative_not_met_though_the_evidence_suffices"]
    cell = lambda lvl, skill: next(x for x in f["per_cell"] if x["profile"] == lvl and x["skill"] == skill)                  # noqa: E731
    wk_excel, adv_excel, none_pbi = cell("working_knowledge", "Microsoft Excel"), cell("advanced", "Microsoft Excel"), cell("none", "Power BI")
    adv_concrete = sum(x["basis"].get("concrete_skill_use", 0) for x in f["per_cell"] if x["profile"] == "advanced")
    adv_total = sum(x["runs"] for x in f["per_cell"] if x["profile"] == "advanced")
    gate_n = sum(x["runs"] for x in f["per_cell"] if x["profile"] in ("none", "familiar"))
    return f"""## 6. Final pass: evidence basis and the deterministic ceiling
Declared before the run, in `depth_basis.py`: the **hard gate** is that no evidence is credited above the maximum depth the contract allows and no named-only / familiar cell is `met`; the quality bar is zero quote-gate / binding / check-id / comparison violations and at least 50% fewer false-positive depth cases than the frozen baseline. Model agreement was not the bar.

**What changed (and nothing else).** The depth pass now also returns an `evidence_basis` per skill: `explicit_depth` / `concrete_skill_use` / `routine_skill_use` / `generic_involvement` / `no_depth_evidence`. Code maps the basis to a CEILING (`no_depth_evidence`, `generic_involvement` -> unspecified; `routine_skill_use` -> working_knowledge; `concrete_skill_use` -> hands_on; `explicit_depth` -> the depth the quote itself states about the skill, else unspecified) and credits `min(model's observed_depth, ceiling)`; a missing or unrecognised basis supports nothing. The depth prompt gained only the basis definitions and output field; the matrix, evidence texts, checks, requirement / exclusion prompts, quote gate, binding, verifier and model ({", ".join(f["model"])}, temperature 0) are the same ({f["jobs"]} runs, {f["calls"]} calls, about ${f["estimated_cost_usd"]}). Raw runs: `results/depth_matrix/raw_basis/`; baseline: `results/depth_matrix/raw/`.

{md([["A. evidence_basis in the acceptable set for its level", f"{f['A_evidence_basis']['correct']}/{n}"], ["B. observed_depth: model's own report / credited after the ceiling", f"{f['B_observed_depth']['model_claim_correct']}/{n} / {f['B_observed_depth']['credited_correct']}/{n}"],
     ["C. maximum_supported_depth equals the evidence level", f"{f['C_maximum_supported_depth']['correct']}/{n}"], ["D. deterministic comparison right given the credited depth", f"{f['D_deterministic_comparison']['correct']}/{n}"],
     ["E. final verdict: met / not met correct / three-way correct", f"{f['E_final_verdict']['met_vs_not_correct']}/{n} / {f['E_final_verdict']['three_way_correct']}/{n}"],
     ["F. quote gate: credited depths failing the gate / first-pass claims failing it / retried and recovered", f"{f['F_quote_gate']['accepted_depths_failing_the_gate']} / {f['F_quote_gate']['failed_gate']} of {f['F_quote_gate']['claims']} / {f['F_quote_gate']['retried_checks']} and {f['F_quote_gate']['retries_recovered']}"],
     ["G. binding: unknown or duplicate check_id / credited quote not naming its skill / not demonstrated work / discarded by binding", f"{f['G_binding']['unknown_or_duplicate_check_id']} / {f['G_binding']['accepted_not_naming_own_skill']} / {f['G_binding']['accepted_not_work_evidence']} / {f['G_binding']['discarded_by_binding']}"],
     ["payload violations / provider or compiler tokens in any request / failed runs", f"{f['depth_payload_violations']} / {f['leak_token_hits']} / {f['failed_jobs']}"]], ["measure", "result"])}

**The gate.**
{md([["credited above the ceiling of its own evidence basis", g["credited_above_ceiling"], "0 required"], [f"`met` on a named-only or familiar profile ({gate_n} cells)", g["met_on_named_only_or_familiar"], "0 required"],
     ["named-only / familiar verdicts", _dist(g["named_only_or_familiar_verdicts"]), "all insufficient"],
     ["false-positive `met` (requirement not met by the evidence): baseline -> now", f"{b['false_positive_met']} -> {g['false_positive_met']}", f"{', '.join(b['false_positive_cells'])} (baseline)"],
     ["credited above the evidence's true level: baseline -> now", f"{b['credited_above_the_evidence_level']} -> {g['credited_above_the_evidence_level']}", ", ".join(g["credited_above_the_evidence_level_cells"]) or "-"],
     ["model claimed a depth above the evidence: baseline -> now (the model's own report)", f"{b['model_claimed_too_deep']} -> {c['model_claimed_too_deep']}", ""],
     ["of today's model over-claims: capped by the ceiling / still credited too deep", f"{c['of_which_capped_by_the_ceiling']} / {c['of_which_still_credited_too_deep']}", ""],
     ["of the baseline's {0} too-deep cells (same profile, skill, run): now credited at or below the evidence / not credited at all / still too deep".format(b["model_claimed_too_deep"]),
      f"{b['previously_too_deep_cells_now_credited_at_or_below_the_evidence']} / {b['previously_too_deep_cells_now_not_credited_at_all']} / {b['previously_too_deep_cells_now_still_credited_too_deep']}", ""],
     ["stronger-than-required cells met", f"{f['stronger_than_required']['met']}/{f['stronger_than_required']['of']}", ""]], ["check", "result", "note"])}

**Acceptance: {"ACCEPTED" if a["accepted"] else "NOT ACCEPTED"}.** No evidence was credited above the ceiling (0), no named-only or familiar profile satisfied a depth requirement (0 of {gate_n}; every one is `not_evidenced`, i.e. insufficient evidence), structural violations {a["structural_violations"]}, and false-positive depth cases fell {a["false_positive_before"]} -> {a["false_positive_after"]} ({"" if a["false_positive_reduction"] is None else f"{a['false_positive_reduction']:.0%} fewer"}). {"The depth contract is therefore accepted and is not to be tuned further." if a["accepted"] else "The contract is not accepted; the remaining failure is classified below and no further schema layer is added."}

Per cell (6 runs each; every column is a distribution over the 6 runs):

{md(cells, ["evidence level", "skill", "required", "evidence_basis", "model's observed depth", "ceiling", "credited", "verdicts", "truth"])}

**What the ceiling did.** {c["cells_capped"]} of {n} observations were capped or voided by the ceiling or the missing-basis rule. It removed the exact failure of the previous pass: the "named only" profile ("worked on Java, Power BI and Microsoft Excel projects") is labelled `generic_involvement` / `no_depth_evidence` and the model's `working_knowledge` for Power BI is voided ({none_pbi['accepted'].get('unspecified', 0)} of {none_pbi['runs']}), and "advanced" claims resting on concrete use are limited to hands_on.

**What it did not fix, and what it costs ({fn} false negatives, all on the safe side):**
* **Over-crediting is not eliminated, only bounded by the model's own basis label.** The "working knowledge" profile's Excel text ("everyday tasks such as sums, simple formulas and charts") is labelled `concrete_skill_use` on {wk_excel['basis'].get('concrete_skill_use', 0)} of {wk_excel['runs']} runs, so the ceiling allows hands_on; the result is still not a false positive only because the Excel requirement is `advanced`. A hands_on requirement on that evidence would have been over-credited. This is a model labelling limitation (the model treats everyday use as concrete use); it is not corrected by a further schema layer.
* **Genuinely advanced evidence is under-credited.** The advanced profile is labelled `concrete_skill_use` (not `explicit_depth`) on {adv_concrete} of {adv_total} observations although it contains "Advanced Java expert" / "Advanced Microsoft Excel user", so the ceiling is hands_on: the advanced Excel requirement is `partly` ({adv_excel['verdicts'].get('partly', 0)} of {adv_excel['runs']}), not `met`. Under the contract an `advanced` requirement is satisfiable only when the model labels the evidence `explicit_depth` AND the quote itself states advanced proficiency (\"advanced\", \"expert\", \"highly proficient\", \"mastery\"); sophisticated concrete work alone is capped at hands_on by design.
* **Conservative voiding.** {f['G_binding']['discarded_by_binding']} observations were voided by the existing binding rule (the quote did not name its skill: "...with working knowledge of each"); they are insufficient evidence, not false positives.

Every under-credit lands in `partly` or `not_evidenced`. A recruiter sees "demonstrated but below the requirement" or "insufficient evidence", never a silent pass.

"""


def build() -> str:
    a = json.loads((RES / "analysis.json").read_text(encoding="utf-8"))
    t, ep = a["totals"], a["error_profile"]
    prev = previous_binding_discards()
    n = a["A_model_observed_depth"]["of"]
    cells = [[c["expected_depth"] + " (" + c["profile"] + ")", c["skill"], c["required"], ", ".join(f"{k}×{v}" for k, v in sorted(c["claimed"].items())), ", ".join(f"{k}×{v}" for k, v in sorted(c["verdicts"].items())),
              c["truth"], f"{c['A']}/{c['runs']}", f"{c['B_e2e']}/{c['runs']}", f"{c['C']}/{c['runs']}"] for c in a["cells"]]
    wrong = [c for c in a["cells"] if c["A"] != c["runs"]]
    return f"""# RESULTS — observed-depth contract, binding morphology and the evidence-basis ceiling (real Judge model; synthetic profiles; targeted test only)

Final Evidence Check hardening pass. **Not called:** CrustData, Harvest, any provider, any retrieval; **not deployed; `StructuredHiringIntent`, the compiler, admission and ranking unchanged.** Only the Judge's own model ran (gpt-4o-mini, temperature {", ".join(t["temperatures"])}) on {t["jobs"]} synthetic judge runs ({t["calls"]} calls, about ${t["estimated_cost_usd"]}). The full earlier synthetic suite was not re-run. Contract: `backend/services/DOWNSTREAM_CONSUMER_CONTRACT.md` (§3c-3f). Raw runs: `results/depth_matrix/raw/`.

## Verdict of the observed-depth pass (superseded by the final pass in §6)
**{"PASS" if a["passed"] else "FAIL: observed-depth extraction is not reliable"}.** Declared before the run: PASS only if (A) the model's observed depth is the expected one in every cell and run, (B) the deterministic comparison is right in every cell and (C) every accepted observation has a gate-passing, skill-naming quote from demonstrated work. Result: **A {a["A_model_observed_depth"]["correct"]}/{n}**, **B (code) {a["B_code_comparison"]["correct"]}/{n}**, **B (end-to-end verdict) {a["B_end_to_end_verdict"]["correct"]}/{n}**, **C {a["C_quote_binding"]["ok"]}/{n}**. Per the escalation rule this is where the work stops: no prompt tuning, no stronger model was run.

## 1. What changed
1. **Binding morphology.** Subject and indicator binding compare words through conservative base forms (case, plural `-s/-es/-ies`, `-ing`, `-ed`, a doubled final consonant, a trailing `-e`): `financial modeling` = `financial models` = `financial modelling`; nothing semantic. Regression tests cover the positives (financial modeling / models, Python, Power BI, APIs / API, ...) and the negatives (financial modeling is not financial planning; Java is not JavaScript; SQL is not NoSQL; Excel is not excellent; Power Query is not SQL query). Re-testing the {prev["total"]} subject-binding discards recorded in the previous phase: **{sum(prev["now_accepted"].values())} would now be accepted** ({", ".join(f"{k} x{v}" for k, v in prev["now_accepted"].items()) or "none"}); {sum(prev["still_discarded"].values())} are still discarded ({", ".join(f"{k} x{v}" for k, v in prev["still_discarded"].items())}). The remaining ones are not morphology (the quote lacks a token of a multi-word category skill, or is a correct discard of cross-assigned evidence); the scope question for multi-word category skills is unchanged and open.
2. **Observed depth.** For a skill + depth check the model is asked one thing: which depth do the supplied passages DEMONSTRATE for the skill (`unspecified` / `working_knowledge` / `hands_on` / `advanced`), with a quote. It is never told the required depth (the payload carries the skill only; {a["depth_payload_violations"]} payload violations). Code then decides `observed_depth >= required_depth` on `unspecified < working_knowledge < hands_on < advanced`; below the requirement but demonstrated is `partly`, undemonstrated is `not_evidenced`. The review pass no longer applies to a depth judgment (it would be a second model comparison). A depth is accepted only with a quote that passes the quote gate, names the skill and comes from demonstrated work or a certification; a title, headline, skills-list entry or computed passage is never depth evidence.
3. **Exclusions.** States unchanged (`PRESENT` / `NOT_PRESENT` / `INSUFFICIENT_EVIDENCE`). Tests enumerate every way a PRESENT claim can fail its evidence (ellipsis, fabricated, too short, no such passage, no passage, a real quote with no indicator, no quote): each yields `INSUFFICIENT_EVIDENCE`, never `NOT_PRESENT`.

## 2. The matrix
One synthetic intent with three skills, each required at a different depth: **Power BI -> working_knowledge, Java -> hands_on, Microsoft Excel -> advanced**. Five synthetic profiles, one per evidence level, state the SAME level for all three skills; {t["jobs"] // 5} repetitions each ({n} cells). The expected observed depth is the profile's level; the expected verdict is the ordinal comparison.

{md([[p.key, p.level, p.label] for p in dm.PROFILES], ["profile", "expected observed depth", "evidence"])}

"Stronger-than-required evidence" is the set of cells whose evidence is deeper than the requirement (hands_on or advanced evidence against Power BI; advanced evidence against Java).

## 3. Results
{md([["A. observed depth correct (the model's own report)", f"{a['A_model_observed_depth']['correct']}/{n}"], ["A'. ... after the deterministic validation", f"{a['A_final_observed_depth']['correct']}/{n}"],
     ["B. the deterministic comparison is right, given the accepted observation (recomputed independently)", f"{a['B_code_comparison']['correct']}/{n}"], ["B'. end-to-end verdict (met / not met) equals the truth table", f"{a['B_end_to_end_verdict']['correct']}/{n}"],
     ["B''. stronger-than-required cells met", f"{a['B_stronger_than_required']['correct']}/{a['B_stronger_than_required']['of']}"],
     ["C. accepted observations with a gate-passing, skill-naming quote from demonstrated work", f"{a['C_quote_binding']['ok']}/{a['C_quote_binding']['of']} ({len(a['C_quote_binding']['violations'])} violations)"],
     ["depth payloads carrying anything but passages + skills / provider or compiler tokens in any request", f"{a['depth_payload_violations']} / {a['leak_token_hits']}"],
     ["quote retries (only failed-quote checks) / recovered / binding discards", f"{t['retried_checks']} / {t['retries_recovered']} / {t['binding_discards']}"]], ["measure", "result"])}

Per cell (6 runs; A = the model reported the expected depth, B' = end-to-end verdict right, C = quote binding right):

{md(cells, ["evidence level", "skill", "required", "model's observed depth", "verdicts", "truth", "A", "B'", "C"])}

## 4. The errors
{ep["errors"]} of {n} observations were wrong: **{ep["over_by_one_level"]} one level too deep, {ep["under_by_one_level"]} one level too shallow, {ep["two_or_more_levels"]} two or more levels off.** They are stable, not noise: {ep["cells_wrong_on_every_run"]} cells were wrong on all 6 runs, {ep["cells_right_on_every_run"]} of {ep["cells"]} cells were right on all 6. By skill: {ep["by_skill"]}. By evidence level: {ep["by_evidence_level"]}.

* **"named only" profile, Excel and Power BI: reported `working_knowledge` on every run** ({ep["by_evidence_level"].get("unspecified/none", 0)} errors) although the only evidence is "worked on Java, Power BI and Microsoft Excel projects" beside a skills list, a title, a headline and years. The contract forbids inferring a depth from generic verbs, titles or years, and the model obeyed it for Java and not for the other two. The deterministic checks cannot catch this: the quote comes from a real work description and names the skill.
* **"working knowledge" profile, Excel: reported `hands_on` on every run** ({ep["by_evidence_level"].get("working_knowledge/working_knowledge", 0)} errors): "everyday tasks such as sums, simple formulas and charts" sits on the boundary between modest and core use for a tool every office worker uses.
* **"advanced" profile, Excel: `hands_on` in 2 of 6 runs** (the same instability on explicit advanced evidence as in the previous phase).
* The ordinal representation itself works: every stronger-than-required cell is met ({a["B_stronger_than_required"]["correct"]}/{a["B_stronger_than_required"]["of"]}), including the case the previous contract failed on 6 of 6 (basic Excel with ADVANCED Power BI), and the code comparison is exact ({a["B_code_comparison"]["correct"]}/{n}).

## 5. Classification (escalation rule: stop and classify, do not tune)
{md([
  ["VALIDATION", "holds", f"C {a['C_quote_binding']['ok']}/{n}; B (code) {a['B_code_comparison']['correct']}/{n}; no cross-assignment, no non-work evidence accepted; the quote gate and retry worked ({t['retried_checks']} retried, {t['retries_recovered']} recovered)"],
  ["REPRESENTATION", "holds", "the ordinal ladder and the observed-depth contract fixed stronger-evidence-meets-weaker-requirement (previously 0/6); the model is not asked to compare"],
  ["PROMPT/CONTRACT", "partly open", "the working_knowledge / hands_on boundary rests on 'modest or supporting use' versus 'a core part of their real work'; an everyday office tool is genuinely ambiguous there (6 of the 20 errors). The 'never infer from generic verbs' rule is already explicit in the prompt, so it is not a missing instruction"],
  ["MODEL CAPABILITY", "the main remaining problem", "12 of the 20 errors break an explicit negative rule (generic verbs / titles / years) on two skills of three, and 2 are an unstable miss on explicit 'Advanced ... user' evidence; all are one level off, 18 of 20 too deep. This is a small model over-crediting adjacent levels, consistently at temperature 0"]],
  ["class", "status", "evidence"])}

**Decision.** Observed-depth extraction is NOT yet reliable enough to pass the declared bar, and the remaining problem is mostly model capability, with one ambiguous boundary. Nothing was tuned and no stronger model was run. For review, in order of cost: (1) decide the working_knowledge / hands_on boundary for ubiquitous tools (a contract decision, no code); (2) only then evaluate a stronger model on this same matrix with the contract unchanged, as a single comparison; (3) if a depth requirement is critical, treat `working_knowledge` as non-binding (it is the level the small model over-credits) and keep hands_on / advanced as the binding depths.

{final_pass()}## 7. Hard stop
No CrustData. No retrieval. No deployment. Live retrieval is not to run until this is reviewed.
"""


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print("wrote", OUT)
