# HANDOFF — Role 1 intake-strategy experiment

Written for a fresh session that has none of the prior conversation. Read this fully before doing anything.
Branch: `claude/sleepy-clarke-5ueovf`. Role 2 is deliberately deferred: work ONLY with Role 1.

## Hard rules (from the owner; do not relax)
- Read-only-first mindset. NO production changes, NO change to production search/compiler/shadow behaviour.
- NO CrustData person/search calls, NO Harvest, NO candidate judging, NO retrieval, NO provider credits.
- NO new architecture: no second "Search Contract", no "Task C", no parallel intent architecture, no ontology project.
- Do NOT put the gold assertions into any LLM prompt. The model extracts meaning; deterministic code validates it.
- Do not "improve" anything before the baseline is captured. Do not assume the answer is "yes, intake is sufficient".
- Commit only experiment code/tests/docs. Keep it easy to delete or promote. No PR unless asked.

## Question
Can the existing `StructuredHiringIntent` / intake pipeline represent the real recruiter strategy for Role 1?
(role identity; brief overriding/narrowing the JD; conditional sourcing paths; path-specific geography and
requirements; hard negatives; proficiency differences; leadership semantics; domain-led vs capability-led;
cyber-incident-review != cybersecurity/SOC; explicit-vs-inferred provenance.)

## Ground truth (recruiter brief is authoritative where it narrows/clarifies/corrects the JD)
Inputs are verbatim in `inputs/role1_jd.txt` and `inputs/role1_recruiter_brief.txt`. Key points: two paths.
Path A domain-led (Cyber Incident Review / Data Breach Analysis; Legal Tech/LPO preferred; India-wide/remote; Power
Query NOT required). Path B capability-led/hybrid (Lead level, 6+ yrs, hands-on SQL+Python, Power Query working
knowledge, Hyderabad OR Pune, domain NOT required). Hard negative: cybersecurity/SOC/security operations, including
a strong SQL/Python analyst at a security firm. "Lead" = people OR technical leadership. Power Query is a lower bar than
hands-on SQL/Python. Do not turn "India" into a city, invent a radius, or turn legal-tech background into a
`current.company_name` filter. The JD's formal requirements/preferences (Relativity/Canopy, degree list, review/QA/
compliance/audit, security frameworks) must not be silently discarded: reconcile them with the brief.

## What is DONE (committed on the branch)
- `inputs/` verbatim JD + brief (engineering directives deliberately left out of the brief; see README).
- `run_baseline.py` baseline harness (current extractor + `compile_intent`, unchanged, N runs, records raw text/tokens).
- `gold_assertions.py` deterministic evaluator: 16 critical assertions PASS/PARTIAL/FAIL + compiler checks + JD
  retention; every failure classed EXTRACTION / REPRESENTATION / VALIDATION / RECONCILIATION / COMPILER / TAXONOMY.
- `provenance.py` lexical JD / BRIEF / APPROVED / INFERRED report.
- `tests/test_experiment_intake_strategy.py` (15 tests). Full suite at handoff: 789 passed, 4 skipped.

## What is NOT done
1. The baseline has NEVER been run: no OpenAI key was available. There are no results and no verdict yet.
2. The experimental schema extension (design only AFTER the baseline), the 5-run experimental arm, the five-run
   comparison, failure taxonomy table, architecture recommendation, final executive conclusion.

## Setup in a fresh session
- Python deps are not preinstalled: `python3 -m venv <dir> && <dir>/bin/pip install -r requirements.txt pytest`
  (use the session scratchpad, not the repo). Run tests with `<dir>/bin/python -m pytest -q -p no:cacheprovider`.
- OpenAI access: the owner added an "OpenAI API Key" Bearer credential (allowed site `api.openai.com`) in the
  environment settings. It is injected as an Authorization header by the proxy; it may NOT create an
  `OPENAI_API_KEY` env var. First run the free check:
  `curl -sS -m 30 -w "HTTP %{http_code}\n" https://api.openai.com/v1/models -H "Authorization: Bearer placeholder" | tail -3`
  - HTTP 200: the injected header works. If `OPENAI_API_KEY` is unset the harness refuses to run (exit 2); then make
    the SMALLEST change to `run_baseline.main` so it can use a placeholder key and rely on the injected header
    (a placeholder in the SDK only if the check shows the proxy overwrites Authorization). Report that change.
  - HTTP 401 "Missing bearer authentication": credential not applied. Ask the owner to open the credential's
    "See resolved curl example" and report what it shows (never ask for the key itself). Do not guess.
- The extractor uses `gpt-6.1-sol` at medium reasoning effort (constants in `structured_intent_extractor.py`): that
  is the sanctioned configuration. Log token usage; no price is known.

## Next steps, in order
1. Run the baseline unchanged: `python -m backend.experiments.intake_strategy.run_baseline --runs 5`. Capture all 5
   StructuredHiringIntent outputs, compiled plans, audit records, gold results, provenance, stability summary.
2. Report the baseline: what is understood, lost, flattened; which failures are extraction vs representation vs
   compiler (keep them separate). Show the owner BEFORE designing any extension.
3. Only then design the SMALLEST extension to the existing `StructuredHiringIntent`, each field justified by a
   baseline failure (candidates: sourcing_paths, path-specific location/requirements, hard negatives, domain slot,
   domain_led archetype, proficiency, leadership interpretation, provenance). Experimental, typed, backwards
   compatible, serialisable only; no compiler support unless needed to validate; cannot affect production.
4. Run 5 runs of the experimental representation with the same JD, brief, model and config. Compare on semantic
   stability (not identical JSON): structure, paths, must/preferred, negatives, proficiency, geography, domain
   distinction, provenance.
5. Deliver: A baseline output; B experimental output; C five-run comparison; D gold table PASS/PARTIAL/FAIL;
   E failure taxonomy; F architecture recommendation (what already works, what is missing, add / do NOT add, what
   belongs in compiler, in taxonomy, stays model-only, becomes deterministic code, smallest next experiment);
   G change summary; H test results (existing + new).
6. End with exactly one of: "INTAKE IS SUFFICIENT" or "INTAKE NEEDS REPRESENTATION CHANGES", with evidence.

## Acceptance gate for recommending live retrieval (all must hold)
Both paths represented; path-specific geography and requirements preserved; Power Query proficiency distinction kept;
cyber incident review distinguishable from cybersecurity/SOC; hard negatives preserved; brief overrides JD ambiguity
correctly; no invented hard constraints; provenance auditable; five-run semantic stability acceptable; all existing
tests green. If any critical item fails: STOP and recommend the smallest intake change. Never compensate for intake
failures by changing retrieval.

## Findings so far (hypotheses to confirm or refute; NOT results of this experiment)
- `prompts/structured_intent.txt` ends by telling the model to treat the recruiter brief "exactly like JD
  requirements, not as corrections": no precedence rule, so a brief that narrows/negates JD wording has no defined
  path (expected RECONCILIATION failure; JD says "security monitoring", "people leadership", brief says otherwise).
- Schema facts (verified by `gold_assertions.schema_supports()` in a test): no field for paths, proficiency, hard
  negatives, leadership type, domain, provenance, and no `domain_led` archetype. Exclusions can only name a current
  title or company.
- Compiler, observed offline on hand-built intents (no network): a country-only location compiles to
  `city IN ["India"]`; a multi-entry location compiles to city-only filters (country scope lost); the role family
  is a hard AND on `current.title`; `role_archetype` is never read by the compiler; required current skills are hard
  ANDs over sparse text fields; a domain "skill" with relationship `any` routes downstream, with `current` it would
  hard-filter (which would remove every Path B candidate).
- Open question for the owner: which "existing source-priority design" is meant. The only one found is the legacy
  `SearchBoundary` (recruiter's boundary overrides the JD for location). The structured path has none.
