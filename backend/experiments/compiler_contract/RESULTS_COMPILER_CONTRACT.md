# RESULTS — Compiler contract validation (offline, measurement only)

**ACCEPTANCE CRITERION NOT MET.** The criterion was: *"No meaningful recruiter intent is silently lost or semantically strengthened without an explicit, auditable
routing decision."* Over the 15 frozen intents (Role 1, 2, 3 x 5 runs), the unchanged compiler leaves **336 of 1079 meaning atoms
(31%) with no destination at all** (empty output delta when the atom is removed; no audit row, no leaf, no checklist item, no warning), and it
strengthens or weakens scope in the ways listed in sections D and G. This is the baseline gap, not a redesign. Nothing was fixed.

What the compiler does well and should keep: it never invents a provider constraint; it never turns a semantic exclusion, a preference or a company preference
into a company or title filter (0 negative leaves; 0 company leaves in Role 3); it keeps required experience, required education, the title, and the location
entry exact; it routes every evidence signal to the downstream checklist with its tier; it carries an unknown level ("Staff", "Senior Manager") verbatim.

## What to distrust (read first)
1. **The expected fates, the check definitions and the gap-type rules are mine.** They were committed before any compile output was examined (`CONTRACT_EXPECTATIONS.md`,
   commit `cda3564`), but you have not reviewed them. The ten predictions in that file were all borne out; a test pins each.
2. **The drop count depends on atom granularity.** One atom = one skill, one list item, one stream, one proficiency value. A skill with a proficiency is two atoms; 109 Role 2
   proficiencies are 109 atoms. Read section C by CONCEPT first and use the percentage only as a secondary number.
3. **Stored intents include their intake-time errors** (frozen, not fixed): Role 1 run 1 put "6+ years" in the global intent; Role 2 (prompt_v3) carries the comparison title
   "Forward Deployed Engineer" and unsupported `current` relationships; Role 3 runs 2-3 carry an invented `leadership`. Where a result depends on such an error it is labelled
   and the gap type says so; the compiler is judged on what it does with the intent it is GIVEN.
4. **Role 2's stored intents pre-date `advanced` and `work_mode`.** Those two are tested on the real Role 3 intents and on one clearly labelled SYNTHETIC overlay of the Role 2
   intents (Python/Java `advanced`, `work_mode=hybrid`, seniority `Staff`). The overlay is not an extraction result.
5. **Offline only.** No provider was called, so recall/precision, whether CrustData matches a literal string such as "Bachelor’s degree", the Judge, and the admission gate were
   NOT run. "Downstream" routes are claims the compiler makes about a consumer that today exists only in shadow mode (the compiled plan is built by `search_compiler_shadow`
   and nothing else calls `compile_intent` or `judge_checklist`; the admission/level code reads the legacy `intent.role.seniority`, not the compiled plan).
6. **Ablation measures "does the output depend on this atom".** It proves an atom reaches nothing; it does not prove that an atom which does reach something is routed the
   RIGHT way. Correctness of the routes that exist is judged separately by the critical checks (sections E) and the probes (D, G).

## Method in one paragraph
Each atom is removed (or, for a qualifier such as proficiency, reset) and the unchanged compiler is re-run; the diff of the whole output (provider leaves, every audit row,
retrieval titles, warnings, normalizations, downstream checklist) is the atom's destination, and an empty diff is a silent drop. A read-set tracer independently records which
intent fields `compile_intent` ever reads; the two agree (a test pins it). Paths are measured by compiling each path's effective view with the same compiler and diffing it against the
plan compiled from the whole intent. Strength, relationship, location and level behaviour are measured with minimal synthetic intents. Compiler, capability map, taxonomy,
schema, knowledge files and all frozen intents are pinned by hash (`results/baseline_manifest.json`, `tests/test_experiment_compiler_contract.py`).

## A. Current compiler behavior across Roles 1-3
Compiled with `COMPILER_VERSION v1-2026-10-02`, capability map `v1-2026-10-01`, taxonomy `v1-2026-10-02`. Per intent (full plans, audit records and downstream checklists are in `results/baseline/`):

| intent | hard leaves | what they are | rows: provider | rows: downstream | rows: context | rows: admission | checklist items | present-but-never-read field paths |
|---|---|---|---|---|---|---|---|---|
| R1/1 | 8 | experience 1, skill text 6, title 1 | 4 | 22 | 0 | 0 | 22 | 73 |
| R1/2 | 1 | title 1 | 1 | 23 | 0 | 0 | 23 | 76 |
| R1/3 | 1 | title 1 | 1 | 23 | 0 | 1 | 23 | 80 |
| R1/4 | 1 | title 1 | 1 | 24 | 0 | 0 | 24 | 76 |
| R1/5 | 1 | title 1 | 1 | 21 | 0 | 0 | 21 | 76 |
| R2/1 | 46 | education 6, experience 1, location 3, skill text 30, title 6 | 14 | 56 | 0 | 0 | 56 | 29 |
| R2/2 | 46 | education 6, experience 1, location 3, skill text 30, title 6 | 14 | 55 | 0 | 0 | 55 | 29 |
| R2/3 | 31 | education 6, experience 1, location 3, skill text 15, title 6 | 9 | 60 | 0 | 0 | 60 | 29 |
| R2/4 | 19 | education 6, experience 1, location 3, skill text 3, title 6 | 5 | 67 | 0 | 0 | 67 | 29 |
| R2/5 | 34 | education 6, experience 1, location 3, skill text 18, title 6 | 10 | 60 | 0 | 0 | 60 | 29 |
| R3/1 | 12 | education 6, experience 2, location 3, title 1 | 4 | 30 | 6 | 1 | 30 | 42 |
| R3/2 | 12 | education 6, experience 2, location 3, title 1 | 4 | 30 | 6 | 1 | 30 | 43 |
| R3/3 | 12 | education 6, experience 2, location 3, title 1 | 4 | 31 | 6 | 1 | 31 | 43 |
| R3/4 | 12 | education 6, experience 2, location 3, title 1 | 4 | 29 | 6 | 1 | 29 | 42 |
| R3/5 | 12 | education 6, experience 2, location 3, title 1 | 4 | 31 | 6 | 1 | 31 | 42 |

Reading:
- **Role 1 compiles to one provider constraint in 4 of 5 runs**: the literal title `Data Analyst`. No geography, no experience, no skills. Run 1 has 8 leaves because the intake placed "6+ years" and `SQL`/`Python` (relationship `current`) in the global intent.
  There is no leaf for India, Hyderabad or Pune in any Role 1 run: all geography lives in `location.countries` (never read) and in path locations (never read).
- **Role 2 compiles to 19-46 leaves**: 6 title leaves (4 from the `Software Engineer` taxonomy entry, plus `Solution Architect` and the comparison title `Forward Deployed Engineer`), degree/stream, 12+ years, Hyderabad
  (country AND state AND city), and one hard OR-group per `current` skill (10, 10, 5, 1, 6 skills).
- **Role 3 compiles to 12 leaves in all five runs**: the title, 8-12 years, the degree and five streams, Hyderabad (country AND state AND city). Every skill, group, evidence signal and level goes downstream; the six companies go to context.
- The `present-but-never-read` column counts field paths (including each `basis` path) that hold a value in the intent but that `compile_intent` never reads.

## B. Field fate matrix (every concept present in the extended intents)
Each cell is the fates of all atoms of that concept over the 5 runs. Concepts are split by strength and relationship where the compiler's behaviour depends on them. Kind: MEANING = recruiter meaning;
RECORD = reconciliation decision; METADATA = provenance / archetype.

| concept [strength, relationship] | kind | Role 1 (5 runs) | Role 2 (5 runs) | Role 3 (5 runs) |
|---|---|---|---|---|
| `company [preferred]` | MEANING | – | – | PREFERENCE_CONTEXT×30 |
| `domain (in path) [preferred]` | MEANING | SILENTLY_DROPPED×8 | – | – |
| `domain (in path) [required]` | MEANING | SILENTLY_DROPPED×3 | – | – |
| `domain [context]` | MEANING | SILENTLY_DROPPED×10 | SILENTLY_DROPPED×3 | SILENTLY_DROPPED×5 |
| `domain [preferred]` | MEANING | SILENTLY_DROPPED×3 | – | SILENTLY_DROPPED×10 |
| `domain [required]` | MEANING | – | SILENTLY_DROPPED×13 | SILENTLY_DROPPED×5 |
| `education.degree [preferred]` | MEANING | SILENTLY_DROPPED×5 | – | – |
| `education.degree [required]` | MEANING | – | ENFORCED×10 | ENFORCED×5 |
| `education.stream [preferred]` | MEANING | SILENTLY_DROPPED×30 | – | – |
| `education.stream [required]` | MEANING | – | ENFORCED×20 | ENFORCED×25 |
| `evidence_signal [context]` | MEANING | VERIFIED_DOWNSTREAM×12 | – | VERIFIED_DOWNSTREAM×54 |
| `evidence_signal [preferred]` | MEANING | VERIFIED_DOWNSTREAM×6 | – | VERIFIED_DOWNSTREAM×10 |
| `evidence_signal [required]` | MEANING | VERIFIED_DOWNSTREAM×55 | VERIFIED_DOWNSTREAM×116 | VERIFIED_DOWNSTREAM×30 |
| `experience.max [required]` | MEANING | – | – | ENFORCED×5 |
| `experience.min (in path) [required]` | MEANING | SILENTLY_DROPPED×4 | – | – |
| `experience.min [required]` | MEANING | ENFORCED×1 | ENFORCED×5 | ENFORCED×5 |
| `location.country (in path)` | MEANING | SILENTLY_DROPPED×5 | – | – |
| `location.entry (in path) [required]` | MEANING | SILENTLY_DROPPED×10 | – | – |
| `location.entry [required]` | MEANING | – | ENFORCED×5 | ENFORCED×5 |
| `location.remote (in path)` | MEANING | SILENTLY_DROPPED×5 | – | – |
| `location.work_mode` | MEANING | – | – | SILENTLY_DROPPED×5 |
| `provenance.basis` | METADATA | SILENTLY_DROPPED×5 | SILENTLY_DROPPED×5 | SILENTLY_DROPPED×5 |
| `reconciliation` | RECORD | SILENTLY_DROPPED×28 | – | – |
| `role_archetype` | METADATA | SILENTLY_DROPPED×5 | SILENTLY_DROPPED×5 | SILENTLY_DROPPED×5 |
| `role_family` | MEANING | ENFORCED×5 | ENFORCED×10, NORMALIZED×5 | ENFORCED×5 |
| `semantic_exclusion` | MEANING | SILENTLY_DROPPED×15 | – | SILENTLY_DROPPED×5 |
| `seniority.alternatives (in path)` | MEANING | SILENTLY_DROPPED×5 | – | – |
| `seniority.leadership` | MEANING | SILENTLY_DROPPED×2 | – | SILENTLY_DROPPED×2 |
| `seniority.leadership (in path)` | MEANING | SILENTLY_DROPPED×18 | – | – |
| `seniority.value` | MEANING | VERIFIED_DOWNSTREAM×1 | – | VERIFIED_DOWNSTREAM×5 |
| `seniority.value (in path)` | MEANING | SILENTLY_DROPPED×9 | – | – |
| `skill (in path) [preferred, any]` | MEANING | SILENTLY_DROPPED×1 | – | – |
| `skill (in path) [required, any]` | MEANING | SILENTLY_DROPPED×4 | – | – |
| `skill (in path) [required, current]` | MEANING | SILENTLY_DROPPED×1 | – | – |
| `skill [preferred, any]` | MEANING | VERIFIED_DOWNSTREAM×19 | – | – |
| `skill [required, any]` | MEANING | VERIFIED_DOWNSTREAM×21 | VERIFIED_DOWNSTREAM×172 | VERIFIED_DOWNSTREAM×47 |
| `skill [required, current]` | MEANING | ENFORCED×2 | ENFORCED×32 | – |
| `skill.proficiency` | MEANING | SILENTLY_DROPPED×20 | SILENTLY_DROPPED×109 | SILENTLY_DROPPED×5 |
| `skill.proficiency (in path)` | MEANING | SILENTLY_DROPPED×6 | – | – |
| `skill_any_of [required, any]` | MEANING | – | VERIFIED_DOWNSTREAM×10 | VERIFIED_DOWNSTREAM×10 |
| `sourcing_path (in path)` | MEANING | SILENTLY_DROPPED×10 | – | – |

Fates are exactly: ENFORCED, NORMALIZED, VERIFIED_DOWNSTREAM, PREFERENCE_CONTEXT, UNRESOLVED, DROPPED_WITH_JUSTIFICATION, SILENTLY_DROPPED. **No atom in 15 intents is DROPPED_WITH_JUSTIFICATION or UNRESOLVED:** the compiler
has no way to say "I did not use this", so every drop is silent. Seniority is counted VERIFIED_DOWNSTREAM because its audit route is `admission_level_fit`; that is a claim about the admission gate (see distrust 5).

## C. Silent-drop findings
| role (5 runs each) | meaning atoms | SILENTLY_DROPPED meaning atoms | share | decision records dropped | metadata dropped |
|---|---|---|---|---|---|
| Role 1 | 296 | 174 | 59% | 28 | 10 |
| Role 2 | 510 | 125 | 25% | 0 | 10 |
| Role 3 | 273 | 37 | 14% | 0 | 10 |
| **all** | 1079 | 336 | 31% | 28 | 30 |

By origin (the 336 meaning atoms):

| origin of the dropped atom | Role 1 | Role 2 | Role 3 | all | concepts |
|---|---|---|---|---|---|
| extension field (not in the production schema) | 110 | 125 | 37 | 272 | domain, location.country, location.remote, location.work_mode, semantic_exclusion, seniority.alternatives, seniority.leadership, skill.proficiency, sourcing_path |
| production-schema atom in the global intent | 35 | 0 | 0 | 35 | education.degree [preferred], education.stream [preferred] |
| production-schema atom, but inside a sourcing path | 29 | 0 | 0 | 29 | experience.min, location.entry, seniority.value, skill |

By concept (only concepts that lose an atom):

| meaning concept (only those with a drop) | Role 1 | Role 2 | Role 3 |
|---|---|---|---|
| `domain` | 13 of 13 | 16 of 16 | 20 of 20 |
| `domain (in path)` | 11 of 11 | – | – |
| `education.degree` | 5 of 5 | 0 of 10 | 0 of 5 |
| `education.stream` | 30 of 30 | 0 of 20 | 0 of 25 |
| `experience.min (in path)` | 4 of 4 | – | – |
| `location.country (in path)` | 5 of 5 | – | – |
| `location.entry (in path)` | 10 of 10 | – | – |
| `location.remote (in path)` | 5 of 5 | – | – |
| `location.work_mode` | – | – | 5 of 5 |
| `semantic_exclusion` | 15 of 15 | – | 5 of 5 |
| `seniority.alternatives (in path)` | 5 of 5 | – | – |
| `seniority.leadership` | 2 of 2 | – | 2 of 2 |
| `seniority.leadership (in path)` | 18 of 18 | – | – |
| `seniority.value (in path)` | 9 of 9 | – | – |
| `skill (in path)` | 6 of 6 | – | – |
| `skill.proficiency` | 20 of 20 | 109 of 109 | 5 of 5 |
| `skill.proficiency (in path)` | 6 of 6 | – | – |
| `sourcing_path (in path)` | 10 of 10 | – | – |

Findings:
1. **Every extension field is silently dropped, in every run, in every role** (`sourcing_paths`, `domain`, `semantic_exclusions`, `skill.proficiency`, `seniority.leadership`, `seniority.alternatives`, `location.countries`, `location.remote`, `location.work_mode`): the compiler reads none of them, and the tracer confirms it. 272 of the 336 dropped atoms.
2. **Role 1's whole strategy is dropped, not weakened**: both paths, both path geographies, the path-only 6+ years, the Power Query waiver, the five reconciliations, the security-operations exclusion and its security-firm qualifier, leadership, and the domain preference. What remains is the title, plus whatever the intake happened to put globally.
3. **`proficiency` is dropped on every skill** (20 + 109 + 5 atoms). The downstream checklist text for a skill is the skill name only (`"Microsoft Excel"`); the `advanced` / `working_knowledge` / `hands_on` qualifier never reaches it.
4. **Production-schema gap, independent of the extension (35 atoms):** a `preferred` education produces no leaf **and no audit row** (Role 1: 5 degrees, 30 streams). A preference that disappears with no trace.
5. **Restated meaning is the only thing that survives.** Where the model ALSO wrote an evidence signal ("People leadership or technical leadership", "Experience managing cyber incident reviews…", "Working knowledge of Power BI…"), the meaning reaches the Judge as untyped text; the typed field itself reaches nothing. That is redundancy in the intake, not compiler routing.
6. **Provenance and decision records are dropped (30 metadata atoms, 28 records).** The audit record binds the whole intent by `intent_hash` only: changing an unread atom changes the intent hash and leaves the plan hash, every audit row and the checklist identical (probe `hash_sensitivity`). No audit row says who claimed an atom, and no row says a reconciliation happened.
7. `role_archetype` is classification metadata; it is counted as METADATA and not as lost meaning.

## D. Semantic strengthening / weakening findings
### D1. Observed on the frozen intents
- **Path logic is flattened, and the flat plan is neither path's plan.** The compiler cannot see paths, so the plan is the AND of whatever the intake put in the global intent. Compiling each path's effective view with the same compiler shows what each path needed and the plan lacks:

| intent | path | provider leaves the PATH needs that the compiled plan lacks | leaves the plan has that the path does not need | audit rows the path needs that the plan lacks |
|---|---|---|---|---|
| R1/1 | PATH A | – | – | seniority |
| R1/1 | PATH B | headline "Power Query", city ["Hyderabad", "Pune"], summary "Power Query", description "Power Query" | – | location, seniority, skill:Power Query |
| R1/2 | PATH A | – | – | seniority |
| R1/2 | PATH B | city ["Hyderabad", "Pune"], years_of_experience_raw 6 | – | experience, location, seniority, skill:Power Query |
| R1/3 | PATH A | – | – | – |
| R1/3 | PATH B | city ["Hyderabad", "Pune"], years_of_experience_raw 6 | – | experience, location, skill:Power Query |
| R1/4 | PATH A | – | – | seniority, skill:Power Query |
| R1/4 | PATH B | city ["Hyderabad", "Pune"], years_of_experience_raw 6 | – | experience, location, seniority, skill:Power Query |
| R1/5 | PATH A | – | – | seniority |
| R1/5 | PATH B | city ["Hyderabad", "Pune"], years_of_experience_raw 6 | – | experience, location, seniority, skill:Power Query |

  Path B needs `city IN [Hyderabad, Pune]` and `years_of_experience >= 6` (and a Power Query row); the whole-intent plan has none of them in runs 2-5. Path A needs a country-wide India filter that the compiler cannot express at all (`countries` is never read, so even Path A's own plan has no geography). In run 1 the intake placed 6+ years globally, so it binds Path A as well (SCOPE_CHANGED), a case the compiler cannot detect because it has no scope.
- **Role 2: an analogy title became a hard target title in 5/5 runs** (`Forward Deployed Engineer` is one of 6 ORed title leaves). **10, 10, 5, 1, 6 required skills with relationship `current` became hard ORs over the current role's description, headline and summary**; the frozen intake validator `unsupported_current_relationship` flags exactly those. The compiler has no way to tell an authoritative `current` from an unsupported one.
- **Role 3: an INFERRED state became a hard filter.** The JD says "Hyderabad, India"; the model wrote "Hyderabad, Telangana, India" from its own world knowledge (ground truth G2: INFERRED), and the compiler turned it into `country = India AND state = Telangana AND city = Hyderabad`. `basis` is not read, so an inferred sub-value is enforced exactly like a stated one.
- **Role 3: `Related discipline` and `Bachelor’s degree` (curly apostrophe) become literal provider strings** (R3-09, an observation: the provider was not called). Degree surface forms are only expanded for B.Tech / B.E / M.Tech.

### D2. Demonstrated by probes (latent: not triggered by the frozen intents, but real behaviour of the unchanged compiler)
Minimal synthetic intents; provider hard leaves besides the title leaf, and the audit route:

| construct | strength | provider hard leaves | audit route |
|---|---|---|---|
| experience | required | 2 | provider_hard_filter |
| location | required | 3 | provider_hard_filter |
| seniority | required | 0 | admission_level_fit |
| education(degree+stream) | required | 2 | provider_hard_filter |
| education(degree only) | required | 1 | provider_hard_filter |
| evidence_signal | required | 0 | downstream_evidence |
| experience | preferred | 2 | provider_hard_filter |
| location | preferred | 3 | provider_hard_filter |
| seniority | preferred | 0 | admission_level_fit |
| education(degree+stream) | preferred | 0 | NO AUDIT ROW |
| education(degree only) | preferred | 0 | NO AUDIT ROW |
| evidence_signal | preferred | 0 | downstream_evidence |
| experience | context | 2 | provider_hard_filter |
| location | context | 3 | provider_hard_filter |
| seniority | context | 0 | admission_level_fit |
| education(degree+stream) | context | 2 | provider_hard_filter |
| education(degree only) | context | 1 | provider_hard_filter |
| evidence_signal | context | 0 | downstream_evidence |

| construct | strength | relationship = current | = past | = any |
|---|---|---|---|---|
| skill | required | 3 (HARD) | 2 (HARD) | 0 (downstream) |
| skill | preferred | 0 (downstream) | 0 (downstream) | 0 (downstream) |
| skill | context | 3 (HARD) | 2 (HARD) | 0 (downstream) |
| skill_any_of | required | 6 (HARD) | 4 (HARD) | 0 (downstream) |
| skill_any_of | preferred | 0 (downstream) | 0 (downstream) | 0 (downstream) |
| skill_any_of | context | 6 (HARD) | 4 (HARD) | 0 (downstream) |
| company | required | 1 (HARD) | 1 (HARD) | 1 (HARD) |
| company | preferred | 0 (context) | 0 (context) | 0 (context) |
| company | context | 1 (HARD) | 1 (HARD) | 1 (HARD) |
| company_scale | required | 1 (HARD) | 1 (HARD) | 1 (HARD) |
| company_scale | preferred | 0 (downstream) | 0 (downstream) | 0 (downstream) |
| company_scale | context | 1 (HARD) | 1 (HARD) | 1 (HARD) |

- **`strength = context` is treated as `required`** for skills, skill groups, companies, company scale and education: `recommend_routing` only special-cases `preferred`. A context-level company becomes a hard company filter.
- **`experience` and `location` ignore strength entirely**: `preferred` and `context` are hard filters exactly like `required` (the audit row records the strength, the routing does not use it).
- **`education` is routed inconsistently**: `preferred` leaves no leaf and no audit row; `context` is a hard filter; `required` is a hard filter.
- **`seniority` strength is recorded but never routes** (always `admission_level_fit`).
- **Location parsing keeps what it can only for a lone 3-part entry:**

| case | location fields | provider leaves |
|---|---|---|
| one_entry_3part | {"entries": ["Hyderabad, Telangana, India"]} | city=["Hyderabad"]; country=["India"]; state=["Telangana"] |
| one_entry_2part | {"entries": ["Hyderabad, India"]} | city=["Hyderabad"] |
| one_entry_city_only | {"entries": ["Hyderabad"]} | city=["Hyderabad"] |
| two_entries_3part | {"entries": ["Hyderabad, Telangana, India", "Pune, Maharashtra, India"]} | city=["Hyderabad", "Pune"] |
| alias_entry | {"entries": ["Bangalore, Karnataka, India"]} | city=["Bengaluru"]; country=["India"]; state=["Karnataka"] |
| countries_only | {"countries": ["India"]} | NO LEAF AND NO AUDIT ROW |
| countries_plus_remote_allowed | {"countries": ["India"], "remote": "allowed"} | NO LEAF AND NO AUDIT ROW |
| work_mode_only | {"work_mode": "hybrid"} | NO LEAF AND NO AUDIT ROW |
| entry_plus_hybrid | {"entries": ["Hyderabad, Telangana, India"], "work_mode": "hybrid"} | city=["Hyderabad"]; country=["India"]; state=["Telangana"] |

  A lone 3-part entry becomes country AND state AND city. A 2-part entry ("Hyderabad, India") loses the country; **two or more entries keep only the cities** (state and country dropped, so "Hyderabad" can match another country); `countries` alone, `remote` and `work_mode` produce no leaf **and no audit row**.
- **Descriptive group terms become literal phrases if the group routes to the provider** (`"Similar business intelligence/reporting platform"` as a whole-word match). Latent in Role 3 only because those groups are `any`.
- **Role family:** the taxonomy has two entries. Every other title is used verbatim:

| role_family in the intent | hard title leaves | titles in the provider filter |
|---|---|---|
| Data Analyst | 1 | Data Analyst |
| Software Engineer | 4 | Software Engineer, Backend Engineer, Backend Developer, Python Developer |
| Solution Architect | 1 | Solution Architect |
| FP&A and Business Finance Manager | 1 | FP&A and Business Finance Manager |
| Software Engineer, Solution Architect, Forward Deployed Engineer | 6 | Software Engineer, Backend Engineer, Backend Developer, Python Developer, Solution Architect, Forward Deployed Engineer |

- **Level strings** are carried verbatim (never silently remapped by the compiler). The downstream candidate-evidence level reader then maps them as follows ("Senior Manager" reads as `senior`; `staff` and `senior manager` are absent from `knowledge/seniority.json`):

| level string | compiler carries it verbatim | audit route | in seniority.json | downstream candidate-evidence level reader maps it to |
|---|---|---|---|---|
| Staff | yes | admission_level_fit | False | staff/lead (rank 4) |
| Senior Manager | yes | admission_level_fit | False | senior (rank 3) |
| Principal Engineer | yes | admission_level_fit | False | principal (rank 5) |
| Lead | yes | admission_level_fit | True | staff/lead (rank 4) |
| Senior | yes | admission_level_fit | True | senior (rank 3) |
| Head of Finance | yes | admission_level_fit | False | director (rank 6) |

## E. Role-specific results (critical checks, judged conditionally: the intent carries the concept; what did the compiler do)
### Role 1
| id | check | results over 5 runs | gap type |
|---|---|---|---|
| R1-01 | Path A vs Path B structure is preserved or routed (path logic must not be flattened into one AND) | FAIL×5 | COMPILER LOGIC |
| R1-02 | Path-specific geography is preserved or routed | FAIL×5 | COMPILER LOGIC |
| R1-03 | Path-specific requirements (skills, experience, seniority, domain inside a path) are preserved or routed | FAIL×5 | COMPILER LOGIC |
| R1-04 | Power Query waiver on Path A is honoured (global Power Query must not bind Path A) | FAIL×5 | COMPILER LOGIC |
| R1-05 | Path B 6+ years is enforced for Path B only (not global, not dropped) | FAIL×5 | COMPILER LOGIC |
| R1-06 | Semantic security-operations / SOC exclusion is routed (and never turned into a company or title filter) | FAIL×5 | COMPILER LOGIC |
| R1-07 | Security-firm qualifier is routed | FAIL×5 | COMPILER LOGIC |
| R1-08 | Leadership = people OR technical is routed | PARTIAL×4, FAIL×1 | COMPILER LOGIC |
| R1-09 | Domain preference (Cyber Incident Review / Data Breach Analysis) is routed | PARTIAL×4, FAIL×1 | COMPILER LOGIC |
| R1-10 | India country is routed to a country filter or audited | FAIL×5 | COMPILER LOGIC |
| R1-11 | Remote-allowed is routed or audited | FAIL×5 | COMPILER LOGIC |

R1-01 to R1-03, R1-10, R1-11: all path atoms and all geography are dropped, so path logic is flattened (the compiled plan has no path structure and the path-only requirements do not exist in it). R1-04 FAIL in every run: the waiver has no destination, and Power Query exists only as path atoms (Path B `required` in all five runs, plus Path A `preferred` in run 4), so it is absent from every compiled plan. R1-05 FAIL in every run: run 1 binds Path A to 6+ years globally, runs 2-5 drop it. R1-06/07: the security-operations exclusion and the security-firm qualifier have no destination, and **no negative company or title leaf is created** (that guard passes). R1-08/09 PARTIAL: only where the model restated the meaning as an evidence signal.

### Role 2
| id | check | results over 5 runs | gap type |
|---|---|---|---|
| R2-01 | Working / hands-on distinction reaches the plan or the downstream checklist | FAIL×5 | COMPILER LOGIC |
| R2-02 | Advanced proficiency (Python, Java) reaches the plan or the downstream checklist [SYNTHETIC OVERLAY: stored Role 2 intents pre-date `advanced`] | FAIL×5 | COMPILER LOGIC |
| R2-03 | Hybrid work mode is routed or audited [SYNTHETIC OVERLAY: stored Role 2 intents pre-date `work_mode`] | FAIL×5 | COMPILER LOGIC |
| R2-04 | Semantic role / work-type requirements (IC engineer, client-problem solution design, POCs, Staff-level) are routed | PASS×5 | — |
| R2-05 | Unknown 'Staff' seniority is carried verbatim and never silently becomes another level [SYNTHETIC OVERLAY] | PASS×5 | — |
| R2-06 | A comparison title ('more like a Forward Deployed Engineer') must not become a hard target title | FAIL×5 | PROVENANCE / VALIDATION |
| R2-07 | Relationship semantics: a required skill becomes a hard filter only where the source states current use | FAIL×5 | PROVENANCE / VALIDATION |

R2-02/R2-03/R2-05 use the labelled synthetic overlay. R2-05 PASS: "Staff" is carried verbatim (the compiler does not invent a level, and no taxonomy for Staff was added). R2-04 PASS: the IC / solution-design / proof-of-concept requirements are evidence signals and reach the downstream checklist.

### Role 3
| id | check | results over 5 runs | gap type |
|---|---|---|---|
| R3-01 | Hyderabad is enforced as a location filter | PASS×5 | — |
| R3-02 | Hybrid work mode does not disappear | FAIL×5 | COMPILER LOGIC |
| R3-03 | 8-12 years is enforced (both bounds) | PASS×5 | — |
| R3-04 | Advanced Excel: the skill AND its depth are routed | FAIL×5 | COMPILER LOGIC |
| R3-05 | Working-knowledge Power BI: the requirement and its depth are routed | PARTIAL×5 | COMPILER LOGIC |
| R3-06 | Named companies stay preferences and are never hard company filters | PASS×5 | — |
| R3-07 | Semantic audit / tax / bookkeeping exclusion is routed (not a company or title filter) | FAIL×5 | COMPILER LOGIC |
| R3-08 | 'Senior Manager' role identity is carried (level verbatim or Manager kept in the title) | PASS×5 | — |
| R3-09 | Education values are provider-usable strings (observation only: the provider is not called offline) | OBSERVATION×5 | TAXONOMY |

R3-04 FAIL: Excel is routed (as `Microsoft Excel`) but `advanced` is dropped. R3-05 PARTIAL: the Power BI group is routed by name, and its depth reaches the Judge only as the intake's untyped "Working knowledge of Power BI…" signal. R3-06 PASS: all 30 company atoms are PREFERENCE_CONTEXT and there are 0 company leaves.

## F. Compiler vs capability map vs taxonomy vs provenance vs intent-representation failures
| issue | cause | evidence |
|---|---|---|
| Nine extension fields are not read; their atoms reach nothing | **COMPILER LOGIC** (the intent carries the information) | read-set + ablation, 272 atoms |
| Path-only atoms vanish; global atoms bind every path; no path structure | **COMPILER LOGIC** | section D1, R1-01..05 |
| Multi-entry location drops state and country; countries-only and remote produce nothing | **COMPILER LOGIC** | location probes |
| `context` strength acts as `required`; experience/location ignore strength; preferred education leaves no row | **COMPILER LOGIC** (pre-existing; independent of the extension) | strength sweep; 35 Role 1 atoms |
| `work_mode` reaches nothing although the capability map already says "no work_mode filter -> disclose context-only" | **COMPILER LOGIC** (the capability map is right; nothing consults it for this field) | capability notes; R3-02 |
| Required `any` skills never route to the provider: their probe field `experience.employment_details.description` is not in the capability map, so it resolves to the unverified default (`disclose`) while the audit row says `downstream_evidence` | **CAPABILITY MAP** | capability notes; 12 leaves in Role 3 |
| An analogy title, an unsupported `current`, an inferred state each become hard filters | **PROVENANCE / VALIDATION** (the compiler cannot tell what is authoritative; `basis` is unread; the frozen validators exist but run only at intake) | R2-06, R2-07, R3-01 |
| Omitted relationship and explicit `current` are the same value after validation | **INTENT REPRESENTATION** (the production default is `current`; there is no "unspecified") | section G |
| Only two role families have taxonomy entries; degree surface forms cover three tech degrees; `staff`/`senior manager` unknown to `seniority.json` | **TAXONOMY** | titles probe; seniority probe; R3-09 |
| The seniority row claims enforcement by an admission gate that reads the legacy `intent.role.seniority`, not the compiled plan | NOT VERIFIED END TO END (a wiring claim, outside this experiment) | `candidate_evidence_builder` reads `intent.role.seniority` |

No row is solved by adding provider semantics to `StructuredHiringIntent`, and none needs it.

## G. Temporal relationship risk (HIGH PRIORITY DESIGN GAP)
Production `SkillReq.relationship` defaults to `"current"` (also `SkillAnyOf`, `CompanyScale`; `CompanyReq` defaults to `any`). The compiler consumes it in `_skill_fields`: `current` -> current-role description, headline, summary; `past` -> past description and title; anything else -> any-time fields.

| question | answer (measured, unchanged compiler) |
|---|---|
| **A.** explicit `current`, required | provider hard filter: an OR over `current.description`, `headline`, `summary` (3 leaves per skill, 6 per group), capability `enforce_but_not_verifiable` |
| **B.** explicit `past` / `any`, required | `past`: hard filter over past description and title (2 leaves). `any`: **no hard leaf**; routed to downstream evidence (capability token `disclose`) |
| **C.** omitted | validated to `current`: identical output |
| **D.** does omission default to `current`? | **Yes.** After validation, an omitted relationship and an explicit `current` are equal (`model_dump` equal), compile to identical output, and have the **same `intent_hash`**. Pydantic's `model_fields_set` could tell them apart, but nothing persisted or compiled uses it |
| **E.** can that create an unintended hard filter? | **Yes.** Every required skill or group whose relationship is omitted becomes a hard AND of a recall-limited text OR (current descriptions are sparsely populated per the capability map) |

**The compiler cannot distinguish "the source did not specify a temporal relationship" from "the source explicitly requires current".** Recorded as a HIGH PRIORITY DESIGN GAP, with two separate channels:
1. **Omission channel (latent):** the stored raw model outputs show `relationship` was omitted on **0 of 343** skill / group / company atoms (Role 1 0/42, Role 2 0/214, Role 3 0/87). Exposure if it had been omitted on every skill and group:

| intent | hard leaves as compiled | hard leaves if `relationship` had been omitted on every skill and group |
|---|---|---|
| R1/1 | 8 | 14 |
| R1/2 | 1 | 16 |
| R1/3 | 1 | 13 |
| R1/4 | 1 | 16 |
| R1/5 | 1 | 16 |
| R2/1 | 46 | 163 |
| R2/2 | 46 | 160 |
| R2/3 | 31 | 142 |
| R2/4 | 19 | 160 |
| R2/5 | 34 | 157 |
| R3/1 | 12 | 54 |
| R3/2 | 12 | 54 |
| R3/3 | 12 | 57 |
| R3/4 | 12 | 54 |
| R3/5 | 12 | 57 |

2. **Unsupported-assertion channel (observed):** the model wrote `current` without source support in Role 2 (prompt_v3): 10, 10, 5, 1, 6 required skills became hard filters. The same failure is now 0 in Role 3 (prompt_v4 rule 23 plus the validator held), but only because of intake-side fixes: nothing at the compiler boundary prevents it.

Gap types: INTENT REPRESENTATION (no "unspecified" value; the production default asserts `current`) and PROVENANCE / VALIDATION (the compiler hard-filters on `current` without checking `basis`). Nothing was changed.

## H. Recommended smallest compiler changes (RECOMMENDATIONS; none implemented, none required to produce this evidence)
In priority order, each with the evidence that motivates it:
1. **No atom without a destination.** Emit an audit row for every extension atom: `semantic_exclusions` and `domain` (by strength) as downstream rows, `leadership` / `alternatives` appended to the seniority row, `proficiency` as a qualifier on the skill row and in its checklist text, `countries` / `remote` / `work_mode` as location rows, `reconciliations` as decision-record rows. This needs no provider change and takes the non-path drops to 0. (272 atoms)
2. **Paths.** The existing compiler already compiles a path's effective view correctly (section D1). The smallest safe change is one plan per path (an OR) instead of one flat plan; until then, a non-empty `sourcing_paths` should produce an UNRESOLVED row per path and must not let path-only atoms vanish silently. (Role 1)
3. **Strength.** Treat `context` like `preferred` everywhere; honour `preferred` / `context` for experience, location and education; always emit an education row. (strength sweep; 35 atoms)
4. **Geography.** Compile `countries` to a country leaf; keep state and country per entry (an OR of AND-groups) instead of cities only. (location probes; Role 1)
5. **A provenance gate at the compiler boundary.** Run the frozen intake validators (`title_analogy`, `unsupported_current_relationship`) before compile, and never turn an `inferred` sub-value into a hard leaf. (R2-06, R2-07, R3-01)
6. **Relationship (an architecture decision, not a compiler tweak).** Make "unspecified" representable (default to no relationship / `any`, not `current`) and compile `current` as a hard filter only where the source supports it. (section G)
7. **Capability map.** Add the any-time description field with its true status so `any` skills route deliberately, and have `work_mode` consult its existing "disclose" entry.
8. **Taxonomy (out of scope for the compiler):** role families, degree surface forms, `staff` / `senior manager` entries.

## I. What should route to the provider
Title / role family (taxonomy-expanded, never an analogy); required experience (global, or scoped to the path that states it); required education (normalized); location entries and country-wide areas (per path); required `current` or `past` skills ONLY where the source states the time scope; explicit company and title exclusions; required companies.

## J. What should route to downstream evidence / the Judge
Skill proficiency (with the skill); semantic exclusions (as a negative check, never a company/title filter); required domain; leadership kinds and level alternatives; work mode and remote allowance (no provider filter exists); required skills whose time scope is `any`; evidence signals with their tier; unresolved reconciliations; the whole path structure where a provider filter cannot express it.

## K. What should remain preference / context
Preferred companies (Role 3: 30/30 correct today), preferred education and qualifications, preferred skills, preferred and context domain, context-strength evidence, preferred experience or location, preferred seniority.

## L. What should be normalized deterministically
City aliases (exists), degree surface forms beyond three tech degrees, taxonomy title expansion (exists for two families), location string parsing with an explicit `inferred` mark for any sub-value the source did not state, typographic apostrophes and "related discipline" style filler in education, unknown levels carried verbatim (exists).

## Compact table: CONCEPT | ROLE | CURRENT FATE | EXPECTED FATE | GAP TYPE
Gap type is "—" where the current fate is acceptable. Expected fates were fixed before the run (`CONTRACT_EXPECTATIONS.md` section 2).

| CONCEPT | ROLE | CURRENT FATE | EXPECTED FATE | GAP TYPE |
|---|---|---|---|---|
| `company [preferred]` | R3 | PREFERENCE_CONTEXT×30 | PREFERENCE_CONTEXT | — |
| `domain (in path) [preferred]` | R1 | SILENTLY_DROPPED×8 | PREFERENCE_CONTEXT / VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `domain (in path) [required]` | R1 | SILENTLY_DROPPED×3 | VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `domain [context]` | R1 | SILENTLY_DROPPED×10 | PREFERENCE_CONTEXT / VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `domain [context]` | R2 | SILENTLY_DROPPED×3 | PREFERENCE_CONTEXT / VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `domain [context]` | R3 | SILENTLY_DROPPED×5 | PREFERENCE_CONTEXT / VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `domain [preferred]` | R1 | SILENTLY_DROPPED×3 | PREFERENCE_CONTEXT / VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `domain [preferred]` | R3 | SILENTLY_DROPPED×10 | PREFERENCE_CONTEXT / VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `domain [required]` | R2 | SILENTLY_DROPPED×13 | VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `domain [required]` | R3 | SILENTLY_DROPPED×5 | VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `education.degree [preferred]` | R1 | SILENTLY_DROPPED×5 | PREFERENCE_CONTEXT | COMPILER LOGIC |
| `education.degree [required]` | R2 | ENFORCED×10 | ENFORCED / NORMALIZED | — |
| `education.degree [required]` | R3 | ENFORCED×5 | ENFORCED / NORMALIZED | TAXONOMY: literal degree string (R3-09) |
| `education.stream [preferred]` | R1 | SILENTLY_DROPPED×30 | PREFERENCE_CONTEXT | COMPILER LOGIC |
| `education.stream [required]` | R2 | ENFORCED×20 | ENFORCED / NORMALIZED | — |
| `education.stream [required]` | R3 | ENFORCED×25 | ENFORCED / NORMALIZED | TAXONOMY: literal 'Related discipline' stream (R3-09) |
| `evidence_signal [context]` | R1 | VERIFIED_DOWNSTREAM×12 | PREFERENCE_CONTEXT / VERIFIED_DOWNSTREAM | — |
| `evidence_signal [context]` | R3 | VERIFIED_DOWNSTREAM×54 | PREFERENCE_CONTEXT / VERIFIED_DOWNSTREAM | — |
| `evidence_signal [preferred]` | R1 | VERIFIED_DOWNSTREAM×6 | PREFERENCE_CONTEXT / VERIFIED_DOWNSTREAM | — |
| `evidence_signal [preferred]` | R3 | VERIFIED_DOWNSTREAM×10 | PREFERENCE_CONTEXT / VERIFIED_DOWNSTREAM | — |
| `evidence_signal [required]` | R1 | VERIFIED_DOWNSTREAM×55 | PREFERENCE_CONTEXT / VERIFIED_DOWNSTREAM | — |
| `evidence_signal [required]` | R2 | VERIFIED_DOWNSTREAM×116 | PREFERENCE_CONTEXT / VERIFIED_DOWNSTREAM | — |
| `evidence_signal [required]` | R3 | VERIFIED_DOWNSTREAM×30 | PREFERENCE_CONTEXT / VERIFIED_DOWNSTREAM | — |
| `experience.max [required]` | R3 | ENFORCED×5 | ENFORCED | — |
| `experience.min (in path) [required]` | R1 | SILENTLY_DROPPED×4 | ENFORCED | COMPILER LOGIC |
| `experience.min [required]` | R1 | ENFORCED×1 | ENFORCED | — |
| `experience.min [required]` | R2 | ENFORCED×5 | ENFORCED | — |
| `experience.min [required]` | R3 | ENFORCED×5 | ENFORCED | — |
| `location.country (in path)` | R1 | SILENTLY_DROPPED×5 | ENFORCED | COMPILER LOGIC |
| `location.entry (in path) [required]` | R1 | SILENTLY_DROPPED×10 | ENFORCED / NORMALIZED | COMPILER LOGIC |
| `location.entry [required]` | R2 | ENFORCED×5 | ENFORCED / NORMALIZED | — |
| `location.entry [required]` | R3 | ENFORCED×5 | ENFORCED / NORMALIZED | PROVENANCE / VALIDATION: the inferred state is enforced as a hard AND (R3-01) |
| `location.remote (in path)` | R1 | SILENTLY_DROPPED×5 | PREFERENCE_CONTEXT / VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `location.work_mode` | R3 | SILENTLY_DROPPED×5 | VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `provenance.basis` | R1 | SILENTLY_DROPPED×5 | DROPPED_WITH_JUSTIFICATION / VERIFIED_DOWNSTREAM | PROVENANCE / VALIDATION |
| `provenance.basis` | R2 | SILENTLY_DROPPED×5 | DROPPED_WITH_JUSTIFICATION / VERIFIED_DOWNSTREAM | PROVENANCE / VALIDATION |
| `provenance.basis` | R3 | SILENTLY_DROPPED×5 | DROPPED_WITH_JUSTIFICATION / VERIFIED_DOWNSTREAM | PROVENANCE / VALIDATION |
| `reconciliation` | R1 | SILENTLY_DROPPED×28 | DROPPED_WITH_JUSTIFICATION / UNRESOLVED / VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `role_archetype` | R1 | SILENTLY_DROPPED×5 | DROPPED_WITH_JUSTIFICATION | COMPILER LOGIC |
| `role_archetype` | R2 | SILENTLY_DROPPED×5 | DROPPED_WITH_JUSTIFICATION | COMPILER LOGIC |
| `role_archetype` | R3 | SILENTLY_DROPPED×5 | DROPPED_WITH_JUSTIFICATION | COMPILER LOGIC |
| `role_family` | R1 | ENFORCED×5 | ENFORCED / NORMALIZED | — |
| `role_family` | R2 | ENFORCED×10, NORMALIZED×5 | ENFORCED / NORMALIZED | PROVENANCE / VALIDATION: analogy title is a hard title leaf in 5/5 runs (R2-06) |
| `role_family` | R3 | ENFORCED×5 | ENFORCED / NORMALIZED | — |
| `semantic_exclusion` | R1 | SILENTLY_DROPPED×15 | VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `semantic_exclusion` | R3 | SILENTLY_DROPPED×5 | VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `seniority.alternatives (in path)` | R1 | SILENTLY_DROPPED×5 | VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `seniority.leadership` | R1 | SILENTLY_DROPPED×2 | VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `seniority.leadership` | R3 | SILENTLY_DROPPED×2 | VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `seniority.leadership (in path)` | R1 | SILENTLY_DROPPED×18 | VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `seniority.value` | R1 | VERIFIED_DOWNSTREAM×1 | VERIFIED_DOWNSTREAM | wiring to the admission gate unverified |
| `seniority.value` | R3 | VERIFIED_DOWNSTREAM×5 | VERIFIED_DOWNSTREAM | wiring to the admission gate unverified; TAXONOMY: 'Senior Manager' reads as `senior` downstream |
| `seniority.value (in path)` | R1 | SILENTLY_DROPPED×9 | VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `skill (in path) [preferred, any]` | R1 | SILENTLY_DROPPED×1 | PREFERENCE_CONTEXT / VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `skill (in path) [required, any]` | R1 | SILENTLY_DROPPED×4 | ENFORCED / VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `skill (in path) [required, current]` | R1 | SILENTLY_DROPPED×1 | ENFORCED / NORMALIZED | COMPILER LOGIC |
| `skill [preferred, any]` | R1 | VERIFIED_DOWNSTREAM×19 | PREFERENCE_CONTEXT / VERIFIED_DOWNSTREAM | — |
| `skill [required, any]` | R1 | VERIFIED_DOWNSTREAM×21 | ENFORCED / VERIFIED_DOWNSTREAM | CAPABILITY MAP: any-time probe field unmapped (never provider-enforceable) |
| `skill [required, any]` | R2 | VERIFIED_DOWNSTREAM×172 | ENFORCED / VERIFIED_DOWNSTREAM | CAPABILITY MAP: any-time probe field unmapped (never provider-enforceable) |
| `skill [required, any]` | R3 | VERIFIED_DOWNSTREAM×47 | ENFORCED / VERIFIED_DOWNSTREAM | CAPABILITY MAP: any-time probe field unmapped (never provider-enforceable) |
| `skill [required, current]` | R1 | ENFORCED×2 | ENFORCED / NORMALIZED | — |
| `skill [required, current]` | R2 | ENFORCED×32 | ENFORCED / NORMALIZED | PROVENANCE / VALIDATION: 32 of 32 `current` skills have no source support (R2-07) |
| `skill.proficiency` | R1 | SILENTLY_DROPPED×20 | VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `skill.proficiency` | R2 | SILENTLY_DROPPED×109 | VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `skill.proficiency` | R3 | SILENTLY_DROPPED×5 | VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `skill.proficiency (in path)` | R1 | SILENTLY_DROPPED×6 | VERIFIED_DOWNSTREAM | COMPILER LOGIC |
| `skill_any_of [required, any]` | R2 | VERIFIED_DOWNSTREAM×10 | ENFORCED / VERIFIED_DOWNSTREAM | — |
| `skill_any_of [required, any]` | R3 | VERIFIED_DOWNSTREAM×10 | ENFORCED / VERIFIED_DOWNSTREAM | — |
| `sourcing_path (in path)` | R1 | SILENTLY_DROPPED×10 | ENFORCED / UNRESOLVED / VERIFIED_DOWNSTREAM | COMPILER LOGIC |

## Disclosures
- Expected fates, atom granularity, the META/RECORD classification and the check definitions are mine and unreviewed.
- The stored intents are the evidence base as they are; intake errors are labelled where they matter.
- Role 2 `advanced` / `work_mode` / `Staff` use a labelled synthetic overlay; Role 2 stored intents are prompt_v3.
- No model, CrustData, Harvest, retrieval, provider, production, compiler, schema, prompt or taxonomy change was made. The unchanged compiler is pinned by hash.
- Tests: `tests/test_experiment_compiler_contract.py` pins the unchanged files and each baseline fact.

**Stopped here. Waiting for architecture review.**
