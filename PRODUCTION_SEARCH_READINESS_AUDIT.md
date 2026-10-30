# Production Search Path — Read-Only Product-Readiness Audit

**Date:** 2026-10-27 · Branch `claude/sleepy-clarke-5ueovf` · HEAD `fbd5626` · working tree clean except two untracked, preserved audit files (`CONFIRMATION_TO_PROVENANCE_AUDIT.md`, this file). **No provider/model calls, no retrieval, no code changes, no commits, no tests executed.**

Each conclusion is tagged **[Verified in code]**, **[Offline evidence]**, or **[Hypothesis]**.

---

## Executive summary (plain English)

The production path a recruiter actually uses is **well-engineered at the component level and deliberately recall-friendly**: a confirmed brief becomes a legacy `SearchIntent`, which the planner turns into a **relevance-ranked natural-language search** (the soft topical signal the experimental compiler lacked) plus a conservative title-expansion query, then candidates are deduped, Harvest-enriched, ranked, and evaluated by an exact-quote-gated Judge with three-state exclusions.

But two things stop it short of "ready to trust":

1. **There is no measured evidence that the integrated production path produces a good shortlist for any real role.** Every quality artifact in the repo validates a *component* (intake extraction, or the Judge on *synthetic* profiles) or the *experimental compiler* path — never the production path end-to-end on live candidates.
2. A **standing policy excludes current Director/VP/Head-of titles from every query**, which is actively harmful for the finance roles under study (a current "Director, FP&A" is dropped).

The components are sound; the integrated product is **unproven, not disproven**. Under the no-spend constraint, the evidence does not justify a code change yet.

---

## Production flow (numbered)

1. **Intake** (`intake_reasoning.py`, `gpt-4o-mini`, temp 0) → `IntakeResult` (Task A/B requirements; `posted_title` kept verbatim).
2. **Confirmation** (`confirmation.py`) → recruiter edits a whitelist (`ConfirmationEdits`); server builds an **immutable, content-hashed** snapshot.
3. **Translate** (`search_translator.build_confirmed_hiring_intent` → `to_search_intent`) → legacy `SearchIntent`.
4. **Plan** (`search_planner.SearchPlanner.build`) → 2 queries: primary **NL hybrid** + supplementary **title-expansion**.
5. **Provider** (`crustdata.CrustDataProvider`) → `/person/search`: structured `filters` (AND) + `search:{query, mode:"hybrid"}`.
6. **Pipeline** (`search_pipeline.py`) → merge/dedup → fire query 2 if pool < 25 → Harvest enrich top-N → rank → admit (cap 25).
7. **Evaluate** (`requirement_judge.py` + `evidence_check.py` + `exclusion_outcome.py`) → per-requirement met/partly/not_evidenced + exclusions.

---

## Stage-by-stage

| Stage | Actual behavior | Evidence (file/function) | Risk or gap |
|---|---|---|---|
| Confirmed → SearchIntent | Preserves: `posted_title`+source, seniority, include/exclude titles (title-expanded), experience min/max, locations+radius+work_mode, `exclude_current_companies`, `preferred_company_types`, NL query, and **skills as `core/supporting/differentiator_signals`** (not a `Skills` filter). **[Verified in code]** | `search_translator.to_search_intent` [:333-402](backend/services/search_translator.py#L333-L402) | Required/preferred skills are **not** structured filters on this path — they live in the NL query (soft) and the per-candidate evidence builder. Intended, but means skill enforcement is entirely downstream. |
| Query construction | Query 1 = NL `search:{query,mode:"hybrid"}` (**no include-title filter** — by design the strongest discovery), carrying skills/role/signals as relevance text. Query 2 = `include_titles` fuzzy-OR on current title. Shared **hard** filters: location (country/state/city `in`), experience years, exclude-titles fuzzy-NOT on current title. `zip_codes`/`work_mode` carried only to trigger drop-and-warn (no provider field). **[Verified in code]** | `SearchPlanner.build`, `crustdata._build_payload` [:145-146](backend/providers/crustdata.py#L145-L146), `_build_filter_conditions` [:150-179](backend/providers/crustdata.py#L150-L179) | **Forced `EXECUTIVE_TITLE_EXCLUSIONS`** (Director, VP, Head of…) applied to current title on **every** query ([search_planner.py:16-43](backend/services/search_planner.py#L16-L43)). Retrieval relevance rests almost entirely on one LLM-authored NL query; its quality is unmeasured. No-conditions fallback matches `name (.) "a"` ([crustdata.py:295](backend/providers/crustdata.py#L295)). |
| Retrieval handling | One request per query; normalize to `Candidate`; merge/dedup by `crustdata_person_id`; supplementary query only if unique pool < `DISCOVERY_TARGET_POOL_SIZE=25`; workspace hard cap `MAX_WORKSPACE_CANDIDATES=25`; cursor paging; retrieval history tracked. **[Verified in code]** | `search_pipeline.py` [:74-92,109-136](backend/services/search_pipeline.py#L74-L136), `candidate_merger.py` | Dedup key is the provider id only — the same person returned without that id (unlikely on one provider) would not merge. Minor. |
| Enrichment | Harvest enriches top-N (config default 25) to give the Judge deep profile passages. **[Verified in code]** | `search_pipeline.py`, `providers/harvest.py`, `config.get_harvest_enrichment_top_n` | If Harvest fails/omits a profile, the Judge sees thin passages → genuine skills read as `not_evidenced` (false negatives at evaluation). **[Hypothesis]** |
| Evaluation | Two-stage Judge (`gpt-4o-mini`, temp 0): requirement verdicts met/partly/not_evidenced with an **exact-quote gate** and no outside knowledge; duration only from the "career dates" passage; a second review pass re-checks each quote; ≤30 passages × 900 chars. Exclusions three-state PRESENT/NOT_PRESENT/INSUFFICIENT with Decision-A show+flag. **[Verified in code]** | `requirement_judge.py` [:58-81,102-109](backend/services/requirement_judge.py#L58-L109), `evidence_check.py`, `exclusion_outcome.py` (referenced by `search_pipeline.py`, `candidate_presentation.py`) | Strict quote gate is good for trust but, combined with enrichment gaps, biases toward under-crediting. "Clearly useful" is a strict conjunction (met>0, no partly, no not_evidenced) — most real candidates will land "borderline". **[Hypothesis]** |

---

## Existing evidence of candidate-quality performance (and limits)

- **Intake extraction** — `gpt-6.1-sol` stable 5/5 vs intake gold for Role 2/3. **[Offline evidence]** (`intake_strategy/RESULTS_ROLE{2,3}.md`, `RESULTS_HARDENING.md`). *Limit:* validates understanding, not retrieval or shortlist.
- **Judge correctness** — exact-quote binding, depth ceiling, three-state exclusions validated over 186+ synthetic runs, `gpt-4o-mini` temp 0. **[Offline evidence]** (`compiler_contract/RESULTS_REAL_JUDGE_VALIDATION.md`, `RESULTS_DEPTH_CONTRACT_VALIDATION.md`). *Limit:* **synthetic candidates against compiled contexts** — not production retrieval output.
- **Provider filter capabilities** — current/any/past company, description/headline keyword discrimination, whole-word `(.)`, skills-list unavailable. **[Offline evidence]** (live probes, memory `crustdata-verified-capabilities`). *Limit:* filter behavior, not shortlist quality.
- **End-to-end production shortlist quality** — **none.** The only live end-to-end run (`live_retrieval_ab`, Role 3) is the **experimental compiler** path, not production, and produced **no clearly-useful candidate in either arm**. **[Verified absence]**
- Integration tests (`test_search_integration.py`, `test_api.py`, `test_candidate_evidence_builder.py`) use **mocked/stubbed providers** — they prove wiring, not real candidate quality. **[Verified in code]**

---

## Three highest-priority readiness gaps (ranked)

1. **No measured end-to-end production shortlist quality (impact HIGH, confidence HIGH).** Every component is validated in isolation; the integrated path has never been shown to return people a recruiter would contact for a real role. This is the core product claim and it is unproven. **[Verified absence of evidence]** — cannot be closed offline without a live run (forbidden by no-spend).
2. **Forced executive-title exclusions drop qualified senior/finance candidates (impact HIGH, confidence HIGH).** `EXECUTIVE_TITLE_EXCLUSIONS` removes current Director/VP/Head-of titles on every query via fuzzy-NOT; for the FP&A role family a current "Director, FP&A"/"VP Finance"/"Head of FP&A" is excluded before the Judge ever sees them. **[Verified in code]** The policy is current-title-scoped (past titles safe) and documented as intentional for IC/eng roles, but is a demonstrable false-negative source for senior finance roles.
3. **Retrieval relevance depends on a single, unmeasured LLM-authored NL query (impact MEDIUM–HIGH, confidence MEDIUM).** There is no structured topical floor; if the NL query is generic, the hybrid search yields loosely-related finance profiles that the (correctly strict) Judge then rates thin. No artifact rates NL-query retrieval quality. **[Verified dependency in code; quality impact is Hypothesis]**

*Separated as risks/unknowns, not blockers:* Harvest-gap under-evidencing (#enrichment); Judge strictness pushing real candidates to "borderline"; dedup-by-provider-id only; skills enforced only downstream.

---

## Recommended next step

**No code change is justified by the current evidence** — the components are sound and nothing here is demonstrably broken in a way that offline analysis can both prove and fix. The single highest-value action that respects the no-spend constraint is **product usage, not a research experiment**: have the recruiter run **one real search through the existing production UI** on a role they know well and judge the shortlist-with-evidence by eye ("would I contact these people?"). That converts gap #1 from an unknown into direct signal at the cost of a normal search, not a controlled A/B.

If even a single live search is out of scope right now, the honest conclusion is: **hold.** Queue gap #2 (narrow the executive-title exclusion so legitimate senior-finance titles like Director/VP/Head-of-FP&A are not auto-dropped for finance roles) as the one concrete, offline-fixable item for a future authorized change — but do **not** implement it now.

Do not launch a new paid compiled-vs-legacy experiment to gather more data; that is not warranted.

---

## Report metadata

- **File:** `PRODUCTION_SEARCH_READINESS_AUDIT.md` (created; not committed).
- **Inspected:** `api.py`, `confirmation.py`, `search_translator.py`, `search_planner.py`, `crustdata.py`, `search_pipeline.py`, `requirement_judge.py`, `structured_intent.py`; `RESULTS_*.md` inventory; test file definitions (not run); memory `crustdata-verified-capabilities`.
- **Unresolved questions:** (a) exact admission/exclusion branch wiring in `search_pipeline`/`admission.py` was confirmed by reference, not line-by-line traced; (b) real NL-query retrieval quality is unmeasured; (c) production end-to-end shortlist quality has no artifact. None resolvable without a live search.

*Report only. No recommendation implemented. Awaiting explicit approval.*
