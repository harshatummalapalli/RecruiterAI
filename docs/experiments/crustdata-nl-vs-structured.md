# EXP-001: CrustData natural-language vs structured retrieval

Experiment id `crustdata-nl-vs-structured-20260924`, run 2026-09-24. Raw data (candidate items, Harvest reads,
judgments) is in `output/experiments/crustdata_nl_vs_structured/crustdata-nl-vs-structured-20260924/` and is
gitignored. Code: `backend/experiments/crustdata_retrieval/`. Tests: `tests/test_experiment_crustdata_retrieval.py`.
This is an experiment only: no production ranking, admission, Harvest, or search-path behaviour changed.

## Executive conclusion

- The two strategies retrieve almost different people. Overlap of the first 50 was 0, 7, 0, 1 and 0 candidates
  (Jaccard 0.00 to 0.10).
- NL retrieval produced clearly better-evidenced candidates in 3 of 5 roles (backend, product manager, ambiguous AI) and was mixed in the other two (AI platform, cyber analyst). Across the top 25 of each strategy
  (125 candidates each) the judge verified 1.67 requirements per NL candidate against 0.75 per structured candidate,
  and 18% of NL candidates (23 of 125) had no evidence beyond total years, against 42% (52 of 125).
- Structured retrieval is not useless: it surfaced 5 strong candidates NL missed (4 in the backend/platform role),
  and it was equal or slightly ahead at the very top of two roles (AI platform, cyber analyst). But it adds noise and
  35 of its 125 top-25 candidates carry a title that may be above the target level, against 2 for NL.
- `fit` is returned only for NL queries. Within an NL page it falls monotonically with provider position in all 5
  roles, but evidence does not (rank correlation with position between -0.41 and +0.34).
- Recommendation: keep NL as the primary retrieval; do not replace it with structured; treat structured as an optional
  narrow supplement. Nothing here changes production.

## Experiment setup

- 5 real roles, 2 strategies each, one CrustData page of 50 (`limit: 50`, first page only, same account and API
  version): **10 calls**, up to 500 candidates. CrustData returned no credit fields, so credit cost is unknown.
- Roles (all real): three from the pass 3/4 validations (Senior Backend/Platform Engineer, US, 8+ yrs; Senior AI
  Platform Engineer, Toronto, 7+ yrs; Senior Product Manager B2B SaaS, US, 6+ yrs); Data Analyst Lead - Cyber
  Incident Review (Hyderabad; a very specific title, from production search a7d9fad3); Senior AI Software Engineer
  (global, 394-character JD; broad, from production search 39917197). Roles 1-3 use the stored search intents from
  those validations; roles 4-5 use the real intake on the original JD with the saved location applied.
- **Strategy A (NL)**: the production path unchanged: planner, query expander, capability mapper, the
  `natural_language` query (`search: {query, mode: hybrid}` plus the shared filters).
- **Strategy B (structured)**: the same shared filters (country/state/city, geo_distance radius where set,
  `years_of_experience_raw`, current-company exclusions, the standing executive-title exclusions) plus a fuzzy
  current-title match on the role title and any confirmed include-titles. No `search` clause, no synonym expansion,
  no LLM. Built by the production payload builder so no unverified filter can appear (a test enforces the allowed
  field list). Every requirement the payload cannot enforce is recorded as `structured_unrepresented_requirement`
  (6 to 11 per role: every core/supporting/differentiator signal, the seniority, work mode and any ZIP).
- Evaluation: the top 25 of each strategy (229 unique candidates after 15 reused from earlier Harvest reads) read
  with Harvest and judged by the existing requirement judge against the same requirements. Cost: Harvest $1.40,
  judge about $0.13 (estimated at list price). Positions 26-50 were retrieved but not read.
- Provider order is preserved (position 1..N as returned) in the experiment dataset only.

## Universe vs retrieved (provider-reported `total_count`)

`total_count` is stored as the provider-reported search universe, not as a match count.

| Role | NL retrieved / universe | Structured retrieved / universe |
|---|---|---|
| Backend / platform | 50 / 170,607,386 (relation `eq`) | 50 / 69 |
| AI platform | 50 / 712,425 | 25 / 25 (no cursor: all of it) |
| Product manager | 50 / 193,469,340 | 50 / 229,258 |
| Cyber data-analyst lead | 50 / 3,240,215 | 50 / 505 |
| Ambiguous AI engineer | 50 / 192,385,235 | 50 / 13,907 |

The NL count is the location/experience scope (the whole scope is ranked); the structured count is the number of
profiles satisfying the title filter as well. Structured responses carry no `total_count_relation`; NL responses
carry `total_count_relation: "eq"`. Two envelope keys appeared that the production provider does not keep:
`total_count_relation` and `remarks` (empty in every response).

## Role-by-role comparison

| Role | NL | Structured | Overlap (top 50) | NL-only | Structured-only | Evidence observation |
|---|---|---|---|---|---|---|
| Backend / platform | 50 | 50 | 0 | 50 | 50 | NL clearly stronger: 17 strong candidates in the top 25 vs 4 |
| AI platform | 50 | 25 | 7 (J 0.10) | 43 | 18 | Mixed: structured equal at the top 10 (1.1 vs 1.0 core), NL ahead at 25; 1 strong NL, 0 structured |
| Product manager | 50 | 50 | 0 | 50 | 50 | NL clearly stronger (1.4 vs 0.1 core in the top 10); 10 of 25 structured titles may be above level |
| Cyber analyst lead | 50 | 50 | 1 | 49 | 49 | Weak either way; structured has more demonstrated work at the top 10 (0.5 vs 0.1), NL has 3 strong vs 0 |
| Ambiguous AI engineer | 50 | 50 | 0 | 50 | 50 | NL somewhat stronger (6 strong vs 1); 15 of 25 structured titles may be above level |

"Strong" here means verified evidence for at least 60% of the core requirements (the shared years line excluded).
It is a descriptive threshold, not a quality label.

## Provider ordering and fit

- `fit` is present on every NL candidate and on **no** structured candidate: it is query-dependent (it needs the
  `search` clause).
- NL fit sequences: backend 36 strong then 14 possible; cyber 1 strong, 44 possible, then 5 weak at positions 46-50;
  AI platform, product manager and ambiguous AI engineer all 50 strong. Fit never increases with position (5 of 5).
  Rank correlation between position and ordinal fit: -0.78 (backend), -0.56 (cyber), undefined for the other three
  (fit does not vary). Descriptive only.
- Fit did not discriminate in 3 of 5 roles, so it cannot be used to choose among those candidates.
- Evidence versus position inside the first 25 NL results: rank correlation +0.06, +0.34, -0.41, -0.21, +0.04; mean
  evidence at positions 1-10 vs 11-25 is 2.2/2.3, 1.1/1.7, 2.6/1.9, 0.8/0.9, 1.5/1.7. Provider position within the first
  window does not order candidates by verified evidence. Structured order (no fit) also shows no pattern.

## Evidence comparison (top 25 of each strategy, pooled over 5 roles, 125 candidates each)

| Measure | NL | Structured |
|---|---|---|
| Verified requirements per candidate (years line excluded) | 1.67 | 0.75 |
| Demonstrated-work evidence per candidate | 1.01 | 0.50 |
| Candidates with no evidence beyond years | 23 (18%) | 52 (42%) |
| Top 10 only: verified requirements per candidate | 1.64 | 0.82 |
| Titles that may indicate a level above the target | 2 | 35 |

The structured title filter matches the role title text (93% of structured candidates have a direct title
match) but a matching title predicts little about the requirements: the same title words appear on people whose
profiles show none of the core requirements.

## What NL uniquely finds

- Candidates whose title does not contain the role words but whose work does: "Senior Machine Learning Engineer"
  for the AI platform role (3 of 4 core requirements evidenced), "AWS Cloud Engineer" and "Senior Cloud Native Backend
  Engineer | Java, Go, AWS, Kubernetes" for the backend role, and generic "Senior Software Engineer" titles whose
  described work matches (6 strong for the ambiguous role, 17 for backend).
- Title variants the role title does not spell out ("Senior Specialist Backend Engineer", "Lead Data Analyst" for
  "Data Analyst Lead").
- Its 50-candidate window is drawn from a scope of 0.7M to 193M profiles; the structured windows are drawn from 25
  to 229k.

## What structured uniquely finds

- Exact or near-exact title matches NL did not rank into its first 50: "Senior Backend / Platform Engineer",
  "Senior Backend Engineer - Platform Enablement", "Backend Platform Engineer" (4 strong in the backend role) and one
  "Senior Software Engineer, Productization & AI Systems" in the ambiguous role.
- For the narrow Toronto AI platform role the structured query returned the whole title-matching set (25), so it is
  exhaustive for that title where NL is not.
- Its weaknesses: it cannot express any skill or domain requirement, its order carries no relevance signal, and it
  surfaces more staff/principal titles.

## Requirements that are hard or impossible to represent structurally

All core/supporting/differentiator requirements (Python, Kafka, relational databases, distributed systems, cloud,
mentoring, B2B SaaS, cybersecurity, AI/ML exposure): skills and technologies are not filterable or returned fields
on this account. Seniority (only through title text and the years floor), work mode and ZIP are also unrepresentable.
A compound role title such as "Backend/Platform Engineer" is matched as one phrase, which is why the structured
universe for that role is only 69 profiles; splitting it would be synonym expansion, which the experiment
deliberately did not do.

## Implication for admission (25 of 50)

- What it tells us: NL's first page contains real evidence beyond what a title match predicts, so retrieval is not
  the bottleneck the structured alternative would fix. Provider position and `fit` do not order candidates by
  verified evidence within the first 25, so admitting "the first 25 as returned" is not supported. The 18% of NL top
  25 with no evidence beyond years is the same effect the Release 1.1 audit saw.
- What it does not tell us: anything about positions 26-50 (not read), whether pages beyond the first hold better
  candidates, or how many strong candidates exist outside the 50. It does not evaluate a triage step. It cannot say
  whether judging all 50 would be worth its cost.

## Recommendation (from observed evidence only)

- Keep NL as the primary retrieval.
- Do not switch to structured-only: evidence per candidate was about half and 42% had none.
- A merged NL + structured set is defensible only as a small supplement for roles with a distinctive, literal title,
  where it added 4 strong candidates the NL page missed; in 3 roles it added none. If it is ever tried, dedupe and
  judge before admission, because its raw order and volume add noise.
- Next hypotheses (ledger): NL depth beyond page 1; a cheap pre-triage that reads profile text; splitting compound
  titles.

## Limitations

- Five roles, one retrieval per strategy, first page only. CrustData results vary between runs (the same Toronto
  search overlapped only 9 of 25 earlier), so a repeat could differ.
- The requirements being judged come from the same intent the NL query is written from; the structured query has no
  way to use them. That is the property under test, but it favours NL on this metric.
- No ground-truth labels. "Strong" and evidence counts are descriptive outputs of the judge, which is probabilistic
  and reads only what the profile says. Harvest failed to read a few profiles (evidence then rests on CrustData text
  only).
- `fit` semantics are undocumented and it was `strong` for every NL result in three roles, so its inconsistency
  across roles is unexplained. Provider order is the order CrustData returned, with no documentation of how it is
  produced.
- Roles 1-3 use intents from earlier validations rather than a fresh intake; roles 4-5 used one intake run each.
- Evaluation covers the top 25 of each strategy only.

## Artifacts

Under `output/experiments/crustdata_nl_vs_structured/crustdata-nl-vs-structured-20260924/` (local, gitignored):
`manifest.json` (intents, NL and structured payloads, unrepresented requirements), `retrieval_<role>_<nl|structured>.json`
(request payload, response envelope, provider-ordered rows, raw items), `evaluation_<role>.json`,
`harvest_evaluation_cache.json`, `evaluation_stats.json`, `analysis.json`.
