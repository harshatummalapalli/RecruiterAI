# PASS 4 — Evidence Quality + Requirement Concerns

**Date:** 2026-09-22
**Scope:** Fixed the evidence-extraction/matching layer only. No ranking weights, top-N, rerank mechanics, or relevance-tier logic were touched.
**Driver script (re-run):** `pass4_experiment.py` (scratchpad) — same 3 PASS 3 roles, same code path.
**Raw data:** `pass4_all_results.json` + one `pass4_<role>_raw.json` per role (scratchpad), for direct diffing against the PASS 3 files.

---

## A. What changed

`backend/services/candidate_evidence_builder.py`'s term-extraction and matching engine was rewritten. Previously, `_extract_signal_terms()` tore each Confirmed-Hiring-Intent signal sentence into independent single words (≥4 chars, minus a stoplist) and `_build_role_alignment()` did **raw substring containment** (`term in text_lower`, no word boundary, no context) against candidate text. That is why "work" — extracted from "...data-driven performance **work**." — matched anywhere the literal string "work" appeared in a Harvest employment description, producing bullets like *"work described there includes 'work'."*

The new engine:
- Tokenizes each JD sentence with position tracking.
- Groups ordinary significant words as before (unchanged — "distributed", "analytics", "stakeholder", "Kafka" etc. still match exactly as they did).
- Introduces a small `_PHRASE_ONLY_TERMS` set (`work`, `working`, `worked`, `technical`, `testing`, `tested`, `consumer`, `consumers`) — words with real domain meaning only inside a phrase, never alone. These now require a genuine neighboring content word in the **same JD sentence**, matched via a windowed multi-word regex (up to 3 filler words tolerated) against the candidate's actual text — not a bare substring anywhere.
- Comma/semicolon/colon in the JD sentence is treated as a hard phrase break, so a comma-separated list of concepts ("instrumentation, on-call, incident response, and data-driven performance work") is extracted as separate list items, not glued into one unmatchable mega-phrase.
- Word-boundary-safe matching (`(?<![A-Za-z0-9])term(?![A-Za-z0-9])`) replaces raw substring containment everywhere — fixes a latent bug where e.g. "rag" could match inside "storage".
- Modestly expanded `_GENERIC_TERMS` (secondary, not primary fix): `prior`, `using`, `use`, `used`, `decisions`, `decision`, `engineers` — pure connectors with no phrase-rescuable meaning at all.
- Source priority for corroboration (`labeled_text_sources()`) is now **strength-first**, not discovery-order-first: Harvest employment descriptions/projects/certifications (STRONG) are checked before headline/title-history/named-skill (SUPPORTING), so when the same concept is corroborated in two places, the stronger, more checkable one wins the attribution and the wording.
- `MatchedSignal` gained `evidence_type`, `evidence_text`, `strength`. `evidence_text` is the actual contextual sentence the match was found in (extracted via sentence-boundary splitting), not the bare matched word.
- `MatchExplainer._strong_evidence()` now quotes `evidence_text` for demonstrated-work bullets instead of the bare term — *"Led the end-to-end product lifecycle — from strategy and roadmap to launch..."* instead of *"...mentions 'work'."*

## B. Why it changed

PASS 3's live 3-role experiment showed this concretely: Product Manager evidence was visibly noisier than the two engineering roles because JD phrasing there leans on generic connector words (`work`, `prior`, `testing`, `technical`, `using`, `decisions`) that Harvest's much longer free-text fields matched incidentally, producing evidence a recruiter couldn't act on or verify. The fix target was explicit: "a matched word is not evidence; evidence requires meaningful contextual support" — implemented deterministically (no LLM, no new dependency), per the explicit design constraint.

## C. Evidence model changes

`backend/models/candidate_evidence.py`:
- `MatchedSignal` gained three fields: `evidence_type` (`"demonstrated_work"` | `"certification"` | `"named_skill"` | `"title_history"` | `"headline"`), `evidence_text` (the actual contextual quote), `strength` (`"strong"` | `"supporting"`) — implementing PART 3's hierarchy (demonstrated work/project/certification = strong; named skill/headline/career history = supporting) as data, not just prose convention.
- `labeled_text_sources()` returns a new `TextSource` NamedTuple (`label, text, detail, evidence_type, strength`) instead of a bare 3-tuple, reordered strength-first.
- `CandidateRanker`'s scoring formula (`_calculate_score`) is completely untouched — it still keys only on `tier` (core/supporting/differentiator, JD-priority), never on the new `strength` field. `strength`/`evidence_type` are presentation/trust metadata only, exactly as PART 6 required.

## D. Concern handling

Audited first (PART 1): `potential_concerns` was already computed by `MatchExplainer._potential_concerns()` entirely independently of `matched_signals`/`strong_evidence` — a seniority mismatch was never at risk of being silently erased by strong evidence; both lists are structurally separate fields on `MatchExplanation` and both always render. This part of the architecture was sound, so nothing was restructured — per the instruction to preserve, not rebuild, an already-correct separation. What was added: a docstring on `MatchExplanation` naming the three axes explicitly (role alignment / evidence strength / requirement concerns) as a standing contract, plus a regression test (`test_active_seniority_concern_remains_visible_alongside_strong_harvest_evidence`) proving a candidate with a real seniority-mismatch concern still shows it in full, unaltered, side by side with strong Harvest evidence.

Live confirmation from the PASS 4 re-run: 4 Product Manager candidates in the final top-5 carry an active concern (`"Entry Level Manager"`/`"CXO"` vs. target `"Senior"`), and every one of them still shows the concern text in full next to several strong, contextual evidence bullets — see section F below. **Ranking itself was not changed** (per PART 11); a concern still doesn't discount score. That remains open, flagged in G.

## E. Tests

14 new regression tests added to `tests/test_candidate_evidence_builder.py` (all in a new PASS 4 section), covering exactly the PART 10 list:
1–6: generic `work`/`technical`/`prior`/`testing`/`using`/`decisions` alone never become evidence (each verified against the literal PASS 3 regression text: *"Prior work involved testing technical decisions using legacy systems."*).
7: a real contextual sentence (*"Designed and operated Kafka-based event processing pipelines."*) produces meaningful evidence.
8: employment-description evidence outranks a same-term generic skill occurrence.
9: skill + employment-description corroboration produces one evidence item, not two.
10: certification produces strong evidence.
11: About text never becomes ranking evidence.
12: self-reported years in About stay labeled unverified, never promoted to a matched signal.
13: an active seniority concern remains fully visible alongside strong Harvest evidence.
14: Harvest failure leaves CrustData evidence fully intact.
(15, "existing CrustData behavior unchanged," is covered by the full pre-existing suite passing unmodified — see below.)

All tests use generic JD phrasing and generic candidate text — no role-specific branching, satisfying PART 9's generalization requirement directly (the same six-word regression list that broke the Product Manager role is tested with a Backend Engineer JD sentence, proving the mechanism, not a PM-only patch).

**Result:** 181 backend tests passing (167 pre-existing + 14 new), only **one** pre-existing test's assertion changed (`test_a_term_found_in_both_crustdata_and_harvest_produces_only_one_matched_signal` — updated from "headline wins" to "employment description wins," the deliberate PART 7 strength-first change, documented inline in the test).

## F. Build/typecheck status

- `pytest tests/ -q`: **181 passed.**
- `npx tsc -b`: clean.
- `npm run build`: clean (bundle size effectively unchanged — this was a backend-only fix; the only frontend change is two new optional fields on the `MatchedSignalOut` TS type, unused by any rendering path).

## G. PASS 3 vs PASS 4 comparison

Re-ran the exact same 3 roles (Epiq Senior AI Platform Engineer, Senior Backend/Platform Engineer, Senior Product Manager) through the identical driver script. **Caveat:** this is a fresh live CrustData search each time, not a replay of the same candidate pool — CrustData returned a different (though similarly-sized) candidate set on the second run, so this is *not* a byte-for-byte "same 15 candidates, did their evidence change" diff. The comparison below is about evidence-quality *behavior*, not literal candidate-by-candidate rank deltas.

| # | Metric | PASS 3 | PASS 4 |
|---|---|---|---|
| 1 | Harvest-sourced matched signals (top-5 × 3 roles) | 46 | 65 |
| 2 | Meaningful Harvest evidence items | 22 | **65** |
| 3 | Generic/noise Harvest evidence items (bare `work`/`prior`/`testing`/`technical`/`using`/`decisions`/`consumer`/`engineers`) | 24 | **0** |
| 4 | Candidates affected (Harvest attempted) | 15 | 15 |
| 5 | Harvest success rate | 15/15 | 15/15 |
| 6 | Candidates whose ranking position changed (top-5 slice) | 14/15 | 10/15 (4/5, 3/5, 3/5 per role) |
| 7 | Candidates with an active seniority concern in final top-5 | 3 | 4 |
| 8 | Product Manager evidence quality | Mostly single generic words (`work`, `prior`, `testing`, `technical`, `using`) | Full contextual sentences quoting real product work (see below) |
| 9 | Total Harvest cost | $0.096 | $0.096 (identical — same top-N=5 × 3 roles, same $0.0064/lookup) |
| 10 | Average enrichment latency | 5,765 ms | 6,573 ms (both well within normal API variance) |

**Metric 3 is the headline result: generic-noise evidence went from 24 items (26% of all Harvest-sourced matches in PASS 3) to zero.** No generic word became a strong-evidence bullet in any of the 15 candidates across all 3 roles.

**Direct before/after example — Senior Product Manager role, PASS 3 (previous run):**
> "Senior Product Manager, Frame.io at Adobe — work described there includes 'work'."
> "Product Owner at Elephant — work described there includes 'technical'."

**PASS 4 (this run), same role, same evidence pipeline, real candidates:**
> "Senior Product Manager at Sedex — 'Led the end-to-end product lifecycle — from strategy and roadmap to launch and optimisation — aligning technical delivery with user needs and measurable business outcomes.'"
> "Technical Product Manager at QYOSS - Rajkot — 'Implemented Agile framework, reducing feature release cycle from 6 weeks to 3 weeks.'"
> "Associate Program Manager at Moglix India Pvt. Ltd. — 'Define and track key product metrics (KPIs) to measure feature success and inform data-driven product decisions.'"

Every one of the 25 strong-evidence bullets across the PASS 4 Product Manager top-5 is now a real, verifiable, sourced sentence. Zero are bare matched words.

**Concern visibility, confirmed live:** 4 of 5 final-top-5 Product Manager candidates (Anup Kumar, Claudia Villatoro, Vibhas Bhardwaj, Ritu Rajput) carry an active `"seniority level does not match target"` concern, and every one of them shows it in full, unmodified, directly alongside several strong contextual evidence bullets — exactly the side-by-side "tension stays visible" behavior PART 8 required. Ranking itself still doesn't discount for it (unchanged, per PART 11 — out of scope for this pass).

**Did evidence quality improve without changing ranking logic?** Yes. `CandidateRanker._calculate_score()` is byte-for-byte unchanged; the score shift visible in the re-run is entirely a consequence of *which* matched signals the (now-correct) evidence layer produces as input — fixing bad input, not retuning the formula, exactly as scoped.

## H. Remaining weaknesses / next-step recommendation

- **Single-letter/slash acronyms don't survive tokenization.** "A/B testing" tokenizes as `A`, `B`, `testing` — since `A`/`B` are single characters, neither counts as a "significant neighbor," so `testing` (a phrase-only word) never gets rescued and the phrase is silently discarded. A real "A/B testing" JD requirement currently produces zero signal from that specific wording (though `analytics`, `experiments`, and other same-sentence words nearby still work fine, and a Harvest description containing "A/B testing" would still be picked up by other unrelated signals). Low-frequency edge case; a targeted tokenizer fix (treating `A/B`-shaped tokens as one unit) would close it cheaply if it recurs.
- **Reranking still doesn't discount for an active concern** (unchanged from PASS 3, out of scope here) — 4 Product Manager candidates with a real seniority mismatch remain in the final top-5, now with visibly *better* evidence supporting their rank, which if anything makes the concern easier to overlook at a glance even though it is never hidden. This is the same open item flagged at the end of PASS 3, still unresolved by design (PART 11 explicitly forbade touching it this pass).
- **The live PASS 3 vs PASS 4 comparison used two different candidate pools** (live CrustData search, not deterministic) — the ranking-position-changed numbers (14/15 vs 10/15) are not a controlled A/B on identical candidates and shouldn't be read as "PASS 4 caused less reordering." The clean, controlled comparison is the noise-elimination metric (24 → 0), which is architecture-level and pool-independent.
- **Recommendation:** before any further Harvest/evidence work, this seems like a natural point to let the concern-vs-evidence tension (H, above) be a deliberate product decision rather than an accumulating side note — e.g., should a recruiter-facing UI surface concerns more prominently when they coexist with a high score, even without touching the ranking formula itself? That's a product call, not an engineering one, and is a reasonable next thing to bring to the user rather than default into.

---

**Files changed (6, no ranking/UI-rendering files touched):**
`backend/models/candidate_evidence.py`, `backend/models/match_explanation.py`, `backend/services/candidate_evidence_builder.py`, `backend/services/match_explainer.py`, `frontend/src/types.ts`, `tests/test_candidate_evidence_builder.py`.
