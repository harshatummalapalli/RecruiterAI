# Dual-Source & Exemplar Intake — Design Note

**Status:** A — APPROVED to build (decisions locked 2026-11-12). B — approved, sequenced after A.
**Author:** drafted 2026-11-12.
**Scope:** How a role's *intent* is assembled at intake. Two new input paths (A: JD × HM/client brief reconciliation; B: exemplar-seeded "someone like this person"), converging on one recruiter-validated `RoleModel` before any CrustData spend.

## 0. Decisions (locked 2026-11-12)

- **All inputs are optional; at least one source is required.** The recruiter must never be forced to supply all three (JD, HM brief, exemplar). The module runs on any non-empty subset — "remove friction." JD is no longer mandatory.
- **A1 — tiering:** HM-only → **core**; JD-only → **non-core** (recruiter can override either).
- **A2 — single-source parity:** No HM brief ⇒ behaviour is **byte-identical to today**. The diff's degenerate case.
- **A3 — conflicts:** resolved **inline** on the brief screen (either/or rows), no separate step.
- **B1 — exemplar can stand alone** (no JD needed) as well as enrich a JD.
- **B2 — one exemplar in v1**, extractor architected so *several* (intersection) is a clean later extension. (Owner unsure → start simple, keep the door open.)
- **B3 — two exemplar forms, no file upload:** a **LinkedIn URL** (enriched via existing API, one gated call) or **pasted profile/resume text** (parsed directly, no enrichment call, zero credits). No upload widget.

---

## 1. Why

Many recruiters don't know *how* to translate a role into a search — they lean entirely on the published JD. But a published JD is the weakest signal we collect: HR-sanitized, over-stuffed, often copy-pasted boilerplate. The real intent surfaces in two places the system ignores today:

1. **The HM/client conversation** — "we actually need someone who's shipped payments infra," which the JD never says.
2. **An exemplar** — "get me another Sachin," handed over as a resume or a LinkedIn URL.

Today intake takes a **single** `raw_input` string + a posted title and AI-derives everything:

```
IntakeAgent.read(notes, posted_title) -> Understanding
IntakeAgent.assemble(understanding, boundary, answers) -> RoleModel   # RoleModel.requirements[], capability_groups[]
```

There is no reconciliation of multiple sources and no exemplar path. This note adds both **without touching the downstream engine** — briefing → search → ranking all consume the same `RoleModel` they do now. The change is entirely *upstream of* `assemble_role_model`.

---

## 2. Principles (non-negotiable)

- **Propose, never decide silently.** This module's only job is to produce a *candidate* intent and get the recruiter to confirm it. No source — JD, HM brief, or exemplar — is authoritative on its own.
- **Zero CrustData spend until the recruiter approves the intent.** All reconciliation is reasoning over text/enrichment we already hold. Exemplar enrichment (B) is one bounded call, gated behind an explicit recruiter action.
- **One output, unchanged.** The module emits exactly today's `RoleModel` + `SearchBoundary`. Nothing downstream learns it came from multiple sources.
- **Conflicts are shown, not averaged.** When sources disagree, the recruiter arbitrates. Averaging two sources is just a new way to be wrong.

---

## 3. Part A — Dual-source intent (JD × HM/client brief)

### Inputs
- **Published JD** (optional) — today's `raw_input`.
- **HM/client brief** (optional) — free text: call notes, an email, a Slack paste.

At least one source overall (JD, HM brief, or exemplar) must be present; none is individually mandatory.

### Flow
1. Read each source **independently** into its own `Understanding` (reuse the existing reader; no new model).
2. **Diff** the two understandings into three buckets:
   - **Agree** — present in both → high-confidence core.
   - **JD-only** — in the JD, absent from the HM brief → likely boilerplate; propose as *lower* tier.
   - **HM-only** — the HM surfaced it, the JD didn't → the real nuance; propose as *core*, flagged "from the HM conversation."
3. Present the diff as the validation screen. Each row is a requirement with its source badge and a tier the recruiter can override. Conflicts (JD says "5+ yrs", HM says "seniority flexible") render as an explicit either/or the recruiter resolves.
4. On confirm → feed the reconciled set into `assemble_role_model` as today.

### Why this shape
- The **diff itself is a coaching artifact** — a junior recruiter sees "the JD said X but the HM emphasized Y, weighted as core." Builds trust and teaches the search.
- Reuses the existing reader and `RoleModel`; the new surface is the *reconciliation*, not a second understanding engine (we have had too many of those — see `architecture-audit-full`).

### Decisions — see §0 (A1 HM-only→core / JD-only→non-core; A2 single-source = byte-identical; A3 inline conflict resolution).

---

## 4. Part B — Exemplar-seeded ("someone like this person")

### Input
- A **LinkedIn URL** (enriched via existing API) or **pasted profile/resume text** (parsed directly, no enrichment call). Optional; may stand alone (no JD) or enrich one. No file upload. One exemplar in v1.

### Flow
1. Enrich the exemplar → a profile (CrustData/Harvest plumbing already exists). **One bounded call, recruiter-triggered**, credit-gated.
2. **Extract the capability arc — drop the incidental.** From the profile, derive *what makes them a fit* (the progression, the kind of work, proven capabilities) and explicitly **discard** the incidental facts (their current employer, their city, their exact tenure, their bootcamp).
3. Propose a `RoleModel` from the arc, shown as: **"Matching on: A, B, C — NOT on their current company or location."** The recruiter confirms or edits each.
4. On confirm → same `assemble_role_model` path.

### The one real risk — overfitting to a human
An exemplar encodes dozens of facts that aren't the hiring intent. Taken literally it tanks recall by matching one person instead of a role — **we have already hit this exact failure** (`capability-memory-carryover-bug`: a learned capability forced as a hard core req cut a search to 8/47). So the design is built around *subtraction*:
- The extraction step's output is reviewed as "keep / drop" per attribute, defaulting incidental facts to **drop**.
- Nothing from the exemplar becomes a **hard** requirement without explicit recruiter promotion.
- The exemplar seeds *capability groups* (interchangeable surface terms), not literal company/title filters.

### Decisions — see §0 (B1 stands alone or enriches; B2 one in v1, intersection later; B3 LinkedIn URL + pasted text, no upload).

Because the exemplar can stand alone, the subtraction discipline must be airtight: with no JD to anchor the role, nothing incidental from the profile can be allowed to leak in as a hard requirement.

---

## 5. What this touches

| Layer | Change |
|---|---|
| Intake UI | New optional inputs (HM brief textarea; exemplar URL/paste) + one reconciliation/validation screen. |
| `recruiter/agents/intake/` | A reconciliation step **before** `assemble_role_model`; an exemplar→arc extractor. The reader and `RoleModel` are reused unchanged. |
| Engine (briefing/search/ranking) | **None.** Consumes the same `RoleModel` + `SearchBoundary`. |
| CrustData | B adds **one** recruiter-gated enrichment call. A adds zero. |

This is deliberately upstream-only: the risky seam has historically been intake, so we isolate the change there and leave the proven downstream path alone.

---

## 6. Recommended sequencing

1. **A first** — highest leverage, zero new external dependency, pure reasoning over text we already collect. Ships as its own validated increment.
2. **B second** — needs the subtraction design and one paid enrichment validation; deserves a focused pass once A's reconciliation UX is proven.

Each ships independently; neither blocks the other.

---

## 7. Before I write code, I need from you

- A1–A3 and B1–B3 above.
- Confirmation that "propose + validate, zero spend until approved" is the right contract (it's the spine of the whole design).
- Whether A is a standalone deploy or batched with the three features already queued (Harvest URL, Open-to-Work chip, Current/Ever toggle — committed, not yet deployed).
