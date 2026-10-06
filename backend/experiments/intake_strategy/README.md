# Intake-strategy experiment — Role 1 (offline, experiment-only)

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
- `RESULTS.md` — tables, caveats, verdict.

    OPENAI_API_KEY=... python -m backend.experiments.intake_strategy.run_experimental --runs 5
    python -m backend.experiments.intake_strategy.compare_arms
