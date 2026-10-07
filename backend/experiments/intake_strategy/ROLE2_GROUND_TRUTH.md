# ROLE 2 — GROUND TRUTH (written BEFORE any model execution)

Cross-role validation of the frozen experimental representation. Role 1 is frozen and untouched. This file is derived ONLY from
`inputs/role2_jd.txt` and `inputs/role2_recruiter_brief.txt` (verbatim). Nothing here was informed by a model output, and no
requirement is added that the sources do not state. Where the sources are ambiguous, the ambiguity is recorded together with the
set of answers I will accept, so that no judgement is made after seeing a result.

Sources: the JD is a conventional list (Summary, Job Responsibilities, Requirements / Skills). The brief is ONE paragraph:

> Look for an IC Engineer who understands how to design a solution for a client problem, more like a Forward Deployed Engineer
> who understands the client requirements, builds POC's, designs the system. Also, he would be working closely with the existing
> teams on enhancing the existing products and features. Location is Hyderabad and need someone who can work on a Hybrid basis.

**Notable fact:** neither source contains any preference wording ("preferred", "nice to have", "ideally", "a plus"). Every JD
requirement is stated as a requirement; the only weakening wording is "Familiarity with…", "or similar", "and/or", "such as",
"including", and "related". So an atom the model marks `preferred` is a *weakening* of a stated requirement, not fidelity.

## 1. Role identity
- Title (JD): **Staff** Software Engineer / Solution Architect, "AI Solutions". Two titles joined by a slash in one role.
- Hands-on engineering role (JD: "This is a hands-on engineering role"); enterprise-grade applications and AI-driven solutions.
- Brief: an **IC (individual contributor) Engineer**, "more like a Forward Deployed Engineer": understands client requirements, builds
  POCs, designs the system, and works with existing teams on enhancing existing products and features.
- "Forward Deployed Engineer" is an ANALOGY ("more like"). It is not a title requirement and names no company.

## 2. Sourcing strategy
**One** sourcing strategy. There is no "path A / path B", no conditional alternative, no condition under which a requirement or the
geography changes. The slash in the title is one dual-titled role, not two candidate populations. Nothing in either source is
conditional. Therefore **`sourcing_paths` must be empty** and nothing may be path-scoped. (Role 1's paths are NOT a template.)

## 3. Hard requirements (all stated as requirements; JD "Requirements / Skills" unless noted)
| id | requirement | notes |
|---|---|---|
| R1 | 12+ years of experience (in Full Stack Software Development, Solution Design, Data Engineering and AI/ML implementation) | one minimum, `required`, global. The discipline list describes the experience; whether 12 years is per discipline or in total is ambiguous and must NOT be turned into several experience records |
| R2 | Bachelor's or Master's degree in Computer Science, Information Technology, Software Engineering, or a related field | `required` (nothing weakens it); degrees OR, streams OR |
| R3 | Python AND Java, "advanced proficiency", building APIs, services, distributed systems | both required (AND, not OR) |
| R4 | Generative AI solutions implemented and deployed in production, "hands-on" | required |
| R5 | Strong understanding of LLMs, RAG architectures, Agentic AI, Prompt Engineering, MCP, A2A | six named items, required |
| R6 | NLP frameworks / ML libraries "such as TensorFlow, PyTorch, scikit-learn, or similar" | OR group; all three named options kept |
| R7 | Cloud platforms "Azure and/or AWS" | OR group; both options kept; not an AND |
| R8 | DevOps tools and practices "including CI/CD pipelines, Terraform, AKS, EKS, GitHub Actions, containerized deployments" | required; the named tools are examples ("including") |
| R9 | Modern UIs "using React, Bootstrap, and related frameworks" | required |
| R10 | Snowflake, Databricks, "and modern data platforms" | required |
| R11 | Strong understanding of Data Integration, ETL, Data Quality, Data Discovery, enterprise data management | required |
| R12 | Experience integrating third-party and enterprise APIs | required |
| R13 | Strong hands-on software engineering background; enterprise-scale applications; solution design / architecture reviews | required (evidence-type) |
| R14 | Strong analytical, problem-solving, troubleshooting; excellent communication and stakeholder management | required (soft; evidence-type) |
| R15 | Brief: IC Engineer; designs solutions for a client problem; builds POCs; works with existing teams on existing products | recruiter-stated sourcing profile, added by the brief |
| R16 | Brief: location Hyderabad; Hybrid working basis | recruiter-stated, added by the brief; the JD has no location |

**Weaker wording in the JD (accepted either `required` or `preferred`, because the JD itself weakens it):** "Familiarity with Azure
DevOps, Jira" and "Familiarity with metadata management tools and data governance concepts".

## 4. Preferred requirements
**None stated.** Any `preferred` atom must be a faithful reading of "Familiarity" wording, otherwise it is a weakened requirement.

## 5. Exclusions
**None stated** in either source. No work type, company, title or background is excluded. "IC Engineer" is a positive identity; "not
a people manager" is an inference, not a recruiter-stated exclusion. So `exclusions` and `semantic_exclusions` must be empty.

## 6. Geography
- City **Hyderabad** (brief). No state or country is stated; `Hyderabad, Telangana, India` is an accepted normalisation of the
  city (the prompt asks for City, State, Country), but `countries` must be EMPTY (no country-wide area is stated).
- **Hybrid** working basis (brief). A work mode, not remote work. `remote` must NOT be `allowed`.
- No radius.

## 7. Experience
12+ years, `required`, global (R1). No maximum. Single record.

## 8. Seniority
- "Staff" (JD title). Accepted: `Staff` in `seniority.value`, strength `required` or `preferred`; or absent (title level dropped:
  PARTIAL, a stated fact lost).
- NOT acceptable (hard seniority invented from ordinary responsibility language): Lead, Principal, Senior, Director, Manager as the
  value, any `alternatives`, or any `leadership` entries. The JD's "Provide technical leadership, mentor team members" is a
  *responsibility*; the Requirements section asks for no leadership, and the brief says IC. It is context at most.

## 9. Skill proficiency (what the sources actually say about depth)
| items | source wording | accepted `proficiency` |
|---|---|---|
| Python, Java | "Advanced proficiency" | `hands_on` or null. **"Advanced" cannot be stated by the current enum** (see section 14) |
| Generative AI in production | "Hands-on experience implementing and deploying" | `hands_on` or null |
| Azure DevOps, Jira; metadata management / data governance | "Familiarity" | `working_knowledge` or null |
| every other skill (cloud, ML libraries, DevOps tools, React/Bootstrap, Snowflake/Databricks, data topics, APIs, LLM/RAG/Agentic/MCP/A2A understanding) | "Experience with…", "Strong understanding of…" (no depth scale) | **null only**: any depth is invented |

`hands_on` on a "Familiarity" item overstates it (failure). `working_knowledge` on Python/Java understates "advanced" (failure).

## 10. Company / background preferences
**None.** No company, company scale, target employer or industry is named. "Forward Deployed Engineer" is an analogy, not a company
or a title. `companies`, `company_scale` must be empty/null. Enterprise / SaaS appear only as context of the work, not as a
background requirement.

## 11. Alternatives (genuine OR groups in the sources)
- TensorFlow / PyTorch / scikit-learn / "similar" (R6)
- Azure and/or AWS (R7)
- degrees: Bachelor's or Master's; streams CS / IT / Software Engineering / related (R2)
- titles: Software Engineer / Solution Architect (one role, two stated titles)
Every other list in the JD is an AND of stated items. Converting an OR into an AND (e.g. Azure AND AWS required separately) or an AND
into an OR (e.g. Python or Java) is a fidelity failure.

## 12. Conditional paths / conditional anything
None: no conditional requirements, geography, exclusions or alternatives. Any path-scoped atom is invented.

## 13. Recruiter-vs-JD reconciliations (frozen source-priority rule)
- **Added by the brief** (JD silent): location Hyderabad; Hybrid; the IC / Forward-Deployed-style profile (client problem design,
  POCs, working with existing teams).
- **No JD requirement is waived, narrowed or contradicted** by the brief: the brief mentions no technology, no experience figure and
  no qualification. Hence **no `waived`/`contradicted`/`narrowed` reconciliation about a technology or qualification is legitimate**.
- **IC vs the JD's "technical leadership, mentor team members":** compatible, not contradictory (a Staff IC leads technically and
  mentors). The brief clarifies that the role is not a people-management role. A `narrowed` record about leadership/IC is acceptable,
  not required; a *required* people-management atom would conflict with the brief.
- **No unresolved JD-vs-brief contradiction exists.** A record with action `unresolved` is an invented conflict (reported, PARTIAL).

## 14. Could the CURRENT schema represent the correct meaning? (decided from the schema, before the run)
| meaning | representable? | if the model gets it wrong, classify as |
|---|---|---|
| one strategy, no paths | yes (empty `sourcing_paths`) | EXTRACTION |
| 12+ years; degrees/streams; Staff; Hyderabad; OR groups (`skill_any_of`); required skills | yes | EXTRACTION |
| no exclusions / companies / domain / leadership | yes (leave unused) | EXTRACTION (over-application) |
| "IC Engineer" (individual contributor, not a manager) | **only as an evidence signal**: no typed track | not a failure; recorded as an observation (candidate general concept, not demonstrated necessary) |
| "Advanced proficiency" (Python, Java) | **NO.** `proficiency` has `hands_on` and `working_knowledge` only; there is no value for a depth above hands-on | **REPRESENTATION** (a general concept: an ordinal depth scale). `hands_on` is the nearest accepted value |
| **Hybrid** working basis | **NO.** `location.remote` is `allowed`/`not_allowed`/null; hybrid is neither remote nor on-site | **REPRESENTATION** (a general concept: work mode). Nearest: `not_allowed` (not fully remote) |
| FDE analogy | yes, as an evidence signal (context) | EXTRACTION if hardened into a title/company |
| unsupported or invented atoms | provenance check | PROVENANCE |

Two representation gaps are therefore predicted **before** the run: an ordinal proficiency scale, and a work-mode value. They are
recorded as gaps by schema introspection regardless of what the model emits. No schema change is made in this phase.

## 15. Provenance expectations
- Hyderabad, Hybrid, IC, FDE-style profile, existing products/teams: `recruiter_brief`.
- Every JD requirement (R1-R14), the title (Staff, Software Engineer, Solution Architect): `jd`.
- Nothing `inferred` may be `required`; nothing `approved_knowledge` is needed (a normalisation of "Hyderabad" to "Hyderabad,
  Telangana, India" is the one place the model may lean on world knowledge, and the city head is in the source).

## 16. What counts as a failure (over-application and fidelity), fixed in advance
Over-application (each is a FAIL): an invented second path or any path-scoped structure; an invented exclusion (`exclusions` or
`semantic_exclusions` non-empty); a preference/analogy hardened into a requirement (FDE as a title/company; `hands_on` on a
"Familiarity" item); Role 1 concepts absent here (`leadership`, `alternatives`, `countries`, `remote: allowed`, `domain` at
preferred/required, `semantic_exclusions`, paths); a company filter (`companies`, `company_scale`, a company exclusion); a hard
seniority inferred from responsibility language (a Lead/Principal/Senior/Director value, any `leadership`, a required people-management
atom); an invented proficiency (any depth outside the table in section 9); an invented reconciliation about a technology.
Fidelity failures: a missing stated fact (R1-R16), a wrong number, an OR turned into an AND or the reverse, a requirement weakened to
`preferred`, an extra role-family title not in the JD title.

Smaller and correct beats richer and invented. A required atom that is `inferred` or unsupported by the sources is a PROVENANCE failure.
