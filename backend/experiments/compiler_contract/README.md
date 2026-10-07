# compiler_contract — offline compiler-contract experiment (EXPERIMENT ONLY)

Question: can the CURRENT deterministic compiler (`backend/services/search_compiler.py`, unchanged) translate the extended hiring intent without silently
dropping, strengthening or weakening meaning? Measurement only: no model, no CrustData, no Harvest, no retrieval, no production/provider/compiler/schema change.

- `CONTRACT_EXPECTATIONS.md` — written and committed BEFORE any compile output was examined: method, expected fate per concept, ten predictions, checks, gap-type rules.
- `RESULTS_COMPILER_CONTRACT.md` — the report (generated tables from `results/contract_analysis.json` + `report_template.md`).
- `results/baseline/` + `baseline_manifest.json` — compiled plans, audit records, downstream checklists, read sets for the 15 frozen intents, with hashes of the compiler-side files and stored runs.
- Code: `loader.py` (frozen intents, read-only), `signature.py` (output signatures, diff, read-set tracer), `atoms.py` (atom enumeration + ablation), `fate.py` (destination -> fate),
  `paths.py` (per-path compile vs whole plan), `probes.py` (strength / relationship / location / level probes), `checks.py` (Role 1/2/3 critical checks), `contract.py` (expected fates, gap types),
  `run_contract.py` (`baseline`, `analyse`), `build_report.py`.
- Tests: `tests/test_experiment_compiler_contract.py` (pins the unchanged compiler-side files and each baseline fact).

Reproduce: `python -m backend.experiments.compiler_contract.run_contract baseline && python -m backend.experiments.compiler_contract.run_contract analyse && python -m backend.experiments.compiler_contract.build_report`

Status: baseline measured, nothing fixed, waiting for architecture review.
