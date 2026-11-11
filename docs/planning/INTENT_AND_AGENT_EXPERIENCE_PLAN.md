# From Job-Form to Recruiter-Reasoning: Intent Capture + Agent Experience — Plan

**Status:** DRAFT for recruiter review. No code written. No experiment spend. Grounded throughout in the live NCS · AI Data Engineer · Pune search (`search_id=1e8513b3`, 2026-10-27), which returned 14 candidates of whom **0 evidenced any AI/RAG work**.

> This is a design to react to, not a finished spec. Drag things around, strike what's wrong, add what's missing.

---

## 1. The problem, stated plainly

The platform today behaves like a form: upload a JD → it extracts a title + a flat list of skills → it searches generic terms → it returns a grid of profiles with no visible reasoning. On the NCS role this produced 14 competent data engineers and **not one** with the AI/RAG experience that defines the job, because:

1. **The distinctive requirement never shaped the search.** "RAG / agentic AI" was captured as *optional* (supporting/differentiator), so the query sent to CrustData never asked for it. You cannot rank in someone who was never retrieved. *(Proven: re-scoring the 14 with AI as a must-have drops all 14.)*
   - **Root cause, confirmed against the live NCS records (search + intake session + confirmation):**
     - The **real NL query** sent to CrustData was: *"Looking for a mid-level AI Data Engineer with 5–8 years… proficient in Python, SQL, and Apache Spark, capable of designing and managing data pipelines."* — **RAG/agentic/LLM appear nowhere**; "AI" survives only as a title adjective. The query asked only for generic data engineering.
     - RAG was classified `supporting`, `ai_focus` was all-`false` (not even flagged despite the JD saying "RAG for agentic AI"), and `ranking.must_have` was `[]`.
     - The only channel from intent to candidates is the natural-language sentence (built from `core/supporting/differentiator_signals`); `ai_focus` and `ranking.must_have` are populated by nothing useful here **and read by nothing anywhere** — doubly dead.
     - Mechanism = **omission + mis-tiering**: the intake LLM left the defining capability out of the query and tiered it as optional. *(The `"{x} is a plus but not required"` phrasing in [search_translator.py:150](backend/services/search_translator.py#L150) is the **fallback** builder, used only if the LLM returns no query — it did not fire on NCS, but it confirms the same de-emphasis philosophy.)*
     - Corroboration: the #1 candidate scored 9.75 with `supporting_coverage = 0.0` and `differentiator_coverage = 0.0` — top of the list with zero AI evidence.
2. **The recruiter never got to set what matters.** The stored confirmation held only a title + "candidate identity" — not the requirements, and not which are must-have vs nice-to-have.
3. **Intake thinks in one dimension.** It extracts literal skills; it does not reason the way a recruiter does — about *what work proves fit*, about *several valid candidate shapes*, and about *career trajectory*.
4. **The experience is a black box.** Nothing shows what was understood, what is being searched, or why a given profile appears.

---

## 2. Design principles (how a recruiter actually reasons)

These are the pillars. Everything below serves them.

- **P1 — Capability over title.** Fit is demonstrated work, read from skills and project text, not a literal title match. "AI Data Engineer" ≈ *has shipped RAG/agentic pipelines*, regardless of title wording.
- **P2 — A role is several valid profiles, not one.** Intake frames 2–4 **archetypes** (candidate shapes) per role, searched and evaluated in parallel, then unioned — the way a recruiter runs several searches for the same req.
- **P3 — Trajectory is a signal.** Reason over career *paths*, not just the current snapshot (e.g. "AI Software Engineer" = AI now + software-engineering past). Current-vs-past matters.
- **P4 — The recruiter sets the bar.** Must-have vs nice-to-have is the recruiter's call, expressed in plain language, and must-haves are about *demonstrated capability*, not titles.
- **P5 — Recall-first retrieve, evidence-first judge.** Cast wide on capability; decide on quoted evidence. (The engine already leans this way — no title hard-gate, Judge scores on evidence.)
- **P6 — Transparency is the product.** Show what was understood, what is being searched, and why each candidate surfaced. This *is* the "AI assistant" feel — not a chatbot skin.
- **P7 — Consult, don't assume.** Intake is a knowledgeable partner, not a parser. It asks, guides, and validates the hiring intent — surfacing distinctions a recruiter may not have considered (e.g. AI Engineer vs Data Scientist vs ML Engineer: overlapping words, different talent pools) — and never silently assumes which the recruiter meant. Every inference the role turns on is put to the recruiter to confirm or correct.

---

## 3. The mechanism — four stages

Legend: ✅ exists · ⚙️ extend existing · 🆕 new.

### Stage 1 — Understand the JD as a recruiter would (any size)
From the JD + recruiter notes, produce a **Role Understanding**:
- ✅ Clean signal extraction already works (it parsed the messy 1,511-char NCS JD correctly).
- 🆕 **Archetypes**: 2–4 candidate shapes, each with its own must/nice signals and *recognition cues* (how to spot the capability from skills/project text, not title).
- 🆕 **Recognition cues per capability**: e.g. AI/RAG → {RAG, retrieval-augmented, agentic, LLM, vector DB, embeddings, LangChain/LlamaIndex, "knowledge base"}. This is what lets P1 work.
- 🆕 **Trajectory rules**: which signals are "current" vs "ever" (e.g. AI = recent/current; software-engineering = ever).

*NCS example output:*
- Archetype A — **Data Engineer who has built AI/RAG pipelines.** Must: AI/RAG capability (cues above) · production batch/streaming pipelines · 5–8 yrs. Nice: Spark, Python, SQL, cloud security.
- Archetype B — **ML/AI engineer who runs production data pipelines.** Must: AI/RAG capability · pipeline ownership. Nice: same.
- Note that Python/SQL/Spark are **table stakes (nice-to-have)**, not what differentiates — the inversion that broke this search.

### Stage 2 — Recruiter reviews and reshapes (the conversation)
- 🆕 **Clarify before confirming (P7).** Where the JD is ambiguous on something the role turns on, intake raises it as a short, guided question rather than guessing — and teaches the distinction so the recruiter decides well.
  - *NCS example:* "This JD mixes RAG/agentic-AI delivery with classic data-pipeline work. Are you after an engineer who *ships AI systems in production* (AI/ML Engineer lineage), or someone who *builds and analyses models* (Data Science lineage)? They're largely different talent pools — I'll search very differently." The recruiter's answer picks/weights the archetypes; it is never assumed.
- 🆕 Present the Role Understanding as an **editable requirement card**, in plain language, grouped **Must-have / Nice-to-have**, per archetype.
- 🆕 Recruiter can: move a signal between must/nice, add/remove a signal, add/remove an archetype, edit recognition cues ("also count Bedrock Agents"), confirm.
- ⚙️ The confirmation snapshot must now carry **the requirements and their tiers** (today it stores only title + identity + hash). This is the single most important wiring change.
- **The go-ahead gate:** nothing searches until the recruiter approves. This is also where the "I don't understand what it's doing" feeling dies.

### Stage 3 — Search the way a recruiter searches manually
- ⚙️ **Must-haves drive the query, not just scoring.** A must-have capability becomes a retrieval term (its recognition cues OR'd across description/headline/skill text) so the pool actually contains those people. *(The engine already supports keyword leaves across these free-text fields — verified.)*
- 🆕 **One query per archetype/path**, unioned and deduped — mirroring how you run several searches for one req. (Extends today's two-query planner.)
- ✅ **No title hard-gate** stays — capability, not label (P1).
- ⚙️ **Depth policy**: if the first page is thin on must-have matches, pull the next page before admitting, instead of one-and-done. (NCS stopped at one page of 50; a cursor was available and unused.)
- ⚙️ **Honest counts**: show must-have matches found, not the 202M index size.

### Stage 4 — Results that explain themselves
- ✅ Per-candidate evidence (met/partly/not-evidenced with exact quotes) already exists — today it's hidden in diagnostics.
- 🆕 Surface it: every candidate card leads with *why they're here and what's missing* ("Built a RAG pipeline at X · 6 yrs · no Spark listed"), tagged to the archetype they matched.
- 🆕 Agent-style narration of state: "Read the JD → 3 must-haves → searching for RAG/agentic engineers → found N, reviewing…"

---

## 4. Worked before/after — NCS AI Data Engineer

| | Today | With this plan |
|---|---|---|
| Distinctive requirement | AI/RAG = optional | AI/RAG = must-have (recruiter-set), with recognition cues |
| Query to CrustData | generic "data engineer / Python / SQL / Spark" | capability terms incl. RAG/agentic/LLM/vector-DB, per archetype |
| Pool | 50 generic DEs, 0 with AI | engineers whose work shows AI, unioned across 2 archetypes |
| Shortlist | 14, none fit the AI core | fewer but *right*; each shown with its AI evidence |
| Recruiter control | title + identity only | must/nice + archetypes + cues, approved before search |
| Feel | upload → random grid | understood → confirm → searching → here's who & why |

---

## 5. Staging (so it can ship in pieces)

**Phase 0 — CrustData hybrid location leak (found 2026-10-27; root-cause CORRECTED after exhaustive isolation).** The leak is NOT caused by negative filter operators (that was a red herring — the production query was simply weak). In `mode:"hybrid"`, when the NL `search.query` is **generic AND does not name the location**, CrustData returns top global semantic matches and the hard filters (location included) stop binding → ~22M, out-of-country results. A **specific** query OR one that **names the location** makes every filter bind, exclusions and all. Proven: identical filters (incl. all 26 exclusions + company `not_in` + geo), only the query varied — generic/no-location leaked; +"based in Pune" or a specific RAG query → clean; geo/order/nesting changes had no effect.
- **Phase 0 collapses into Phase 1:** the strong, location-anchored query that Phase 1 produces *is* the fix. No filter surgery, no client-side exclusion rework, no over-fetch, no removal of negatives needed.
- *Belt-and-suspenders:* always inject the confirmed location (city/state) into the NL query text; keep the existing client-side geo safety net as a final guard (the CrustData relax-threshold is heuristic).
- *Evidence:* live isolation probes; no Harvest/Judge. See memory [[crustdata-negative-operator-location-bug]] and `PHASE_0_1_IMPLEMENTATION_SPEC.md`.

**Phase 1 — Fix the upstream intent so it surfaces the right candidates (no new spend, biggest quality win; also fixes Phase 0).** Two precise moves, both upstream:
- **1a. Capture priority correctly (intake reasoning).** The role's *defining* capability belongs in `core_signals` (the lead of the NL query), not in supporting/differentiator. For an "AI X" role the AI capability is the core discovery signal, not "a plus." This is an intake-reasoning/prompt fix, and it is where "consult, don't assume" (P7) lives — the agent proposes the priority and the recruiter confirms it.
- **1b. Stop throwing the priority away (close the dead wiring).** A captured must-have must actually drive retrieval: (i) lead the NL query sentence, and (ii) ideally become a real retrieval term. Today `ai_focus` and `ranking.must_have` are written but read by nothing, and differentiators are phrased as "a plus but not required." Either populate `core_signals` from the recruiter-confirmed must-haves, or wire `ranking.must_have`/`ai_focus` into the query builder — and remove the "plus but not required" de-prioritization for confirmed must-haves.

This pair alone would have fixed the NCS search. Archetypes/per-archetype queries (Stage 3) are a later enhancement *within* this phase, not a prerequisite.

**Phase 2 — Intake reasoning upgrade:** archetypes + recognition cues + trajectory (Stage 1). Touches the intake model prompt; validate against a couple of real JDs before/after (no live retrieval needed to test extraction).

**Phase 3 — Agent experience:** the requirement card, the must/nice controls, evidence-first candidate cards, state narration (Stages 2 & 4 UI). This is the "assistant feel" rebuild of the current webby flow.

Phases 1 and 3 are independent — the UX can start in parallel. Nothing here requires a paid A/B experiment.

---

## 6. Second step — the Code-Mode strategy sandbox

Confirmed shape: a **Code-Mode-style exploration space** that is a **hybrid of (a) pre-search planning and (b) parallel sampling**. The platform doesn't commit to one reading of the role; it drafts several *strategies*, runs each as a small live probe, and lets the recruiter compare real samples before launching the full search.

This is distinct from archetypes, and it has prior art in the repo:
- **Archetypes (Phase 1–2)** = several candidate shapes *within one agreed interpretation*.
- **Sandbox (this step)** = *competing interpretations/strategies* explored side by side (the "AI Engineer" reading vs the "Data Scientist" reading), each expressed as executable retrieval logic.
- **Prior art:** the existing `live_retrieval_ab` harness already runs two strategies and compares them, and the Crustdata **Code Mode** surface (`execute({code})` driving `callTool`) already lets a strategy be written as a short script rather than a fixed call. The sandbox productizes that A/B harness into a recruiter-facing, agent-authored loop.

**How it would work (a + b hybrid):**
1. From the agreed intent, the agent **drafts 2–3 strategies** as Code-Mode scripts — e.g. S1 = capability-first (RAG/agentic cues across skills+description), S2 = trajectory-first (AI-now + eng-past), S3 = title+skill blend. *(pre-search / planning = the (a) half)*
2. Each strategy runs a **bounded sample probe** in parallel (e.g. top ~10 each), returning real candidates with evidence. *(parallel-run = the (b) half)*
3. The recruiter sees the samples **side by side** — who each strategy surfaces and why — and picks one, merges, or edits a strategy.
4. The chosen strategy **commits** into the Phase-1 full-search path (same query builder, now driven by the winning script).

**Design implications / guardrails (resolve before build):**
- **Spend:** sample probes make live CrustData calls and cost credits. Must be bounded (small sample, capped number of strategies) and run **only on the recruiter's go** — never automatically. This is a *runtime product feature*, not an offline experiment, but it does spend; budget must be explicit and shown.
- **Safety of "code":** agent-authored strategies must be reviewable and constrained to the provider tool surface (the Code Mode MCP already sandboxes `execute` to `callTool`), not free-form execution against production.
- **Scoring:** how samples are compared (coverage of must-haves? evidence strength? overlap between strategies?) needs a fixed, honest rubric so the comparison isn't vibes.
- **Sequencing:** this is strictly after Phase 1 — it *reuses* the Phase-1 query path as its commit target, so Phase 1 must exist first.

---

## 7. Decisions needed from you

1. **Where to start** — ✅ **Phase 1 (fix what it returns) first** — confirmed by recruiter.
2. **Archetypes per role** — cap at 3? Let intake propose and you prune?
3. **Must-have strictness** — hard-drop a candidate who misses a must-have capability, or show them flagged at the bottom ("missing: AI")? (Hard-drop is cleaner but risks false negatives when the capability is real but unstated.) *Recruiter flagged: defer this until the consultative-intake behavior (P7) is settled.*
4. **Trajectory defaults** — is "AI current + any engineering past" the right default shape for AI-* roles, or set per role?
5. **Sandbox shape** — ✅ Code-Mode hybrid of pre-search planning + parallel sampling (see §6). Open sub-decisions there: sample-probe credit budget, strategy-comparison rubric.
