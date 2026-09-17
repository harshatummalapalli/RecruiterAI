// Canonical types for the Recruiter Intelligence Layer. This file has zero
// dependencies on `models/` or `screens/` — it is the dependency root of the
// whole layer. `models/searchBrief.ts` and `models/clarification.ts` import
// FROM here (and re-export a couple of names for backward compatibility),
// never the other way around. That one-directional dependency is what keeps
// Recruiter Intent "independent of any provider" and independent of the
// Search Brief it eventually produces.

import type { LocationEntry } from '../screens/localJdExtraction'
import type { AiConceptFlags } from './technologyGraph'

export type WorkMode = 'remote' | 'hybrid' | 'onsite'
export type EmploymentType = 'Full-time' | 'Contract' | 'Contract-to-hire' | 'Internship' | 'Part-time'
export type SearchGeography = 'global' | 'country' | 'multiple' | 'radius'

// Kept in sync with backend/services/search_planner.py's
// EXECUTIVE_TITLE_EXCLUSIONS — the backend applies this standing policy
// regardless of what the recruiter edits here, so this is the Search
// Brief's transparent, editable starting point for the same list, not a
// separate source of truth. Deliberately excludes ambiguous IC titles like
// "Principal"/"Staff"/"Lead"/"Engineering Manager".
export const DEFAULT_EXCLUDED_TITLES = [
  'Founder',
  'Co-Founder',
  'CEO',
  'Co-CEO',
  'CTO',
  'CIO',
  'CPO',
  'CAIO',
  'Chief Technology Officer',
  'Chief Information Officer',
  'Chief Product Officer',
  'Chief AI Officer',
  'Chief Data Officer',
  'VP',
  'Vice President',
  'SVP',
  'EVP',
  'Director',
  'Managing Director',
  'Head of Engineering',
  'Head of Technology',
  'Head of Product',
  'Head of Data',
  'Head of AI',
  'Head of ML',
]

export type ClarificationOption = { value: string; label: string }
export type ClarificationQuestion = {
  id: string
  question: string
  options: ClarificationOption[]
}

export type Severity = 'high' | 'medium' | 'low'

/** What a Constraint Validation rule produces: a structured finding, never
 * UI text. Only findings that need a recruiter decision carry a `question` —
 * the Clarification Generation stage decides which findings actually
 * surface, and in what priority order. */
export type ValidationFinding = {
  id: string
  severity: Severity
  summary: string
  question: ClarificationQuestion | null
}

export type RoleFamily =
  | 'Backend Engineer'
  | 'Frontend Engineer'
  | 'Full Stack Engineer'
  | 'AI Software Engineer'
  | 'Applied AI Engineer'
  | 'ML Engineer'
  | 'Data Engineer'
  | 'Data Scientist'
  | 'DevOps Engineer'
  | 'Platform Engineer'
  | 'Security Engineer'
  | 'QA Engineer'
  | 'Mobile Engineer'
  | 'Engineering Manager'
  | 'Unclassified'

export type RoleClassification = {
  roleFamily: RoleFamily
  specialization: string | null
  /** Short, human-readable reasons the classifier picked this family —
   * evidence, not a black-box score. */
  evidence: string[]
  confidence: number
}

export type LanguageSignal = 'polyglot' | 'acceptable-backgrounds' | 'primary-with-support' | 'ambiguous'

export type TechnologyProfile = {
  primaryTechnologies: string[]
  supportingTechnologies: string[]
  /** Technology-family ids (see knowledge/technologyFamilies.ts) referenced
   * by the JD's skills — e.g. ['programming-languages', 'cloud']. */
  technologyFamilies: string[]
  aiConcepts: AiConceptFlags
  languageSignal: LanguageSignal | null
  languageDominant: string | null
  confidence: number
}

export type TitleProfile = {
  primaryTitle: string
  equivalentTitles: string[]
  pastTitles: string[]
  excludedTitles: string[]
  seniority: string | null
  confidence: number
}

export type ExperienceProfile = {
  minimumYears: number | null
  maximumYears: number | null
  conflicting: boolean
  confidence: number
}

export type LocationProfile = {
  geography: SearchGeography
  country: string | null
  locations: LocationEntry[]
  workModes: WorkMode[]
  ambiguousCountries: string[]
  confidence: number
}

export type ConfidenceSection = 'role' | 'technology' | 'title' | 'experience' | 'location' | 'constraints'

/**
 * The canonical, provider-independent representation of what a recruiter is
 * actually trying to hire for. Every downstream feature — Search Brief,
 * Candidate Ranking, Resume Matching, Interview Questions, Outreach,
 * Compensation Benchmarking, Talent Mapping — should read from this instead
 * of re-parsing the JD. See docs/ARCHITECTURE.md for the full pipeline.
 */
export type RecruiterIntent = {
  hiringObjective: string
  roleFamily: RoleFamily
  roleSpecialization: string | null
  seniority: string | null
  hiringConstraints: string[]
  primaryTechnologies: string[]
  supportingTechnologies: string[]
  domainExpertise: string[]
  industryContext: string[]
  companyPreferences: { include: string[]; exclude: string[] }
  candidateBackgroundPreferences: string[]
  locationStrategy: LocationProfile
  experienceStrategy: ExperienceProfile
  employmentModel: EmploymentType[]
  exclusions: { titles: string[]; companies: string[]; skills: string[] }
  ambiguities: string[]
  clarificationsRequired: ClarificationQuestion[]
  /** Advisory recruiter guidance for the matched role family/seniority
   * (knowledge/hiringPatterns.ts) — informs, never filters or validates. */
  hiringGuidance: string[]
  confidenceBySection: Record<ConfidenceSection, number>

  // Full stage outputs, kept on the intent so a downstream consumer can go
  // deeper than the flattened summary fields above without re-running the
  // pipeline itself.
  roleClassification: RoleClassification
  technologyProfile: TechnologyProfile
  titleProfile: TitleProfile
  requiredSkills: string[]
  preferredSkills: string[]
}
