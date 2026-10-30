# Phase 0 + Phase 1 — Implementation Spec

**Written for:** the engineer implementing this (may be a future session). **Design only — no code here.** Grounded in the live NCS · AI Data Engineer · Pune investigation (2026-10-27).

> **Code baseline warning.** The deployed build is SHA `b3f48157`, which is **ahead of / different from** this local checkout (`fbd5626`). The post-retrieval "geographic safety net" exists in the deployed code but NOT in this local branch. Implement against current `main`/deployed, and re-locate any line references below before editing.

---

## Phase 0 — Restore location (the blocker)

### What we proved (root cause CORRECTED 2026-10-27 after exhaustive isolation)
The location leak is **not** caused by negative filter operators. It is caused by a **weak natural-language hybrid query.** In `mode:"hybrid"`, when the `search.query` is generic *and* does not name the location, CrustData returns top global semantic matches and the hard `filters` (location included) effectively stop binding (returns ~22M, out-of-country candidates). Make the query **specific** (capability-rich) *or* have it **name the location** — either one — and every filter binds, exclusions and all.

Decisive isolation (identical filters incl. 26 `(!)` exclusions + `not_in` company + geo; only the query text varied):
- generic query, no location word → 22M, Chicago/Paris leak ✗
- generic query **+ "based in Pune, Maharashtra, India"** → 2.1M, all Pune ✓
- specific RAG query, no location word → 260K, all Pune ✓
- changing geo `10.0→10`, removing geo, re-ordering conditions, nesting negatives → **no effect** (all still leak with the generic query).
- All 26 `(!)` exclusions + `not_in` company + geo, with a specific/location-naming query → clean. **So the exclusions were never the problem.**

Earlier runs fit: production used a generic, location-less query → leaked; every "clean" probe happened to use a specific, Pune-naming query. The "negative-operator" theory was a red herring (the production query was simply weak).

### The fix: a strong, location-anchored hybrid query (this is Phase 1) — keep all structured filters
Because the trigger is the query, **Phase 0 collapses into Phase 1**. No filter surgery is required.
1. **Produce a specific, capability-rich NL query** (Phase 1, §below): the generic query caused *both* the bad candidates *and* the location leak — one root cause.
2. **Always inject the confirmed location into the NL query text** (city/state), e.g. append "based in {city}, {state}". Belt-and-suspenders that makes filters bind even if a query is otherwise weak. Add in `backend/services/search_translator.py` query assembly.
3. **Keep the structured filters as-is**, including the exec-title `(!)` and hiring-company `not_in` exclusions — they do not break location once the query is strong. **No client-side exclusion step, no over-fetch, no removal of negatives is required for the location bug.**
4. **Keep the existing client-side geo safety net** as a final defense-in-depth guard (the exact CrustData threshold for relaxing filters on a weak query is heuristic/uncharacterized, so a last-line location check stays cheap insurance).
5. **Never surface `total_count` as a real pool size** — noisy/unreliable (267K vs 2.1M vs 22M across near-identical filters). Report the actual result set.

### Decision for the recruiter (now INDEPENDENT of the location bug)
The 26 blanket executive-title exclusions no longer *need* to change for location to work. They remain **independently** worth narrowing — they hard-drop current `Director` / `Head of Data` / `Head of AI` who can be ideal senior candidates (readiness-audit gap #2). Optional, separate decision: narrow/drop them, or convert "not senior" to a soft NL steer. Not required for Phase 0.

### Phase 0 acceptance tests
- **Offline (no spend):** the assembled NL query for any role names the confirmed location and leads with the defining capability.
- **Live (one cheap probe/role):** with the strong, location-anchored query, location binds (zero out-of-country candidates in the top page) **even with the exclusions left in**.

---

## Phase 1 — Carry the defining capability into the query

### 1a — Intake must tier the defining capability as core (not optional)
In `backend/services/intake_reasoning.py` (Task B): the role's **defining** capability must land in `core_signals` and appear in the natural-language query. On NCS it was filed as `supporting` and omitted from the query; `ai_focus.rag/agentic_ai` were left `false` despite the JD. Fix the Task B prompt so that:
- the capability that distinguishes the role (e.g. "RAG / agentic AI" for an "AI X" role) is core, and
- the generated NL query leads with it, and **never** phrases a must-have as "a plus / not required";
- `ai_focus` flags are set when the JD states them.
Validate against intake gold (`backend/experiments/intake_strategy/gold_role3.py`) + add an NCS-shaped gold case. Extraction tests need no provider calls.

### 1b — Guarantee the must-have reaches the query (don't rely only on the LLM)
The NL query is LLM-authored, so 1a is necessary but not sufficient. Add a **deterministic safeguard** in `backend/services/search_translator.py` (`to_search_intent` / query assembly): prepend the recruiter-confirmed must-have capabilities to `natural_language_search_query`, and ensure no confirmed must-have is rendered with "a plus but not required" (that phrasing is in `_fallback_natural_language_query` L150 — keep it only for genuinely optional differentiators).
- Note: `SearchIntent.ai_focus` and `SearchIntent.ranking.must_have` are currently **dead** (written, read by nothing). Reviving them is optional; the minimal, lower-risk path is `core_signals` + the NL query. If revived, wire them in the query builder and cover with tests.

### P7 — Recruiter confirms the tiering
The recruiter must be able to confirm/flip must-have vs nice-to-have before search (the "consult, don't assume" step). The full requirement-card UI is Phase 3; an interim text confirmation of the core capability can ship with Phase 1.

### Phase 1 acceptance tests
- **Offline:** intake-gold asserts the defining capability is `core` and present in the NL query; a translator test asserts the confirmed must-have appears in the query and is never tagged "not required".
- **Live:** NCS → strong, location-anchored query (filters incl. exclusions left in) → tight Pune pool with AI engineers on top (demonstrated across probes, including a "Gen AI / Agentic AI Engineer").

---

## Sequencing & risks
- **Phase 0 and Phase 1 are now one change** — the strong, location-anchored query fixes both candidate quality and the location leak. Ship together.
- **Risks:** the CrustData threshold for relaxing filters on a weak query is heuristic/uncharacterized → mitigated by (a) always naming the location in the query and (b) keeping the client-side geo safety net. LLM query variance mitigated by the 1b deterministic safeguard (prepend must-have capability + location to the query).
- **No over-fetch / no client-side exclusion rework needed** for the location bug (earlier plan superseded).
- **Rollout:** offline tests → one cheap live probe per representative role → ship. CrustData support stays a fallback only if a strong, location-anchored query ever fails to bind location.

---

# Phase 2 — Archetype disambiguation, hard capability precision, and company scope

**Written for:** the implementer. This is the layer that answers "is the intake intelligent enough to tell a Java vs .NET engineer, a Data Engineer from a DevOps Engineer, a systems-heavy AI Engineer from a Data Scientist, and to exclude/include by company history?" Phase 0+1 make *stated* intent reach retrieval and bind location. Phase 2 adds the **disambiguation of ambiguous intent** and **recruiter-tunable precision**.

## 2.0 The core principle: soft by default, hard on request
CrustData has **no skills-list filter and no job-family classifier** — so role/skill criteria are *soft* (NL hybrid relevance + Judge) unless we deliberately make them hard. The bridge to *hard* is the **description/headline/summary keyword filter**, verified live (2026-10-01): whole-word `(.)`, discriminates (desc `Java` 29,193 vs `.NET` 9,449; `(.) "Java"` does NOT match "JavaScript"), filterable across `current/past/any-time description`, `basic_profile.summary`, `basic_profile.headline`. So **any capability can be either**:
- **soft** → a phrase in the NL hybrid query (recall-friendly, ranks, never excludes), or
- **hard** → a positive `(.)` keyword leaf OR'd across description/headline/summary (precise, whole-word, *excludes* non-matches).

The recruiter chooses per capability (must-have → hard; nice-to-have → soft). This is exactly how "Java not .NET", "DevOps not SWE", ".NET only" become *enforceable* instead of hopeful.

## 2.1 Archetypes — data model & extraction (intake)
Extend the intake output with a small set of **archetypes** (1–3) the role could map to. Each archetype:
```
{ label,                       # "Systems-heavy AI Engineer"
  representative_titles: [...], # -> positive title-expansion (.) on current.title
  must_have:   [ {term, hardness: hard|soft, scope: current|ever} ],
  nice_to_have:[ {term, ...} ],
  recognition_cues: [...],     # synonyms/keywords that evidence the capability
  trajectory: {...} }          # e.g. AI current + SWE ever (any-time fields)
```
- **Where:** `backend/services/intake_reasoning.py` (Task B) + the intent schema. **Model/prompt change → needs a paid validation run** (intake-gold), so gate behind approval; everything below is offline-testable once the schema exists.
- **Ambiguity handling:** when the JD supports more than one reading (the "AI Engineer vs Data Scientist" case), emit 2–3 archetypes each flagged `needs_confirmation`, rather than silently picking one.

## 2.2 Consultative confirmation (P7 — "consult, don't assume")
- Present the archetypes to the recruiter as a choice: *"This reads as (a) systems-heavy AI engineer, (b) software-heavy AI engineer, or (c) data scientist — which, or which mix? Each searches very differently."* The recruiter picks/weights/edits and sets, per capability, **must vs nice** (→ hardness) and **current vs ever** (→ company/skill scope).
- **Interim (pre-UI):** when any archetype is `needs_confirmation`, ask one disambiguation question; the full editable card is Phase 3.
- Store the chosen archetype(s) on the confirmed, content-hashed intent.

## 2.3 Retrieval — one query per confirmed archetype, unioned
- The planner already runs multiple queries; extend from 2 to **N (one per archetype)**, each: positive title-expansion on that archetype's representative titles + a capability-rich, **location-anchored** NL query (Phase 1 augmentation) + any **hard** must-have capabilities as `(.)` description/headline keyword leaves. Union + dedup by `crustdata_person_id` (merger already does this).
- Every query stays positive-rich and names the location → location binds (Phase 0). Hard keyword leaves are positive, so they never trigger the weak-query leak.
- **Worked example — "AI Data Engineer" for NCS:** archetype A = DE-who-ships-RAG (title family Data/ML Engineer; hard must-have `RAG|agentic|LLM` via description `(.)`; soft Spark/Python/SQL), archetype B = ML/AI-engineer-who-runs-pipelines. Two queries, unioned. The hard RAG keyword is what converts "AI" from a de-prioritized word into an enforceable requirement — the recruiter opts into the recall cost.

## 2.4 Role-family discrimination (DE / SWE / DevOps / Cloud; Java / .NET)
No dedicated classifier; discriminate with the tools above:
- **Title** → positive title-expansion (soft, recall-friendly).
- **Signature capability** → hard `(.)` description/headline keyword when the recruiter wants precision (e.g. DevOps: `Kubernetes|Terraform|CI/CD`; Cloud: `AWS|Azure|GCP`; Java vs .NET: `Java` vs `.NET`/`C#`, whole-word so no JavaScript bleed).
- **Judge** verifies per candidate downstream.
Recruiter dials precision↔recall by marking a capability hard vs soft. This is the honest answer to "how does it tell them apart": by capability evidence the recruiter designates, not by a magic title taxonomy.

## 2.5 Company scope — fix the historical-company gap
Verified live (2026-10-01, re-confirmed 2026-10-27) — three scopes, all exact, `in`/`not_in` both work:
| Scope | CrustData field |
|---|---|
| current employer | `experience.employment_details.current.company_name` |
| **ever worked there** | `experience.employment_details.company_name` (any-time; superset of current) |
| past only | `experience.employment_details.past.company_name` |

Build:
1. **Intent model:** replace the current-only `preferred_companies` / `exclude_current_companies` with **scoped** lists, e.g. `company_rules: [ {company, mode: include|exclude, scope: current|ever|past} ]` (keep back-compat shims).
2. **Confirmation:** recruiter picks scope per company — "currently at X" vs "ever at X". Default for exclude = `current` (ever-exclude is aggressive); default for target/include = recruiter's choice.
3. **Translation** (`crustdata.py _build_filter_conditions`): map each rule to the matching field + `in`/`not_in`.
4. **Caveats:** (a) `exclude … ever` on a large employer removes millions — surface the impact to the recruiter; (b) `not_in` is a negative operator, so it must ride with a strong, location-named query (Phase 0) or location leaks; (c) exact match, so canonicalize company names (the recruiter picks from CrustData-resolved names, not free text).

## 2.6 Geography — reference mapping (already structural; documents the Phase 0 model + one gap)
| Recruiter case | Boundary input | CrustData filter |
|---|---|---|
| Remote, anywhere in India | work_mode=remote, country=India, remote_scope=anywhere | `country in [India]` |
| Only Bengaluru/Hyderabad/Chennai/Pune | work_mode=remote, remote_scope=cities, remote_cities=[…] | `city in […]` (OR) |
| Within 10 mi of Jersey City | work_mode=onsite/hybrid, city=Jersey City, radius=10 | `geo_distance(Jersey City, 10mi)` |
| **Onsite across several cities** | **not modeled** (onsite boundary is single city + radius) | — |
**Gap to close:** allow a **city list for onsite/hybrid** too (not just remote) → translate to `city in […]`. Small `SearchBoundary` + translator change. All geography is recruiter-defined (never LLM-guessed) and binds once the query is strong+location-named.

## Phase 2 sequencing & validation
- 2.5 (company scope) and 2.6 (multi-city onsite) are **offline-testable, no model change** — ship first, cheapest wins.
- 2.1–2.4 (archetypes + hard/soft capability) need the intake prompt/schema change → **paid validation run (approval required)** against intake-gold + one cheap live probe per archetype. The retrieval/translation half is offline-testable once the schema lands.
- Nothing here changes Phase 0/1; it builds on them.
