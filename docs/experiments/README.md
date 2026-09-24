# RecruiterAI experiment ledger

The canonical list of retrieval / ranking / evidence experiments. Every new experiment gets a row here and a report
in this folder; raw artifacts live under `output/experiments/<experiment>/<id>/` (gitignored: they contain candidate
data). Experiment code lives under `backend/experiments/` and must never change the production search path.

## Ledger

| ID | Date | Hypothesis | Roles | Strategies | CrustData calls | Cost | Main result | Confidence / limits | Decision | Follow-up hypothesis | Artifacts |
|---|---|---|---|---|---|---|---|---|---|---|---|
| EXP-001 `crustdata-nl-vs-structured-20260924` | 2026-09-24 | Given the same confirmed hiring intent, CrustData natural-language retrieval returns materially different (and better-evidenced) candidates than a query built only from verified structured filters. | 5 (backend/platform, AI platform, product manager, cyber data-analyst lead, ambiguous AI engineer) | A: production NL path. B: verified structured filters, current-title match, no NL clause, no synonyms | 10 (1 page of 50 each; credits not reported in the response) | Harvest $1.40 (229 reads) + judge ~$0.13 | Candidate sets are almost disjoint (overlap 0, 7, 0, 1, 0 of 50). NL top-25 candidates carry about twice the verified requirement evidence (1.67 vs 0.75 requirements per candidate) and far fewer "possibly above level" titles. `fit` exists only on NL results and falls monotonically with position, but position does not track evidence. | 5 roles, 1 retrieval per strategy, first page only, no ground-truth labels, requirements come from the same intent the NL query is written from. | NL stays the primary retrieval. Structured is a narrow supplement at best, not a replacement. No production change. | Would deeper NL pages or a cheap pre-triage change who gets admitted? Does splitting compound titles ("Backend/Platform Engineer") recover the structured recall? | [report](crustdata-nl-vs-structured.md); `output/experiments/crustdata_nl_vs_structured/crustdata-nl-vs-structured-20260924/` |

## Open hypotheses (not yet run)

| Hypothesis | Why it matters | Depends on |
|---|---|---|
| Provider ordering: is CrustData's position within the first page evidence-bearing? | EXP-001 found `fit` is monotone in position but evidence is not; needs more searches and depth beyond 25. | EXP-001 |
| Fit usefulness: is `fit` ever discriminating? | In 3 of 5 EXP-001 roles every NL result was `strong`. | EXP-001 |
| Admission strategy: judge all 50 vs cheap pre-triage vs deterministic admission. | Release 1.1 found 39 of 50 candidates tie at the baseline cutoff. | Release 1.1 audit |
| Retrieval depth: pages 2+ of NL. | EXP-001 only saw the first window. | EXP-001 |
| Multi-query convergence: does a candidate found by two queries carry more evidence? | The current 0.5 convergence bonus is untested. | EXP-001 |
| Harvest value: how much does the full profile change the verdict vs CrustData-only evidence? | Harvest is the largest per-search cost. | - |
| Requirement stability: same JD, repeated intake. | Measured once in Release 1.1 (core 4-6 items before temperature 0). | Release 1.1 |
