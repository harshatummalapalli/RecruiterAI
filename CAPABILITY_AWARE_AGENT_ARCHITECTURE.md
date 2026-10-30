# Capability-Aware Sourcing Agent — Architecture

**Written for:** the product owner + the implementer. A scope/design to react to, not a finished spec. **No credits spent writing this.**

The goal: a sourcing assistant that **understands** the hiring intent, **validates** it with the recruiter, **maps** every constraint honestly against what CrustData can actually do, then **activates** the search — and that **learns** over time, both about CrustData and about each recruiter. This replaces the "dumb form → random profiles" experience with a professional assistant.

---

## 0. What "intelligence" means here (honest framing)

This is **not** one magic LLM that "just knows," and it is **not** AGI. It is an engineered, adaptive system where intelligence comes from four cooperating parts:

1. **Understanding** — an LLM that reads the JD / recruiter input into a structured, correctly-framed intent.
2. **Knowledge** — a *structured, tested* model of CrustData (not LLM memory): every field, operator, what's a hard filter vs soft ranking vs impossible, cost, and the quirks we found the hard way.
3. **Memory** — per-recruiter / per-company history and revealed preferences, persistent across time.
4. **Human validation** — the recruiter confirms the plan. This is the *reliability mechanism*: the LLM can mis-frame, so the agent **proposes and the human locks it**, rather than guessing silently.

The value is the *architecture and the feedback loops*, not the LLM being perfect. Setting that expectation now is what keeps this from over-promising.

---

## 1. Core architecture — the capability-aware pipeline

```
JD / recruiter input
   └─ (A) CrustData Capability Model  ← structured, tested source of truth
   └─ (B) Intent Understanding (LLM)  → structured, framed hiring intent
   └─ (C) Capability Mapping (deterministic) → hard / soft / evidence / can't-do + cost
   └─ (D) Consultative Confirmation (P7) → recruiter sees & locks the plan
   └─ (E) Activate & Retrieve → mapped, confirmed search → evidence-first results
```

**(A) CrustData Capability Model — the "knows CrustData in and out" part.**
A machine-readable spec (data, not prose) of every capability: fields (`current.company_name`, any-time `company_name`, `description`/`headline` keyword, …), operators (`in`, `not_in`, `(.)` whole-word, `(!)`, `geo_distance`), each tagged **hard-filter / soft-signal / unavailable**, with **cost** (0.03/result) and **known quirks** (a weak/location-less query makes hard filters leak; `(.)` is whole-word; skills-list unavailable; work_mode unfilterable). The agent *reasons against this*, so mapping is reliable and testable — never guessed.
*Reuses:* our verified-capabilities knowledge + `capability_mapper.py` + the dormant `search_compiler.py` (which already compiles intent → a capability-aware CrustData filter tree with provenance — an early version of exactly this engine, just not wired to production).

**(B) Intent Understanding.** JD + recruiter input → a structured intent that is **framed correctly** (an "AI X" role is AI-centric; capabilities carry a stable tier; the defining capability lands in *core*, not "optional"). This is the intake-reframing work — now with a purpose: it must produce something that *maps onto real CrustData capabilities*.

**(C) Capability Mapping.** Deterministic: each intent element → **hard filter** / **soft ranking** / **downstream evidence (Judge)** / **can't be done**, plus an **estimated cost** (results × 0.03) and **scope tightness**. Anything unmappable is surfaced, never dropped.

**(D) Consultative Confirmation.** The agent shows the recruiter, in plain language: *"I'll hard-filter on location, experience, and company; I'll enforce RAG as a keyword (you asked); I'll rank on the rest; I can't filter work mode. This is a tight scope (~N in pool), ~1.5 credits."* Where the role is ambiguous (AI Engineer vs Data Scientist), it **asks**. The recruiter adjusts and locks. → This is "no silent drops" + "consult, don't assume," built into the architecture.

**(E) Activate & Retrieve.** Run the agreed, mapped search. Because the scope is tight and correct, a 50-pull returns the *right* people; the credit meter shows the spend.

---

## 2. Add-on layer 1 — CrustData capability learning (drift detection)

**Doable, with an honest mechanism.** CrustData does **not** notify us of changes, so the agent "learns" by **testing**, not by magic self-rewriting:
- **Pin the API version** (already `x-api-version: 2025-11-01`), so changes are opt-in, not surprise.
- A **scheduled capability-verification suite** (the same probe style we used all session) periodically re-asserts each capability in model (A): does `not_in` still work? is `(.)` still whole-word? did cost change? did a field stop discriminating?
- On a mismatch, it **flags the drift for a validated update** — it does **not** blindly rewrite its own rules. (Silent auto-adaptation on a mis-detected change could quietly break every search; detect-and-flag is the safe design.)
- **Bounded cost:** the suite spends a few credits per run; it runs on a schedule the recruiter-admin approves, and the result is visible (like the meter).

So: the capability model stays current *and trustworthy*, because every change is tested and reviewed, not assumed.

---

## 3. Add-on layer 2 — recruiter & company memory (personalization)

**Doable and a genuine differentiator.** A persistent, per-recruiter + per-company profile that the agent reads at intake and writes after each search:
- **What it remembers:** past confirmed briefs, search outcomes, and — the real signal — **shortlist/reject decisions** (the product already captures `recruiter_decisions`). From these it derives **revealed preferences** (Recruiter 1 @ Epiq → Software Engineers of a certain flavor; Recruiter 2 @ NCS → juggling varied role combinations).
- **What it does with it:** on return (even a year later), propose a starting frame — *"Last time you searched SWE at Epiq you wanted backend-heavy, no managers — same flavor?"*; calibrate ranking to what they've actually shortlisted before; speed up repeat searches; carry company-level context across recruiters.
- **Identity:** now possible — the session already carries the login email (added for the credit meter), so searches can be attributed to a person and a company.

**Honest design care (this is where it's easy to get wrong):**
- **Remember patterns, not raw everything.** Store preferences, outcomes, and derived signals — not an indiscriminate dump. "Memory of everything forever" is a storage + privacy liability; "memory of what matters" is the valuable, lasting thing.
- **Isolation & privacy:** per-recruiter and per-company data separation; a clear policy on storing candidate PII (who was viewed/shortlisted) — retention, access, and the recruiter's own data rights.
- **Learning is a suggestion, not a cage:** revealed preferences *propose*; the recruiter can always override. A recruiter whose needs change must never be trapped by last year's pattern.

---

## 4. What exists vs what's new

| Layer | Already in the repo | New to build |
|---|---|---|
| (A) Capability model | verified-capabilities knowledge; `capability_mapper.py`; dormant `search_compiler.py` | encode as ONE structured, tested spec the agent consults |
| (B) Intent understanding | `intake_reasoning.py`, confirmation snapshot | reframing + stable tiering (one paid validation) |
| (C) Capability mapping | `capability_mapper.py`, compiler's routing | honest hard/soft/can't + cost/tightness estimate |
| (D) Consultative confirm | confirmation step (the seam) | the plain-language plan + ambiguity questions (UI) |
| (E) Activate/retrieve | the whole production pipeline (now location-correct) | minor tuning |
| Add-on 1 (drift) | our probe harness style | scheduled capability-verification + flag |
| Add-on 2 (memory) | `recruiter_decisions`, session email | per-recruiter/company profile store + preference derivation |

Most of the *core* is assembling and sharpening pieces that already exist; the genuinely new, high-value work is the **structured capability model**, the **intake reframing**, and the **two learning layers**.

---

## 5. Honest caveats & risks

- **LLM mis-framing** → mitigated by (D) the human confirm. Non-negotiable; it's the reliability mechanism.
- **Drift auto-adaptation is risky** → detect-and-flag + validated update, never blind self-modification.
- **Memory = privacy surface** → needs multi-tenant isolation + a PII/retention policy before it stores candidate data.
- **"Super intelligent" expectation** → it's a strong *engineered* assistant with memory and feedback loops. Honest, consultative, and improving — not omniscient. Pitch it that way.
- **Cost** → intake validation (one-off) + drift probes (scheduled) spend credits; both bounded and approved; the meter makes all of it visible.

---

## 6. Sequencing (so it ships in value-order, not all at once)

- **Phase A — Core capability-aware agent (A–E).** The foundation and the biggest immediate win: concrete intake, no silent drops, tight scope, assistant feel. Mostly wiring existing pieces + the capability model + intake reframing. **One small paid validation** (intake). → This alone makes the product work.
- **Phase B — Recruiter/company memory.** After the core works and identity/feedback are solid. The differentiator.
- **Phase C — CrustData drift-learning.** An ongoing ops layer, scheduled once the capability model is the single source of truth.

Rationale: A is the precondition for everything you want; B and C are force-multipliers that only make sense on a working core. Don't let the (exciting) learning layers block the foundation.

---

## 7. The decision

Build it as the real architecture, Phase A first. The only credit spend in Phase A is one bounded intake-validation run (on NCS + 1–2 other JDs), shown to you as a before/after shortlist before anything ships. Phases B and C carry their own small, approved budgets. **Nothing spends credits without explicit approval.**
