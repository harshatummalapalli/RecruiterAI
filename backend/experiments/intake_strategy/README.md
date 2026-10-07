# Intake-strategy experiment — Role 1 (offline, experiment-only)

**FROZEN. Status: ROLE 1 REPRESENTATION ACCEPTED FOR CROSS-ROLE VALIDATION.** This does not authorize compiler or retrieval work. The
conclusions, locked recruiter decisions, proven / not-proven lists, architecture boundary and risks are in the FROZEN section of
`DESIGN.md`.

Question: can the existing `StructuredHiringIntent` / intake representation express the recruiter's real sourcing
strategy for Role 1? Upstream of retrieval: no provider, Harvest, judge, ranking or production code is touched, and
`tests/test_experiment_intake_strategy.py` enforces that these files never import them.

## Run the baseline (current implementation, unchanged)

    OPENAI_API_KEY=... python -m backend.experiments.intake_strategy.run_baseline --runs 5

Writes per-run JSON and a summary to `output/experiments/intake_strategy/baseline/` (gitignored). The model and
reasoning effort are whatever `structured_intent_extractor` already uses; nothing is overridden.

## Files

- `inputs/role1_jd.txt` — the job description, verbatim.
- `inputs/role1_recruiter_brief.txt` — the recruiter's own description plus their clarifications, verbatim. Left out on
  purpose: the paragraph of engineering directives ("Do NOT flatten...", "The system should understand...") and the
  experiment instructions. Those direct the system rather than state the recruiter's requirements; including them
  would hand the model the answers. Edit this file before a run if you disagree.
- `gold_assertions.py` — deterministic evaluator holding the recruiter ground truth. Never put in a prompt.
  PASS / PARTIAL / FAIL per assertion, each failure classed as extraction / representation / validation /
  reconciliation / compiler / taxonomy. Representability is decided from the schema, not from prompt success.
- `provenance.py` — lexical stated-vs-inferred report (JD, BRIEF, APPROVED, INFERRED).
- `run_baseline.py` — the harness, the recording client and the five-run semantic-stability summary.

## Experimental arm (built after the baseline, from its failures)

- `DESIGN.md` — field-by-field justification of the extension and what was deliberately not added.
- `experimental_schema.py` — `ExperimentalHiringIntent(StructuredHiringIntent)`: additive, serialisable only, no compiler support.
- `prompt_v2.txt`, `experimental_extractor.py` — same model/effort (imported from production); only prompt and parse target differ.
- `validators.py` — code checks the model's provenance / reconciliation claims against the JD and brief text.
- `gold_experimental.py` — evaluator for the new shape (same assertion ids where the question is the same).
- `run_experimental.py` — five-run harness. Streams, because the larger reply exceeds the ~90 s non-streaming upstream cutoff.
- `compare_arms.py` — offline baseline-vs-experimental table. `results/` — compact stripped run snapshots.
- `RESULTS.md` — first experimental run, tables, caveats. `RESULTS_HARDENING.md` — hardening pass (v3), verdict, gate.
- `prompt_v3.txt` — hardening prompt (`--prompt v3`, default); `prompt_v2.txt` stays reproducible.

    OPENAI_API_KEY=... python -m backend.experiments.intake_strategy.run_experimental --runs 5
    python -m backend.experiments.intake_strategy.compare_arms

## Cross-role validation (Role 2)

`ROLE2_GROUND_TRUTH.md` (written and committed before any model run), `inputs/role2_*.txt`, `gold_role2.py`, `run_role2.py`, `compare_role2.py`,
`RESULTS_ROLE2.md` (verdict: NEW REPRESENTATION GAP FOUND), `results/role2/`. The frozen schema, `prompt_v3.txt` and validators were run unchanged;
Role 1 files are pinned by hash in `tests/test_experiment_role2.py`.

## After Role 2, before Role 3

`CHANGES_AFTER_ROLE2.md`: ordinal proficiency (`advanced`), typed `work_mode` (separate from `remote` and from geography), five generic validators
in `validators_cross_role.py` (title analogy, responsibility-only required, unsupported `current`, unsupported proficiency, unsupported work mode), and
`prompt_v4.txt` (new file; `prompt_v3.txt` and the frozen runners are unchanged). `replay_cross_role_validators.py` replays them read-only over the stored runs.
Role 1 and Role 2 inputs, results, evaluators and prompts are pinned by hash in `tests/test_experiment_cross_role_changes.py`. No model has run on the new design.

## Cross-role validation (Role 3, JD-only)

`inputs/role3_jd.txt` (verbatim; there is no brief and none was created), `ROLE3_GROUND_TRUTH.md` (committed before any model run), `gold_role3.py`,
`run_role3.py`, `compare_role3.py`, `RESULTS_ROLE3.md` (verdict: THREE-ROLE VALIDATION FOUND EXTRACTION/VALIDATION ISSUES ONLY, with the Power BI
depth-on-OR-group caveat stated there), `results/role3/`, `results/role3_analysis.json`. Run on frozen `prompt_v4.txt`, the experimental schema and
`validators_cross_role.py`, unchanged. The schema is not promoted; the owner decides.
