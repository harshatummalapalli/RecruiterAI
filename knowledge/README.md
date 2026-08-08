# RecruiterAI Knowledge Library

Structured recruiter knowledge, stored as data — not code. Nothing in this
directory is wired into the application yet: it exists so that recruiter
knowledge can be authored, reviewed, and extended by anyone (not just
someone comfortable editing TypeScript), and so the application can
eventually **load** these datasets instead of embedding the same information
inside reasoning code.

This mirrors, and substantially expands on, the knowledge that today lives
hardcoded in `frontend/src/intelligence/knowledge/*.ts`. That TypeScript
knowledge module is the Recruiter Intent Engine's current source of truth;
this directory is the next step — a versionable, engine-agnostic form of the
same kind of knowledge, plus new datasets that don't have a TypeScript
equivalent yet.

## Principle

**Knowledge informs. Reasoning decides.** Every file here describes what's
generally true about roles, technologies, careers, and hiring — never a
specific candidate, JD, or search. Advisory datasets (`hiring-patterns.yaml`,
`common-hiring-mistakes.yaml`) are guidance, not rules: nothing in this
library should ever be read as "reject if X" or "require Y." A future loader
should treat every field here as *evidence to consider*, not a constraint to
enforce.

## Format

YAML, chosen over JSON for this library specifically because it's the more
readable and editable of the two for humans hand-authoring or reviewing
prose-heavy entries (guidance strings, notes, distinctions) — comments are
allowed, trailing commas aren't a trap, and multi-line strings don't need
escaping. Each file is self-contained and independently editable.

Every dataset uses `kebab-case` ids so a future loader can reference entries
across files predictably. Where a dataset overlaps with the current
TypeScript knowledge module's `RoleFamily` union, the entry carries a
`ts_role_family` field with the exact string the TypeScript code already
uses — that's the seam a future loader would use to replace the hardcoded
`RoleFamily` type with data-driven values.

## Datasets

| File | Contents |
|---|---|
| [`role-families.yaml`](./role-families.yaml) | Responsibilities, technology families, career transitions, and related families for each top-level role family. |
| [`career-progressions.yaml`](./career-progressions.yaml) | The IC ladder and the management ladder, kept separate, plus per-family progression notes. |
| [`technology-families.yaml`](./technology-families.yaml) | Technologies grouped into families (relationships only — no ranking, no "best" technology). |
| [`semantic-titles.yaml`](./semantic-titles.yaml) | Groups of titles recruiters treat as interchangeable even though the strings don't match. |
| [`technology-relationships.yaml`](./technology-relationships.yaml) | Typed, pairwise relationships between specific technologies (requires, extends, orchestrates, alternative-to, ...) — more specific than family grouping. |
| [`hiring-patterns.yaml`](./hiring-patterns.yaml) | Advisory guidance recruiters commonly rely on, keyed by role family and/or seniority. |
| [`common-career-transitions.yaml`](./common-career-transitions.yaml) | Cross-family moves (not the IC ladder) — e.g. Backend Engineer → Platform Engineer — with how common each is and why. |
| [`common-hiring-mistakes.yaml`](./common-hiring-mistakes.yaml) | Recurring recruiter/JD pitfalls, for future ambiguity- and over-constraint-detection to draw on. |
| [`ai-engineering-roles.yaml`](./ai-engineering-roles.yaml) | A closer look at the AI-adjacent role cluster (AI Software Engineer, Applied AI Engineer, ML Engineer, Data Scientist, MLOps Engineer, Prompt Engineer) and how recruiters commonly confuse them. |
| [`backend-roles.yaml`](./backend-roles.yaml) | A closer look at the backend-adjacent role cluster (Backend Engineer, API Engineer, Distributed Systems Engineer, Backend SRE). |
| [`platform-roles.yaml`](./platform-roles.yaml) | A closer look at the platform-adjacent role cluster (Platform Engineer, DevOps Engineer, Infrastructure Engineer, SRE). |
| [`data-roles.yaml`](./data-roles.yaml) | A closer look at the data-adjacent role cluster (Data Engineer, Data Scientist, Analytics Engineer, Data Platform Engineer). |

## Non-goals of this milestone

- No loader, parser, or import path was added anywhere in the application.
- No file in `frontend/` or `backend/` was modified.
- Nothing here is consumed at runtime yet — that is deliberately left for a
  future milestone, once there's a chosen loading strategy (bundled at build
  time vs. fetched, and whether it replaces or supplements
  `frontend/src/intelligence/knowledge/*.ts`).
