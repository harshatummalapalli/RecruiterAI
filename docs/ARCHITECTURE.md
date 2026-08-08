# RecruiterAI — Architecture

This document describes how RecruiterAI turns a job description into candidate
results, and why the code is organized the way it is. It is written for
whoever touches this codebase next — including a future version of whoever is
reading it now.

---

## Design philosophy

RecruiterAI is not a keyword parser wearing a UI. The product's bet is that a
JD should be *understood* the way a senior technical recruiter would read it —
ambiguity detected, unrealistic requirements flagged, technologies related to
each other rather than string-matched — before any search ever runs.

That understanding has to live somewhere that isn't the UI, and isn't the
JD text itself. It's a first-class internal model: **Recruiter Intent**.
Every screen, and every future feature, is meant to consume that model
instead of re-reading the JD from scratch.

---

## The pipeline

```
JD / Recruiter Input
        ↓
Recruiter Intent Engine (frontend/src/intelligence/)
        ↓
Recruiter Intent               ← canonical, provider-independent
        ↓
Search Brief                   ← a structured implementation of Recruiter Intent
        ↓
Provider Query                 ← backend translates Search Brief → provider call
        ↓
Candidate Results
        ↓
Candidate Assessment
```

**Recruiter Intent is the seam.** Everything above it is "understanding the
recruiter." Everything below it is "acting on that understanding." A new
sourcing provider, a smarter reasoning model, or a downstream feature like
Interview Question Generation should only ever need to plug in on one side of
that seam — never both.

---

## Layer responsibilities

### 1. Recruiter Intelligence Layer — `frontend/src/intelligence/`

The decision engine. Pure functions, zero UI dependencies, zero dependency on
`models/` or `screens/*.tsx`. This is enforced directionally: `intelligence/`
never imports from `models/` — `models/` imports from `intelligence/`.

It runs the **Recruiter Reasoning Pipeline**, a sequence of single-responsibility
stages:

| Stage | File | Responsibility |
|---|---|---|
| 1. Role Classification | `roleClassifier.ts` | Classifies the JD into a role family (Backend Engineer, ML Engineer, Engineering Manager, ...) by scoring it against `knowledge/roleFamilies.ts` — multiple independent signals per family (title match, tech-stack match, responsibility-phrase match), not a single keyword, and not a family-specific branch in this file. |
| 2. Technology Understanding | `technologyAnalysis.ts` (+ `technologyGraph.ts`, `languageReasoning.ts`, `knowledge/technologyFamilies.ts`) | Detects primary/supporting technologies, which technology families the JD touches, and distinct AI concepts (LLM, RAG, MCP, Agents, Prompt Engineering, Fine-Tuning — never merged as synonyms). Judges whether multiple detected languages mean a genuine polyglot requirement, interchangeable backgrounds, or a primary language with supporting tech. |
| 3. Title Reasoning | `titleReasoning.ts` (+ `titleIntelligence.ts`, `knowledge/careerProgression.ts`, `knowledge/semanticTitles.ts`) | Expands the primary title into equivalent titles, past titles (one IC-ladder step down), and the default exclusion list — by rule (strip seniority, swap Engineer/Developer, walk the ladder) plus known title-equivalence groups from knowledge, not a static synonym table. |
| 4. Experience Reasoning | `experienceReasoning.ts` | Resolves a working min/max years value and flags when the JD states more than one conflicting range. |
| 5. Location Reasoning | `locationReasoning.ts` | Resolves every distinct location that survived extraction and flags when the JD names more than one country. |
| 6. Constraint Validation | `constraintValidation.ts` (+ `ruleEngine.ts`) | Reusable recruiter rules — over-constrained skill lists, title/experience mismatches, location conflicts, experience conflicts, work-mode conflicts, unresolved multi-language signals. Returns structured `ValidationFinding`s, never UI text. |
| 7. Clarification Generation | `clarificationEngine.ts` | Turns findings into the question set the recruiter actually sees. Prefers one high-value question over several low-value ones (see below), capped at 5. |

`recruiterIntent.ts` sequences all seven stages and assembles their outputs
into the canonical `RecruiterIntent` (typed in `types.ts`) — it contains no
reasoning of its own, only orchestration.

**Why staged instead of one big rule file:** each stage can be tested,
reasoned about, and improved independently. Swapping "Experience Reasoning"
for a smarter version never risks breaking "Location Reasoning." This is also
what makes the pipeline extensible — a new stage (e.g. Domain Expertise
Detection) slots in without touching the others.

#### Recruiter Knowledge Engine — `frontend/src/intelligence/knowledge/`

Knowledge and reasoning are separate concerns. Reasoning stages decide;
`knowledge/` only describes what's generally true and never looks at a
specific JD. A reasoning stage asks *"what does recruiter knowledge say?"*
instead of embedding an assumption like `if title contains 'AI'` directly in
its own control flow.

| Module | What it holds |
|---|---|
| `roleFamilies.ts` | Per role family: detection signals (title/tech/responsibility patterns — still data, just structured), common responsibilities, common technology families, common career transitions, related role families. `roleClassifier.ts` is a generic scorer over this list — it has no per-family branches of its own. |
| `technologyFamilies.ts` | Technology families (Programming Languages, Frameworks, Cloud, Containers, AI, Vector Databases, Databases, Messaging, Observability, Infrastructure) as flat member lists — relationships only, no ranking. `technologyAnalysis.ts` asks it "what family does this skill belong to?" |
| `careerProgression.ts` | The IC ladder (Junior → Mid-level → Senior → Lead → Staff → Principal), kept separate from the management ladder (Engineering Manager → Senior EM → Director → VP) — different careers, not one line. `titleIntelligence.ts` uses this to step down one rung for past titles. |
| `semanticTitles.ts` | Title equivalence groups (e.g. Applied AI Engineer ≈ LLM Engineer ≈ Generative AI Engineer) — titles recruiters treat as interchangeable even though the strings don't match. |
| `hiringPatterns.ts` | Advisory guidance keyed by role family and/or seniority (e.g. "Staff Engineers are usually architecture-focused"). Surfaced on `RecruiterIntent.hiringGuidance` — **informs, never filters or validates.** Nothing downstream is allowed to treat it as a rule. |

Adding a new role family, technology family, career transition, title
equivalence, or hiring pattern is a **data change in `knowledge/`** — it
should never require touching `roleClassifier.ts`, `titleIntelligence.ts`,
`technologyAnalysis.ts`, or any other reasoning stage.

**Confidence is internal only.** Every stage reports a 0–1 confidence, rolled
up into `RecruiterIntent.confidenceBySection`. Nothing renders it. It exists
so Clarification Generation can tell a genuinely low-confidence field from
one that's simply not mentioned in the JD.

**Prioritizing clarifying questions:** Constraint Validation findings carry a
severity (`high` / `medium` / `low`). Clarification Generation keeps only
findings within one severity tier of the highest one present, so a JD with
one blocking ambiguity and several minor ones surfaces the blocking one (and
close peers) without burying the recruiter in low-value questions.

### 2. Search Brief model — `frontend/src/models/searchBrief.ts`, `frontend/src/models/clarification.ts`

The Search Brief is **a structured implementation of Recruiter Intent**, not
an independent interpretation of the JD. `applyLocalExtraction` calls
`buildRecruiterIntent(jdText)` and maps the result into the legacy
`SearchBrief` shape the UI already binds to, respecting whichever fields the
recruiter has locked by editing them directly. `buildClarificationQuestions`
is a one-line pass-through to `RecruiterIntent.clarificationsRequired`.

This module also owns:
- The recruiter-facing edit surface (locked-field tracking, three-stage
  non-destructive merge: local extraction → AI parse → recruiter edit).
- Translating a resolved `SearchBrief` into the backend's `SearchIntent`
  contract (`briefToSearchIntent`) for the `/search` call.

Why the mapping lives here and not inside `intelligence/`: `SearchBrief` is a
UI-shaped, editable, provider-facing structure. `RecruiterIntent` is not —
it has no notion of "locked fields" or backend contracts. Keeping that
translation in `models/` keeps `intelligence/` provider- and UI-agnostic.

### 3. Provider layer — `backend/`

Unchanged by this milestone. `backend/providers/crustdata.py` and friends
translate the backend's `SearchIntent` (a provider-agnostic contract, not a
Crustdata-specific one) into actual provider queries. `RecruiterIntent`
contains no provider-specific concepts, so a second provider can be added by
extending the backend's provider layer without touching `intelligence/` or
any screen.

### 4. UI — `frontend/src/screens/`

Consumes exactly one thing: `SearchBrief` (plus the small set of
UI-only view models built on top of search results — `models/discovery.ts`,
`models/candidateAssessment.ts` — for Candidate Review). No screen imports
from `frontend/src/intelligence/` directly, and none needed to change for
this milestone — confirmed by re-running the full previous verification
suite against the live backend after this refactor.

---

## Data flow, end to end

```
Recruiter types/pastes a JD
        ↓
Stage 1 (every keystroke): applyLocalExtraction
  → buildRecruiterIntent(jdText)   [the 7-stage pipeline, in full, locally]
  → map intent → SearchBrief fields (respecting locks)
  → Live Preview panel renders straight off SearchBrief
        ↓
Recruiter clicks "Build Search Brief"
        ↓
buildClarificationQuestions(jdText) → RecruiterIntent.clarificationsRequired
  ├─ empty  → generateSearchBrief() runs immediately
  └─ non-empty → Clarification screen (existing UI, unchanged) asks
                 the prioritized question set; recruiter answers with a
                 single tap
        ↓
generateSearchBrief()
  → parseJobDescription(jdText)     [backend /parse-jd — unchanged contract]
  → applyAiParse(brief, intent, locked)   [stage 2 — enriches, never blanks]
  → applyClarificationAnswer(...) for each answered question, last-applied
    so nothing overwrites an explicit recruiter decision
        ↓
Search Brief screen (existing UI, unchanged) — fully editable
        ↓
Recruiter clicks "Find Candidates"
  → briefToSearchIntent(brief) → POST /search   [backend contract unchanged]
        ↓
Candidate Review (existing UI, unchanged) — ranking, AI Assessment
(models/candidateAssessment.ts), Shortlist/Maybe/Reject, comparison
```

---

## Extending this later

- **A new reasoning stage** (e.g. domain/industry detection once there's real
  evidence to detect from): add a file to `intelligence/`, call it from
  `recruiterIntent.ts`, add its output to `RecruiterIntent`. No other layer
  changes.
- **A new role family, technology family, career transition, or hiring
  pattern**: add it to the relevant file in `intelligence/knowledge/`. No
  reasoning stage changes.
- **A smarter Role Classifier, or an LLM-backed reasoning stage**: replace
  the body of `roleClassifier.ts` (or any single stage) — its function
  signature is the contract, not its implementation. It should still ask
  `knowledge/` rather than re-embedding assumptions.
- **A second sourcing provider**: extend the backend provider layer.
  `RecruiterIntent` and the Search Brief UI need no changes, because neither
  contains provider-specific concepts.
- **Candidate Ranking, Resume Matching, Interview Question Generation,
  Outreach Personalization, Compensation Benchmarking, Talent Mapping,
  Internal Mobility**: each should consume `RecruiterIntent` (via
  `buildRecruiterIntent`) directly, the same way `models/searchBrief.ts`
  does, rather than re-parsing the JD. None of these are built yet — this is
  what `RecruiterIntent`'s shape was designed to make possible without a
  rewrite.

## What's deliberately *not* in Recruiter Intent yet

`domainExpertise`, `industryContext`, and `companyPreferences` are typed and
present on `RecruiterIntent`, but populated conservatively — empty unless a
future stage has real evidence to detect from. No stage guesses an industry
or a company preference type from vibes. When a stage like that is built, it
slots into the pipeline the same way the other seven did.
