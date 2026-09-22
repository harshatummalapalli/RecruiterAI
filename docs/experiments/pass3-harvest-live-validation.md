# PASS 3 — Live Validation: CrustData → Baseline Ranking → Harvest Top-5 → Rerank

**Date:** 2026-09-22
**Type:** Observation experiment only. No ranking weights, architecture, or source code changed as a result of this run.
**Driver script:** `C:\Users\harsh\AppData\Local\Temp\claude\c--Projects-RecruiterAI\35d5fbbe-8b09-460e-88a0-fd2b2a91ca10\scratchpad\pass3_experiment.py`
**Raw data:** same scratchpad directory — `pass3_all_results.json` (summary) and one `pass3_<role>_raw.json` per role (full API response + captured pre-Harvest baseline).

The experiment drove the actual production code path — `POST /intake/start` → `/intake/{id}/answer` (if needed) → `/intake/{id}/confirm` → `POST /search` — through `FastAPI TestClient` against a real `create_app()` using the repo's real `OPENAI_API_KEY`, `CRUSTDATA_API_KEY`, and `HARVEST_API_KEY`. Auth was bypassed via a FastAPI dependency override (`require_session`), not by touching `backend/auth.py`. The only instrumentation was a wrapper around `CandidateRanker.rerank_top_n` that records its inputs before calling straight through to the real, unmodified method — this is how "baseline top-5 pre-Harvest" was captured, since the API itself only returns the final (post-rerank) result.

---

## Roles run

| Role | Raw input | Location |
|---|---|---|
| 1. Epiq Senior AI Platform Engineer | Reused JD text matching the earlier 5-candidate controlled experiment | Toronto, Canada |
| 2. Senior Backend / Platform Engineer | Distributed systems, cloud/infra, Go/Java, Kafka | United States |
| 3. Senior Product Manager | B2B SaaS, less keyword-heavy, non-engineering | United States |

All three reached intake `status: ready` with **zero** clarification rounds needed — the JD text was specific enough that no ask-issues were raised.

---

## A. Per-role results

### 1. Epiq — Senior AI Platform Engineer (pool: 25)

| Final rank | Baseline rank | Candidate | Baseline score | Final score | Tier | Harvest signals used |
|---|---|---|---|---|---|---|
| 1 | 5 | Mustafa B. — Senior Platform & AI Engineer | 7.05 | **9.95** | direct | python, reliability, typescript, orchestration |
| 2 | 1 | Abhishek Arya — Senior Associate | 8.05 | 9.35 | direct | "Distributed Systems" skill, background |
| 3 | 2 | Hartaran Panesar — Senior AI Platform Engineer | 8.05 | 9.05 | direct | reliability |
| 4 | 3 | Nick Logachev — Senior SWE (AI Platform) | 7.65 | 8.95 | direct | distributed, **mcp** |
| 5 | 4 | Nnaemeka Nnamani — Senior AI/ML Platform Engineer | 7.35 | 7.35 | direct | *(none — 0 matched signals)* |

All 5 baseline top-5 candidates changed rank position. Positions 6–25 (`160003923, 109797646, 117520055, 207375806, 197568845, …`) were untouched — confirmed identical before/after rerank.

**Notable:** Mustafa B. jumped from baseline #5 to final #1 purely on Harvest-sourced evidence (real, specific terms: python/reliability/typescript/orchestration from his actual employment description at AgentCore). Nick Logachev's Harvest data surfaced "mcp" — a named nice-to-have framework CrustData's baseline fields never showed. Nnaemeka Nnamani's Harvest fetch succeeded but contributed zero matched terms — pure enrichment cost with no decision value for this candidate.

### 2. Senior Backend / Platform Engineer (pool: 25)

| Final rank | Baseline rank | Candidate | Baseline score | Final score | Tier | Harvest signals used |
|---|---|---|---|---|---|---|
| 1 | 3 | Adam Cooper — Senior SWE @ Khan Academy | 6.75 | **9.25** | direct | aws, event, observability, mentoring, work |
| 2 | 1 | Shankalpa Lamichhane — Sr SDE @ Tyler Technologies | 8.35 | 9.25 | direct | work, engineers, consumer |
| 3 | 5 | Ivan Shmelov — SWE @ Wix | 6.25 | 7.75 | direct | project:event, project:engineers, work, consumer |
| 4 | 4 | Fernando Castro — Senior SWE @ Deutsche Bank | 6.25 | 7.45 | adjacent | **datadog**, work, engineers, **fintech** |
| 5 | 2 | Rahul Shinde — Senior SWE @ ConnectWise | 6.85 | 7.15 | adjacent | work *(only)* |

Baseline positions 6–25 unchanged. 4 of 5 changed rank; Fernando Castro stayed at baseline/final rank 4.

**⚠ False-positive / scope flag:** Ivan Shmelov carries an active concern — `"Candidate's seniority level ('Entry Level') does not match the target ('senior')."` — yet Harvest evidence still pushed him from baseline #5 to final #3, *above* two candidates with no such concern. The rerank scorer currently has no mechanism to discount score for an unresolved concern; it rewards evidence density regardless. This is a real, observed instance of the exact "False-Positive / Scope Evidence" risk category the experiment was designed to probe.

**Notable meaningful evidence:** Fernando Castro's Harvest data surfaced "datadog" (a named nice-to-have observability tool) and "fintech" (a named bonus-differentiator background) — both specific, verifiable, and exactly the kind of thing CrustData's baseline fields could not show.

### 3. Senior Product Manager (pool: 25)

| Final rank | Baseline rank | Candidate | Baseline score | Final score | Tier | Harvest signals used |
|---|---|---|---|---|---|---|
| 1 | 4 | Kim Walker — Senior Interactive Producer @ Apple | 5.05 | **9.25** | direct | work, analytics, communication, testing, prior, technical |
| 2 | 1 | Joicyellen Pereira — Senior Product Manager | 6.05 | 8.25 | direct | agile, analytics, stakeholder, testing, saas, prior, technical |
| 3 | 2 | Shiben Chourey — Product Manager @ LTIMindtree | 5.85 | 7.75 | direct | agile, analytics, stakeholder, testing, saas, prior, technical |
| 4 | 5 | Roman Royzman — Senior Product Manager | 5.05 | 7.65 | direct | using, stakeholder, saas, prior, **"Technical Product Management" skill** |
| 5 | 3 | Shalaka Greene — Senior Product Manager @ Mitratech | 5.15 | 7.45 | direct | agile, decisions, stakeholder, testing, saas, prior |

Baseline positions 6–25 unchanged. All 5 changed rank position.

**⚠ False-positive / scope flags:** Shiben Chourey and Shalaka Greene both carry an active concern (`"Entry Level Manager" does not match "Senior"`), and both remained in — or moved up within — the final top-5 despite it. Same pattern as Ivan Shmelov above.

**Signal quality is visibly noisier here than the two engineering roles.** Most of this role's Harvest-sourced "strong evidence" bullets are single generic words (`work`, `prior`, `testing`, `technical`, `using`, `decisions`) that happen to appear both in the JD's phrasing (e.g. "…prior experience", "…technical background", "A/B testing") and, incidentally, in a candidate's long-form employment description. The genuinely meaningful hits — `analytics`, `communication`, `stakeholder`, and Roman Royzman's explicit "Technical Product Management" skill listing — are real and valuable, but they're a minority of the matched terms for this role.

---

## B. Cross-role report

| # | Metric | Value |
|---|---|---|
| 1 | Total candidates discovered | 75 (25 per role) |
| 2 | Total candidates enriched | 15 (5 per role — configured top-N) |
| 3 | Harvest success rate | 15 / 15 = **100%** |
| 4 | Total Harvest cost | **$0.096** (15 × $0.0064, full-profile lookups) |
| 5 | Candidates with meaningful new evidence | **9 of 15** — Mustafa B., Abhishek Arya, Nick Logachev (mcp), Hartaran Panesar, Adam Cooper, Fernando Castro (datadog/fintech), Joicyellen Pereira, Roman Royzman, Kim Walker (partial) |
| 6 | Candidates whose ranking (position) changed | **14 of 15** within their top-5 slice (only Fernando Castro, backend role, stayed at rank 4) |
| 7 | Candidates whose relevance tier changed | **0** — by design, tier is derived from title/seniority alignment (CrustData baseline fields only) and is architecturally untouched by Harvest; only score/evidence are enriched. Confirms the intended separation held in practice. |
| 8 | False positives discovered | **3** — Ivan Shmelov, Shiben Chourey, Shalaka Greene, all carrying an unresolved seniority-mismatch concern that Harvest evidence density still ranked upward |
| 9 | Important new positive evidence | Nick Logachev's MCP mention; Fernando Castro's Datadog + fintech background; Abhishek Arya's and Roman Royzman's explicit skill-list corroboration ("Distributed Systems", "Technical Product Management"); Adam Cooper's AWS/observability/mentoring detail |
| 10 | Harvest added info but no decision value | **1 clean case** (Nnaemeka Nnamani — successful fetch, 0 matched signals); a further ~5-6 candidates had Harvest evidence that was mostly generic single-word matches (`work`, `prior`, `testing`, `technical`, `using`, `decisions`) contributing little beyond noise |
| 11 | Average enrichment latency | **5,765 ms** (range: 2,750 ms – 10,008 ms) |

---

## C. The two questions the experiment was designed to answer

**"After seeing Harvest-enriched candidates, how often did we know something materially important that we did NOT know from CrustData?"**

In 9 of 15 cases (60%), yes — and in a handful of those it was decisive, not marginal: Mustafa B.'s entire #1 ranking in the Epiq role rests on Harvest-only evidence (python/reliability/typescript/orchestration from an employment description CrustData never showed); Nick Logachev's and Fernando Castro's named-technology hits (MCP, Datadog, fintech) are exactly the kind of specific, checkable fact a recruiter could not have gotten from title/headline alone. In the remaining ~40% of cases, Harvest either added nothing new (1 clean case) or added mostly generic filler words that happened to overlap JD phrasing without representing a real new fact.

**"How often did Harvest change what a recruiter should investigate next?"**

For at least 4 of 15 candidates, yes, meaningfully: Mustafa B. and Adam Cooper both moved from mid-pack (baseline #5 and #3) to final #1 on the strength of Harvest evidence — a recruiter using only baseline CrustData ranking would have looked at a different person first. Separately, and just as important: for 3 candidates (Ivan Shmelov, Shiben Chourey, Shalaka Greene), Harvest enrichment surfaced a seniority-mismatch concern that should make a recruiter *more* cautious, even though the ranking mechanism itself pushed their score up. The system correctly *shows* the concern text next to the score — but does not itself resolve the tension, which is appropriate: RecruiterAI reasons over evidence, the recruiter decides.

---

## D. Architecture behavior check

Confirmed exactly as designed, with live traffic:

- **Baseline ordering outside the enriched top-N is inviolate.** Verified directly for all 3 roles: positions 6–25 (candidate IDs, in order) were byte-identical before and after Harvest reranking.
- **Only the top-5 slice was ever enriched or reordered.** 15 Harvest calls total across 3 roles (5 × 3), never more.
- **No enrichment promotion.** No unenriched candidate (rank 6+) appeared in any final top-5. Not implemented, not observed.
- **Relevance tier is untouched by Harvest.** 0 of 15 candidates changed tier — tier logic never consulted Harvest evidence, exactly as designed.
- **Harvest never broke discovery.** All 15 calls succeeded; no candidate fell back to a failure path in this run, so failure-handling wasn't exercised live here (it's covered by the 27 Harvest-specific unit/integration tests from PASS 2 instead).
- **Idempotency was not exercised in this run** (each role only ran once, so there was no second POST to the same `search_id` to test cache-reuse against) — this is already covered by `tests/test_api.py`'s two dedicated idempotency tests from PASS 2, not re-verified live here.

**One real gap surfaced, not present in the original design spec:** reranking currently has no mechanism to weigh an active `potential_concerns` flag against the score boost Harvest evidence provides. All 3 false-positive cases above are unresolved-seniority-mismatch candidates whose Harvest-driven score increase moved them up anyway. This is not a bug relative to what PASS 2 was scoped to build — concern-weighted reranking was never part of the spec — but it is exactly the kind of thing a real-role observation run is supposed to surface, and is worth a deliberate decision (not a silent fix) in a future pass.

A second, smaller gap: the existing generic-term stoplist (`_GENERIC_TERMS`) does not cover common connective English words (`work`, `prior`, `background`, `testing`, `technical`, `using`, `decisions`, `consumer`, `engineers`) that appear both in JD ranking-signal phrasing and, incidentally, in Harvest's much longer free-text fields. This produced several oddly-worded, low-value "strong evidence" bullets (e.g. *"work described there includes 'work'"*) — most visible in the Product Manager role, where there are fewer high-specificity domain nouns to anchor on. Not a correctness bug (still source-labeled, still corroboration-based, never fabricates years or invents facts) but a signal-to-noise issue worth a future look at the stoplist.

No ranking weights were changed. No architecture was changed. This document is the observation only.
