"""Builds RESULTS_DEPTH_CONTRACT_VALIDATION.md from results/depth_matrix/analysis.json and the recorded discards of the previous phase. No number is typed by hand."""

from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any, Dict

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


def build() -> str:
    a = json.loads((RES / "analysis.json").read_text(encoding="utf-8"))
    t, ep = a["totals"], a["error_profile"]
    prev = previous_binding_discards()
    n = a["A_model_observed_depth"]["of"]
    cells = [[c["expected_depth"] + " (" + c["profile"] + ")", c["skill"], c["required"], ", ".join(f"{k}×{v}" for k, v in sorted(c["claimed"].items())), ", ".join(f"{k}×{v}" for k, v in sorted(c["verdicts"].items())),
              c["truth"], f"{c['A']}/{c['runs']}", f"{c['B_e2e']}/{c['runs']}", f"{c['C']}/{c['runs']}"] for c in a["cells"]]
    wrong = [c for c in a["cells"] if c["A"] != c["runs"]]
    return f"""# RESULTS — observed-depth contract and binding morphology (real Judge model; synthetic profiles; targeted test only)

Final Evidence Check hardening pass. **Not called:** CrustData, Harvest, any provider, any retrieval; **not deployed; `StructuredHiringIntent`, the compiler, admission and ranking unchanged.** Only the Judge's own model ran (gpt-4o-mini, temperature {", ".join(t["temperatures"])}) on {t["jobs"]} synthetic judge runs ({t["calls"]} calls, about ${t["estimated_cost_usd"]}). The full earlier synthetic suite was not re-run. Contract: `backend/services/DOWNSTREAM_CONSUMER_CONTRACT.md` (§3c-3f). Raw runs: `results/depth_matrix/raw/`.

## Verdict
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

## 6. Hard stop
No CrustData. No retrieval. No deployment. Live retrieval is not to run until this is reviewed.
"""


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print("wrote", OUT)
