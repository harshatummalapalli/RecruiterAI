# EXP-002: does a selected slice of the Knowledge Library improve the intake decision?

Code: `backend/experiments/intake_knowledge/` (`scenarios.py`, `run.py`), slice selector `backend/experiments/intake_knowledge/knowledge_slice.py`.
Raw artifacts: `output/experiments/intake_knowledge/` (git-ignored).

## Hypothesis

Giving Task B (the ASK/TELL/IGNORE decision) a small, deterministically selected slice of the Knowledge Library as
**advisory** context makes the intake notice real issues it otherwise misses (title/work mismatch, conflicting or
impossible requirements, over-constrained lists) **without** asking more unnecessary questions.

If it does not, the library is not wired into intake. Its existing presence is not a reason to use it.

## Design

- 9 fixed, realistic scenarios (`scenarios.py`). Each records, **before any run**, what a good intake should do:
  a regex for a warranted ASK (none means every ASK is a false positive) and a regex for the finding worth surfacing.
- Task A runs **once per scenario** (temperature 0, real model) and is pinned. Both conditions use that same output,
  so the only difference is the knowledge excerpt in Task B.
- Conditions: **without** (production Task B) vs **with** (same prompt plus the slice, ~1.1k tokens).
- 3 runs per scenario per condition. Everything downstream of Task B is the production code unchanged: deterministic
  backstops and the recruiter's Search Boundary (fixed Toronto/hybrid, so location is never a legitimate question).
- Model: gpt-4o-mini, temperature 0 (production settings).

## Metrics

| Metric | Definition |
|---|---|
| ASK count | ASK issues per run, after backstops and boundary |
| False-positive ASK | An ASK matching no warranted-ASK pattern for the scenario |
| Finding hit | The expected finding surfaced anywhere (TELL, warning, question, consequence). A scenario counts as a hit when it is found in at least 2 of 3 runs |
| Materiality | An ASK whose two consequences are both filled in, different from each other, and name an input the search actually uses |
| Stability | Same ASK count and same hit result across the 3 runs of a scenario |
| Brief quality | Read directly: do the requirement tiers and the search sentence improve, on the scenarios where that is the point? |

## Decision rule (fixed before the first run)

Wire the knowledge slice into Task B **only if all of these hold**:

1. Finding hits with knowledge are at least **2 higher** than without, across the scenarios that expect a finding.
2. False-positive ASKs with knowledge are **no higher** than without (summed over all runs).
3. On the scenarios where zero questions is correct (S1, S2, S7, S9), the ASK count with knowledge is **no higher**.
4. Stability with knowledge is **no worse** than without.

Otherwise: do not wire it. Report why.

## Results

54 runs (9 scenarios x 2 conditions x 3 runs), about $0.10, 204 s. Raw runs: `output/experiments/intake_knowledge/runs.json`.

| Scenario | ASK count without / with (3 runs each) | False-positive ASKs | Expected finding (Task B output) | Expected finding (Task B + Task A reading) |
|---|---|---|---|---|
| S1 clear role | 0,0,0 / 0,0,0 | 0 / 0 | n/a | n/a |
| S2 title says software engineer, work is platform | 0,0,0 / 0,0,0 | 0 / 0 | no / no | yes / yes (identity read as DevOps Engineer) |
| S3 conflicting experience ranges | 1,1,1 / 1,1,1 | 0 / 0 | yes / yes | yes / yes |
| S4 over-constrained required list | 0,0,0 / 0,0,0 | 0 / 0 | no / no | no / no (15 items all "hard") |
| S5 impossible technology tenure | 0,0,0 / 0,0,0 | 0 / 0 | no / no | yes / yes (only as "extensive experience", not challenged) |
| S6 staff title, junior experience | 0,0,0 / 0,0,0 | 0 / 0 | no / no | no / no (Task A dropped "Staff") |
| S7 AI engineer, backend-dominant | 0,0,0 / 0,0,0 | 0 / 0 | no / no | yes / yes |
| S8 vague notes only | 0,0,0 / 1,0,0 | 0 / 0 | no / no | yes / yes |
| S9 data scientist title, ETL work | 0,0,0 / 0,0,0 | 0 / 0 | no / no | yes / yes |

Decision rule, applied as written:

1. Finding hits at least 2 higher with knowledge: **failed**. Identical in both conditions (1 vs 1 on Task B output, 6 vs 6 with Task A's reading).
2. False-positive ASKs no higher: passed (0 vs 0).
3. Zero-question scenarios no higher: passed (0 vs 0).
4. Stability no worse: **failed**. One scenario (S8) produced a question in 1 of 3 runs with knowledge and never without.

**Verdict: the knowledge slice is NOT wired into Task B.** Rule 1 is the point of the experiment and it failed outright.

## What the run does show

- The slice was inert. Task B's own rules (closed world, concrete-consequence test) decide what can be asked, and a
  reference excerpt did not change what it considered. Whatever helps must be a change to what Task B is asked to
  do, not extra reading material.
- The real gaps are three scenarios that neither condition handles: **S4** (fifteen requirements all marked "hard",
  no challenge), **S5** (12+ years of Kubernetes accepted at face value) and **S6** (a Staff title over 1-2 years of
  experience: Task A even dropped "Staff" from the identity, and nothing was raised). These are feasibility and
  consistency problems, not knowledge problems.
- Task A's role reading already surfaces title-versus-work mismatches (S2, S7, S9), so those need no new mechanism.
- The pinned understanding was stable across all 54 runs (temperature 0), which supports pinning Task A.

## Follow-up

Release 4 step 6 (feasibility challenges) tests a narrow instruction on S4, S5 and S6 **without** the library, under
the same kind of pre-registered rule. See EXP-002b in this file once run.

---

# EXP-002b: does a narrow feasibility instruction (no library) catch what the intake misses?

Code: `backend/experiments/intake_knowledge/run_feasibility.py`. Same 9 scenarios, same pinned Task A outputs as EXP-002.

## Hypothesis

Adding to Task B (a) a narrow FEASIBILITY CHECK (three named situations, at most two issues, must reference exact
requirement texts, defaults to a plain factual TELL) and (b) a per-requirement evidence quote, catches S4
(over-constrained), S5 (impossible tenure) and S6 (staff title over junior years) **without** raising anything on
the sensible roles, and without destabilising the rest of the decision.

## Conditions

- **baseline**: the production Task B prompt exactly as it was before Release 4 (`baseline_task_b.txt`).
- **revised**: the Release 4 Task B prompt (feasibility section and requirement evidence added), followed by the
  production code validation (`verify_requirement_evidence`, `validate_feasibility_issues`).

3 runs per scenario per condition, temperature 0, gpt-4o-mini. No knowledge slice in either.

## Decision rule (fixed before the first run)

Adopt the revised prompt **only if all hold**:

1. **Catch:** a feasibility TELL or ASK that references the right requirements appears (in at least 2 of 3 runs) on **at least 2 of S4, S5, S6**.
2. **No false alarms:** zero feasibility issues survive validation on the sensible roles **S1, S2, S3, S7, S9**, in all runs.
3. **No regression:** ASK counts and false-positive ASKs on every scenario are no worse than baseline; S3 still asks exactly one question.
4. **Stability:** the number of scenarios whose ASK count differs across the 3 runs is no higher than baseline.
5. **Evidence is honest:** every quote kept as "stated in JD" appears in the raw input (guaranteed by code; reported as the share of requirements that end up verified vs claimed).

Otherwise the feasibility prompt is not adopted, and challenges stay out of Release 4.

## Results

54 runs, about $0.08. Raw: `output/experiments/intake_knowledge/runs_feasibility.json`.

| Scenario | Feasibility issues raised (baseline / revised, per run) | Requirements stated as verifiable quotes (revised, run 1: verified / total) |
|---|---|---|
| S1 clear role | 0 / 0 | 5 of 6 |
| S2 title vs platform work | 0 / 0 | 0 of 8 |
| S3 conflicting ranges | 0 / 0 | 0 of 4 |
| **S4 over-constrained** | 0 / **0** | 0 of 15 |
| **S5 impossible tenure** | 0 / **0** | 0 of 4 |
| **S6 staff title, junior years** | 0 / **0** | 0 of 3 |
| S7 AI/backend split | 0 / 0 | 5 of 5 |
| S8 vague notes | 0 / 0 | 0 of 4 |
| S9 data scientist over ETL | 0 / 0 | 2 of 6 |

Decision rule as written:

1. **Catch on at least 2 of S4, S5, S6: failed (0 of 3).** The model raised no feasibility issue in any of the 27 revised runs, including the three scenarios built to trigger one.
2. No false alarms on the sensible roles: passed (0), but trivially, since nothing was ever raised.
3. No regression in ASKs: passed. 4. Stability: passed (no scenario varied).
5. Evidence honesty: the code check works (a quote is kept only if it appears in the input) but the model's quotes were mostly paraphrases: 12 of 56 requirements verified on the scenarios where any were claimed. Model-supplied evidence is not a usable basis for "Stated in JD".

**Verdict: the revised Task B prompt is NOT adopted and was reverted.** gpt-4o-mini treated the instruction as
optional next to Task B's existing closed-world and concrete-consequence rules, and its evidence quotes are not
reliable.

# EXP-002c: the same goal, as a dedicated single-purpose reviewer call

The failure above is about one prompt carrying too many jobs. A separate call whose only job is the three
feasibility situations fits the architecture (the model reasons; code validates) and cannot disturb Task B.

## Conditions and rule (fixed before the first run)

- Task B runs unchanged (production prompt). Then a **reviewer** call sees only: the posted title, seniority, the
  experience range and the three requirement lists, and may return at most two findings for the three situations,
  each with exact `references`. Findings are TELLs only (nothing here blocks a search). Code drops any finding whose
  references are not requirements (or the posted title), or that references too few items for its situation.
- 3 runs per scenario, temperature 0, gpt-4o-mini.
- Adopt only if: (1) at least 2 of S4, S5, S6 are caught in at least 2 of 3 runs with correct references;
  (2) **zero** surviving findings on S1, S2, S3, S7, S8, S9 in every run; (3) the same result in all 3 runs for at
  least 8 of 9 scenarios. Otherwise feasibility challenges are left out of Release 4.

## Results

27 reviewer runs after 9 unchanged Task B runs. Raw: `output/experiments/intake_knowledge/runs_feasibility_reviewer.json`.

| Scenario | Findings per run (3 runs) | Assessment |
|---|---|---|
| S1, S2, S3, S7, S8, S9 (sensible roles) | 0, 0, 0 | Correct. No false alarms. |
| **S4 over-constrained (15 core)** | 1, 1, 1: over-constrained, cites all 15 requirements | **Correct and stable.** |
| **S5 impossible tenure** | 1, 1, 1: labelled "over-constrained", cites Kubernetes, large language models, Terraform, AWS | **Wrong finding.** Calling those four "unrelated technology families" is false, and the real problem (12+ years of Kubernetes) was never seen: Task B had already reduced the requirements to bare terms ("Kubernetes"), so the years were gone before the reviewer looked. |
| **S6 staff title, junior years** | 0, 0, 0 | **Missed.** |

Decision rule as written:

1. Catch at least 2 of S4, S5, S6 with correct references: **failed** (1 of 3; S5's finding is wrong, not a catch).
2. Zero findings on the sensible roles: passed (0 of 162 role-runs).
3. Same result in all 3 runs for at least 8 of 9 scenarios: passed (9 of 9).

**Verdict: feasibility challenges are NOT part of Release 4.** The only reliable detection is over-constrained lists
(S4), and the same situation produced a false, confident-sounding statement on S5. A note that is sometimes
factually wrong is worse than no note, and the brief promises to be factual.

## What this teaches, for later

- The impossible-tenure case fails upstream of any reviewer: requirement texts lose their years when Task B
  compresses them. A future attempt should review the raw input's stated tenures, not the compressed list.
- A narrow "over-constrained only" note showed 3 of 3 on S4 but also one false alarm (S5), so it needs a larger
  scenario set before it can be trusted. It was not adopted after the fact: the rule was fixed in advance.
- The experiment code (`feasibility_reviewer.py`, `feasibility_review_prompt.txt`, `run_feasibility*.py`) is kept for
  the record. `run_feasibility.py` (EXP-002b) targets a Task B prompt and model fields that were removed from the
  product, so it documents the result but no longer runs against the current code.
