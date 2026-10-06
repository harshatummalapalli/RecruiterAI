# DESIGN — the smallest extension to `StructuredHiringIntent` (Role 1, experimental)

Status: experiment. Nothing here changes production. `ExperimentalHiringIntent` **is a** `StructuredHiringIntent`
(subclass, `experimental_schema.py`), so it is not a new contract: every production field is unchanged, existing intent
JSON still validates with the new fields empty, and the production leak validator still scans every new string.

## Source-priority model (owner-specified; the legacy `SearchBoundary` is NOT used)

    JD + recruiter/HM brief  ->  StructuredHiringIntent

- **JD**: authoritative for formal responsibilities, formal qualifications, stated experience/skill requirements, formal
  preferred qualifications, the role description.
- **Brief**: authoritative for *sourcing interpretation* when it explicitly clarifies, narrows, waives or corrects the JD;
  may add sourcing constraints, define hard negatives, define alternative paths.
- Not a blind merge, not universal brief priority. JD items the brief does not address are retained. A genuine conflict the
  brief does not settle is surfaced (`reconciliations[].action = "unresolved"`), never silently resolved.
- Provenance vocabulary: `jd | recruiter_brief | approved_knowledge | inferred`.

## What was added (and why each field earned its place)

Each entry follows the template the owner set. "Baseline evidence" cites `results/baseline/` (5 runs) and the baseline
gold table. A field that did not solve an observed failure was not added (see "Considered and NOT added").

### 1. `sourcing_paths: [SourcingPath]` (`id`, `label`, `strategy`, `basis`)
- **WHY NEEDED**: Role 1 has two alternative legitimate ways to find a candidate with different conditions.
- **BASELINE EVIDENCE**: `two_paths_preserved`, `path_a_domain_led`, `path_b_capability_led` FAIL 5/5 (REPRESENTATION). The
  model understood both paths and wrote them as prose evidence signals ("Capability-led candidates must be based in
  Hyderabad or Pune") that no code can read.
- **WHY CURRENT SCHEMA FAILS**: one flat intent has one location, one strength per skill, one archetype. Two paths
  cannot be held without merging them.
- **WHY THE SMALLEST FIX**: a list of small records that carry only what *differs*. `strategy` is a 3-value enum
  (`domain_led | capability_led | hybrid`) because the recruiter's own words were "domain-led" / "capability-led / hybrid"
  and the existing `role_archetype` (`title/skill/hybrid`) describes how the role is defined, not how a path sources.
- **ALTERNATIVES**: (a) add `domain_led` to `role_archetype`: global, so it still cannot differ per path; (b) one full
  intent per path: duplicates the global intent (rejected by the owner); (c) free-text only: what the baseline did.
- **DECISION**: ADD. `strategy` is the weakest-justified part: a domain-led path is also recognisable from carrying a
  required domain atom. It is kept because the recruiter states it explicitly and the evaluator needs a path identity
  that does not depend on a model-chosen label. It could be dropped if a second role never needs it.

### 2. Path-scoped requirements = override semantics, not tagging
Fields on a path: `seniority`, `experience`, `location` (replace the global value for that path) and `skills`, `domain`
(replace the same-named global entry, else add). `effective_view(intent, path_id)` resolves them.
- **WHY NEEDED**: geography, Power Query strength, domain strength and seniority differ by path.
- **BASELINE EVIDENCE**: `path_geography_differs`, `pq_not_mandatory_path_a`, `pq_working_knowledge_path_b` FAIL 5/5;
  `path_b_min_6_years` / `path_b_lead_requirement` only PARTIAL (global, not Path B). Power Query became *required* in run 5
  and the compiler then hard-filtered on it, which would drop every Path A candidate.
- **WHY CURRENT SCHEMA FAILS**: singletons (`location`, `seniority`, `experience`) have exactly one slot.
- **WHY THE SMALLEST FIX**: inheritance. Global holds what is true of every path; a path states only the difference. Only
  the five fields Role 1 demonstrably varies are overridable.
- **ALTERNATIVES**: (a) a `scope` tag on every atom: cannot scope singletons without turning them into lists, and touches
  every type; (b) a flat generic `requirements[{path, kind, ...}]` list: a second general contract, rejected; (c) copying the
  whole intent into each path: rejected.
- **DECISION**: ADD (typed overrides on the path). Education, companies and company scale stay global-only until a role
  needs otherwise.

### 3. `proficiency` on a skill (`hands_on | working_knowledge | null`)
- **WHY NEEDED**: the recruiter distinguishes depth ("hands-on SQL/Python", "Power Query is working knowledge, a lower bar").
- **BASELINE EVIDENCE**: `sql_hands_on`, `python_hands_on` PARTIAL 5/5 and `pq_working_knowledge_path_b` FAIL 5/5. Strength says
  how much a skill is *wanted*, not how well it must be known; SQL and Power Query were both just "required".
- **WHY THE SMALLEST FIX**: one nullable 2-value enum on the existing skill record. No level scale, no numbers.
- **ALTERNATIVES**: encode depth in `strength` (conflates two axes, what the baseline did); free text (unvalidatable).
- **DECISION**: ADD with exactly the two values observed. More levels are deliberately not invented.

### 4. `semantic_exclusions: [{concept, includes[]}]`
- **WHY NEEDED**: Role 1's hard negative is a *kind of work* (security operations / SOC), not a company or a title.
- **BASELINE EVIDENCE**: `hard_negative_secops_preserved` FAIL 5/5. The only expressible negative was a company, so the baseline
  emitted `exclude_current_company: "Security firms"` in 5/5 runs, which the unchanged compiler turns into
  `company_name NOT_IN ["Security firms"]` (a literal that matches no real company).
- **WHY THE SMALLEST FIX**: a concept plus the examples the recruiter named. What a provider can enforce, what needs evidence
  verification and what stays semantic is the compiler's later decision, as the owner required.
- **ALTERNATIVES**: a new `Exclusion.kind` such as `exclude_concept`: the production compiler silently ignores unknown kinds
  (verified at `search_compiler.py:289-297`: only company kinds and title are handled), so the negative would vanish with no
  error; a separate list makes it explicit and cannot alter `compile_intent` behaviour.
- **DECISION**: ADD as its own list. `exclusions` stays for named companies/titles.

### 5. `leadership` on `seniority` (`["people","technical"]` = either)
- **WHY NEEDED**: "Lead" means people OR technical leadership; the model must not assume people management.
- **BASELINE EVIDENCE**: `lead_people_or_technical` FAIL 5/5 (RECONCILIATION): the JD's people-leadership wording became a required
  signal, overriding the brief.
- **WHY THE SMALLEST FIX**: it qualifies the existing level word, so it lives on `Seniority` and is path-overridable for free.
  No executive/seniority field was invented.
- **ALTERNATIVES**: an evidence signal "people or technical leadership" (unvalidatable, and where the baseline mangled it).
- **DECISION**: ADD. Note the failure was classed RECONCILIATION, not REPRESENTATION: the field gives the answer a place, but
  on its own does not make the model drop the conflicting JD responsibility (see RESULTS).

### 6. `basis: {sources[], quote}` on every atom
- **WHY NEEDED**: explicit-vs-inferred must be auditable, and a hard constraint must never rest on an inference.
- **BASELINE EVIDENCE**: `provenance_preserved` FAIL 5/5. The lexical report (`provenance.py`) could classify atoms after the
  fact, but nothing travelled with the atom, and it cannot see `recruiter_brief` vs `approved_knowledge` intent.
- **WHY THE SMALLEST FIX**: the model *claims* sources and a short verbatim quote; code verifies (`validators.py`). No line
  numbers are asked for. Three outcomes stay distinct: claimed (model), verified (code), unsupported/inferred.
- **ALTERNATIVES**: model-supplied "verified" flags (never trusted); a provenance graph (overbuilt); provenance only on a few
  atom types (leaves holes where hard constraints hide).
- **DECISION**: ADD as an optional mixin on each atom type. Labels such as `retained_from_jd` / `added_by_brief` are DERIVED by
  code from where support was found, not asked of the model.

### 7. `reconciliations: [{topic, action, jd_quote, brief_quote, result, path_id}]`
- **WHY NEEDED**: when the brief narrows, waives or contradicts a JD item, there may be no surviving atom to carry the decision
  (the JD's "security monitoring" simply must not remain a requirement). The decision must still be visible. A genuine,
  unsettled conflict needs somewhere to be surfaced.
- **BASELINE EVIDENCE**: `cyber_review_not_secops` FAIL 5/5 and `lead_people_or_technical` FAIL 5/5, both RECONCILIATION: the prompt
  told the model to treat the brief "exactly like JD requirements, not as corrections".
- **WHY THE SMALLEST FIX**: only non-trivial decisions are recorded (`narrowed | waived | contradicted | unresolved`); retained
  and added items need no record because their provenance already says so.
- **ALTERNATIVES**: a per-atom reconciliation enum (duplicates the list for surviving atoms, nothing for dropped ones);
  silent override (what the owner ruled out).
- **DECISION**: ADD. Code checks that the quotes are verbatim in the right source, that a waiver was actually applied on the named
  path, and that a "contradicted" item does not survive as a required atom.

### 8. `domain: [{name, strength}]` (global and per path)
- **WHY NEEDED**: Path A is *domain-led*: its identity is the work domain. Neither skill nor company.
- **BASELINE EVIDENCE**: `cyber_review_not_secops` could only be PARTIAL: the domain existed only as `context`/`preferred` evidence-signal
  prose mixed in with the SOC statements; `schema_supports()["domain"]` is False.
- **WHY THE SMALLEST FIX**: same shape as a skill (name + strength). Legal-tech/LPO background is a domain entry, not a company.
- **ALTERNATIVES**: evidence signals (what the baseline did; no way to say Path A requires it and Path B does not).
- **DECISION**: ADD, unconditionally weakest-evidence of the set: the experiment found the model splits domains into 4-9 atoms
  per run (granularity instability), so a role needing a *single* domain would exercise it better.

## Considered and NOT added
| Candidate | Why not |
|---|---|
| `remote` / work-mode flag | RESOLVED in the hardening pass: added as `location.remote` (see below). |
| Multi-valued seniority ("Lead / Senior") | RESOLVED in the hardening pass as `seniority.alternatives`, only because the brief literally states "Lead / Senior" for Path A (see below). |
| Path priority / ranking ("domain-led strongest, capability-led acceptable") | Ranking, which the owner excluded. The model keeps it as a `context` evidence signal. |
| Path-scoped negatives | Role 1's negative is global. Add only when a role needs one. |
| An explicit location-level field (country vs city) | RESOLVED in the hardening pass as `location.countries` (see below). |
| More proficiency levels, a leadership taxonomy, an archetype taxonomy, an ontology | Not demonstrated by any failure. |
| A `retained/added` enum asked of the model | Derived by code instead; asking would be unverifiable. |
| Line numbers | Forbidden; fabrication risk. |

## Exact diff against the current schema
`StructuredHiringIntent` is unchanged. `ExperimentalHiringIntent(StructuredHiringIntent)` adds:

    + domain:               List[DomainReq]          # {name, strength, basis}
    + semantic_exclusions:  List[SemanticExclusion]  # {concept, includes[], basis}
    + sourcing_paths:       List[SourcingPath]       # {id, label, strategy, seniority?, experience?, location?, skills[], domain[], basis}
    + reconciliations:      List[Reconciliation]     # {topic, action, jd_quote?, brief_quote?, result, path_id?}

and re-types existing fields to subclasses that only ADD optional members:

    skills[*]            + proficiency, + basis
    skill_any_of[*], companies[*], education, experience, location, exclusions[*], evidence_signals[*]   + basis
    seniority            + leadership[], + basis

Nothing is removed or renamed; `company_scale`, `role_archetype`, `role_family` are untouched. About 240 lines in one
file; `rm -r backend/experiments/intake_strategy` removes it completely.

## Concept placement
- **Global (in the runs)**: role identity (`Data Analyst`, hybrid), hands-on SQL/Python, 6+ years, base level, education preference,
  JD formal preferences (Relativity/Canopy, frameworks), the security-operations negative, the leadership meaning.
- **Path-scoped**: geography, Power Query strength, domain strength, Path A seniority, path strategy.
- **Model-only** (nothing checks them from the sources alone): path count/identity, which JD responsibilities are `required` vs
  `context`, paraphrase quality, semantic-concept wording, reconciliation `result` text.
- **Deterministically validated at runtime**: enum membership, provider-leak guard, unique path ids, basis presence on
  constraints, quote verbatim in the cited source and cited to the right one, inferred-but-required, waiver applied on the
  named path, contradicted item not surviving, reconciliation quotes. NOT validated: that a quote *entails* the atom (the
  lexical overlap is informational only).
- **Compiler, later (not done)**: country vs city from entry form; compiling per path and combining; semantic negative ->
  enforce / verify / semantic-only; proficiency -> evidence verification, not a filter; remote.
- **Taxonomy / approved knowledge, later**: the SOC / security-operations synonym set to recognise the negative in profiles;
  Legal Tech / LPO / Legal Solutions as one environment; Cyber Incident Review ~ Data Breach Analysis aliasing;
  `approved_knowledge` verification (cannot be checked today).
- **Must NOT be added**: a second intent/contract, a path-priority/ranking field, provider fields, a boolean expression DSL,
  per-path copies of the whole intent, model-supplied verification flags, line-number sources.

---

# Hardening pass (second extension; three typed additions, one rejected field)

Trigger: five correctness issues from the first experiment (Path B's 6+ years inherited by Path A; "Senior" appearing for Path
A; "remote" surviving only in quote text; India held as a city-style entry; reconciliation conflicts that no runtime check
could see). Rule applied: broaden the schema only where the representation, not model variability, is what fails.

## What the source actually says (it matters for item 2)
`inputs/role1_recruiter_brief.txt` line 50, under Path A: "Lead / Senior Data Analyst identity". "Senior" appears nowhere
else in either source. So "Senior" is **source-supported for Path A and unsupported for Path B and globally**. The previous
Lead/Senior variation was an instability *and* a single-valued `seniority.value` forced to drop one of two source-stated
alternatives. Both are recorded in RESULTS_HARDENING.md.

## New fields (same template)

### A. `location.countries` + `location.remote` (on the experimental location)
- **WHY NEEDED**: "India-wide / remote" (Path A) must be distinguishable from city-level Hyderabad/Pune (Path B), typed.
- **BASELINE EVIDENCE**: v2 held India as `entries: ["India"]` in 5/5 runs (country-ness only by string form; the compiler later
  read it as `city IN ["India"]`), and "remote resources across India" appeared in no typed field in 5/5 runs.
- **WHY CURRENT SCHEMA FAILS**: `entries` is one list of strings with no level; there is no remote member.
- **WHY THE SMALLEST FIX**: `countries` (country-wide areas, name only) kept apart from `entries` (places below country);
  `remote` is `allowed | not_allowed | null`. `not_allowed` is the only value beyond "allowed" and exists so a recruiter's "no
  remote" is not forced into silence; "remote only" is not invented. Radius is untouched.
- **ALTERNATIVES**: a `level` tag per entry (cannot hold a country plus a preferred city); a boolean `remote_allowed` (cannot
  say "not allowed" vs unstated without a tri-state, so an enum reads better); a remote flag on the path rather than the
  location (rejected: remote is a property of where, and the path override already moves the whole location).
- **DECISION**: ADD. No provider compilation is implemented.

### B. `seniority.alternatives: [str]`
- **WHY NEEDED**: a source that states more than one acceptable level for the same scope ("Lead / Senior").
- **BASELINE EVIDENCE**: v2 Path A level was `Senior` x3 and `Lead` x2: one value forced a choice between two stated levels.
- **WHY THE SMALLEST FIX**: an OR-list on the existing record; no seniority taxonomy. Each level (value or alternative) must be
  stated in the source for that scope, checked by code (`unsupported_level`), so a model-generated level is flagged, never promoted.
- **ALTERNATIVES**: a list-valued `value` (breaks every consumer of the production type); free text "Lead / Senior" (unverifiable).
- **DECISION**: ADD as a generic capability, as the owner allowed. Role 1's Path B and global level stay single-valued.

### C. Rejected: a new field to locate a path in the source
Leakage checking needs to know which source lines belong to which path. A `source_name` field was considered and **rejected**:
the existing `SourcingPath.id` already carries a name, and the v3 prompt asks for the source's own short designation ("Path B").
Code verifies that some source line opens with it; a path that cannot be located is reported (`path_leakage_checkable`) and not
silently skipped. Limit: a descriptive id that happens to open some unrelated line can be mis-located.

## Generic deterministic validators added (no Role 1 content; unit-tested on an unrelated role)
`path_requirement_leakage`, `reconciliation_conflict` (replaces the two narrower checks), `unsupported_level`,
`country_city_misrepresentation`, `place_not_in_source`, `remote_unsupported`. Definitions are in the `validators.py` docstring.

**On "unless explicitly marked global".** In this representation, placing a requirement at the top level IS the marker that it
applies to every path. The leakage check tests that claim against the sources: a REQUIRED requirement is flagged when the sources
state it only for some paths, whether it was inherited from the global intent or placed in the wrong path. A genuinely global
requirement is one the sources state for every path (SQL and Python here) or for none. This is why an overview line such as "6+
years of experience" does not exempt a requirement that only one path's section restates.

Known limits (reported, not tuned away): section attribution is a plain heuristic (prose below a path heading stays attributed to
it until the next heading); negated lines never count as stating a requirement; strength other than `required` is not checked;
`reconciliation_conflict` fires only for reconciliations whose `jd_quote` is verbatim in the JD and matches an atom by topic words,
so it misses a JD item whose surviving atom comes from different sentences than the quoted one (the leadership case).

## Not added (as instructed)
Scoring, query text, provider fields, ranking, taxonomy, embeddings, probes, candidate evidence, feedback, line numbers, ontology.

---

# FROZEN: Role 1 final status and architectural conclusions

**ROLE 1 REPRESENTATION ACCEPTED FOR CROSS-ROLE VALIDATION**

This is an owner decision made after the hardening pass. It means the representation is expressive enough for Role 1 to justify
testing whether the design generalises. It does NOT authorize compiler or retrieval implementation, and it is not a claim that
the acceptance gate in `RESULTS_HARDENING.md` was met 5/5 (it was not; see "Unresolved risks"). The experiment is frozen: no
further Role 1 tuning, no Role 2, no live retrieval, no production change.

## Locked recruiter decisions (ground truth; the evaluator in `gold_experimental.py` encodes them)
| | Path A: domain-led | Path B: capability-led / hybrid |
|---|---|---|
| Seniority | Lead OR Senior (brief: "Lead / Senior Data Analyst identity"; `Senior` stays) | Lead |
| Experience | none | 6+ years (NOT global, NOT on Path A) |
| SQL / Python | hands-on | hands-on |
| Power Query | not required | working knowledge (required) |
| Domain | Cyber Incident Review / Data Breach Analysis, **preferred, not required** (the brief says "Ideally"); legal-tech / LPO / legal-solutions background preferred | not required |
| Geography | country India, remote allowed | cities Hyderabad OR Pune |
| Leadership | "Lead" = people OR technical leadership (both paths) | same |

Global: the security-operations negative (below) and the JD's formal items the brief does not address (Relativity/Canopy, degree
streams, review / QA / compliance / audit, frameworks and privacy), retained at the JD's strength.

## Final Role 1 representation (what the experimental intent must say)
    role_family: Data Analyst                    archetype: hybrid
    seniority (global): Lead, required, leadership [people, technical]
    skills (global): SQL hands_on required; Python hands_on required; Power Query working_knowledge required;
                     Relativity, Canopy preferred
    domain (global): Cyber Incident Review / Data Breach Analysis (legal-tech context), preferred
    semantic_exclusions: security-operations work (cybersecurity operations, SOC, security operations, SIEM, threat detection);
                         "a strong SQL/Python analyst working at a security firm" (subordinate to the first, see below)
    sourcing_paths:
      Path A (domain_led):   seniority Lead + alternative Senior, preferred;
                             location countries [India], entries [], remote allowed;
                             skills: Power Query not required (waived); domain: preferred
      Path B (capability_led): experience 6+ required; location entries [Hyderabad, Telangana, India; Pune, Maharashtra, India]
                             (inherits Lead, SQL/Python hands-on, Power Query working knowledge, no required domain)
    reconciliations: security monitoring contradicted; Power Query waived on Path A; "Lead" widened to people OR technical
    experience (global): absent      company exclusions: none      radius: none

## Leadership
The existing `seniority.leadership = [people, technical]` already represents "acceptable types: people, technical", so **no new
field is added** (the owner's `acceptable_types` is this same list under its existing name). The JD sentence "Lead, mentor,
support Cyber Incident Review Analysts" stays contextual evidence (`context`), never an implicit direct-reports requirement. The
evaluator fails (PARTIAL, RECONCILIATION) when it survives as a *required* people-only atom.

## Cyber / security distinction
The semantic negative is about work identity: security-operations-style work (cybersecurity operations, SOC, security operations,
and equivalent). The recruiter's statement that a strong SQL/Python analyst working at a security firm is to be excluded is kept
as a qualified semantic concept in the recruiter's own words, **subordinate to the work-identity negative**: it applies when the
evidence shows the person's actual work is security operations, not on employer industry alone. The evaluator requires the firm
statement to sit beside the work-identity negative and fails any company-name exclusion. Honest limit: the schema has no field
that says "this negative is conditional on that one"; today that subordination is a convention the compiler and judge must
honour (see risks).

## 6+ years
It belongs to Path B only: not global, not on Path A. The generic `path_requirement_leakage` validator stays. The 1 leak in 5 runs
(run 1: placed globally, so inherited by Path A) is recorded as an extraction/reconciliation instability that the validator
correctly caught. No further tuning to reach 5/5.

## PROVEN FOR ROLE 1
- the current (production) representation could not express the sourcing strategy (baseline: 14 of 16 critical assertions non-PASS,
  12 of them REPRESENTATION by schema introspection)
- `sourcing_paths` are justified
- path-scoped requirements are justified (override semantics)
- path-scoped geography is justified
- proficiency (`hands_on` / `working_knowledge`) is justified
- semantic exclusions are justified (the baseline's only expressible negative was a company, which compiled to a meaningless filter)
- typed country / remote geography is justified (`location.countries`, `location.remote`)
- provenance and reconciliation are justified (code can verify the model's quotes; reconciliations make narrowing visible)
- the recruiter brief must be able to explicitly narrow or waive JD meaning (the production prompt's "treat the brief exactly like JD
  requirements, not as corrections" produced the reconciliation failures)
- intake and compiler need separate responsibilities (the baseline compiled India as a city and a work-type negative as a company
  string, from intents that were otherwise understandable)

## NOT YET PROVEN GENERALLY
- that this schema generalises across role families
- that these exact fields are sufficient for all difficult recruiter workflows
- that compiler behaviour is correct against the new representation (the compiler was never run on it)
- that retrieval quality improves
- that semantic exclusions can be reliably enforced by providers

"Sufficient for this class of role" is **not** claimed: one role is one data point. An earlier wording to that effect in
`RESULTS.md` is withdrawn.

## Architectural boundary
    JD + Recruiter/HM Brief
            |
            v
    StructuredHiringIntent          (intake: understand and reconcile; preserve strategy)
            |
            v
    Deterministic Compiler          (translate APPROVED intent into provider constraints)
            |
            v
    Provider-executable plan
            |
            v
    CrustData retrieval
            |
            v
    Evidence / Judge                (semantic facts a provider cannot reliably enforce)
            |
            v
    Recruiter decision

| layer | responsibility |
|---|---|
| Intake | understand and reconcile hiring intent from two sources with different authority |
| StructuredHiringIntent | preserve recruiter strategy, alternatives, scope, strengths, provenance and exclusions; meaning only, never provider mechanics |
| Compiler | translate approved intent into executable provider constraints; decides what a provider can enforce, what needs verification, what stays semantic |
| Taxonomy / knowledge | approved equivalences, role-family mappings and provider capability knowledge |
| Evidence / Judge | evaluate semantic facts provider search cannot reliably enforce (work identity, depth of skill, leadership kind) |

Two rules that follow, and are not negotiable: do not move compiler logic into the LLM, and do not move semantic judgment into
provider filters merely because a field is filterable.

## Negative decisions (explicitly NOT being added)
- a second search contract
- a separate Task C
- LLM-generated provider query text
- candidate scoring
- retrieval ranking changes
- a universal role ontology
- provider-specific fields in `StructuredHiringIntent`
- automatic company-industry exclusions
- automatic people-manager requirements
- invented geographic radius

## Unresolved risks
1. **Extraction instability remains.** Over the 5 v3 runs scored against the locked ground truth: Path A domain `preferred` in 2,
   `required` in 3 (extraction; the schema can express the right answer); 6+ years leaked into Path A in 1 (caught by the
   validator); a required people-only leadership atom survived in 1 (not caught at runtime). The representation is accepted; the
   reliability of extraction into it is not established.
2. **Runtime validation covers less than the evaluator.** The generic validators are structural and lexical. The evaluator holds
   Role 1's truth; nothing at runtime would have known the run-4 leadership atom was wrong.
3. **Provenance "verified" means the quote exists in the cited source, not that it entails the atom.**
4. **The security-firm subordination is a convention, not a field.** A compiler or judge that reads the firm statement as an
   employer-industry rule would violate the recruiter's decision with no schema error.
5. **The compiler has never run against the new representation.** Per-path compilation, countries vs entries, remote,
   proficiency and semantic exclusions are all unimplemented downstream; the baseline already showed the compiler corrupts
   country-level intent.
6. **Semantic exclusions may not be provider-enforceable.** Whether a provider can enforce "security-operations work" is untested.
7. **The prompt is shaped by this class of role** and the evaluator by this role's truth. Neither is neutral evidence of
   generality. One model, one JD, five runs per arm.

## Recommended next experiment
A differently shaped real role, not another Role 1 cycle: run `prompt_v3` and the unchanged schema and validators once on a role
with a different structure (for example a single path with a hard negative and a numeric experience band, or a title-defined
role with company preferences and no paths), with the recruiter's ground truth written down **before** the run, and report
which fields were exercised, which were not needed, and what was missing. Compiler and retrieval work stay out of scope until
that result is in.
