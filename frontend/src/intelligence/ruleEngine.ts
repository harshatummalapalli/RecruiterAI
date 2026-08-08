// Reusable recruiter rules, consumed by the Constraint Validation stage
// (constraintValidation.ts). A rule either stays silent (nothing worth
// flagging) or produces a structured ValidationFinding — never freeform UI
// text. Whether a finding actually becomes a question the recruiter sees,
// and in what priority, is entirely the Clarification Generation stage's
// call, not this file's.

import { IC_LADDER } from './knowledge/careerProgression'
import type { ValidationFinding } from './types'

const SENIOR_TITLE_HINT = /\b(staff|principal|director|head of)\b/i
const MAX_REASONABLE_REQUIRED_SKILLS = 8
const SENIOR_MINIMUM_YEARS = 8

/** Over-constrained search: requiring a very long list of skills all at
 * once usually narrows the candidate pool to near zero. */
export function detectOverConstrainedSkills(requiredSkillCount: number): ValidationFinding | null {
  if (requiredSkillCount <= MAX_REASONABLE_REQUIRED_SKILLS) {
    return null
  }
  return {
    id: 'overConstrainedSkills',
    severity: 'medium',
    summary: `${requiredSkillCount} required skills is over-constrained — likely to narrow the candidate pool sharply.`,
    question: {
      id: 'overConstrainedSkills',
      question: `This JD lists ${requiredSkillCount} required skills — requiring all of them at once will narrow the pool sharply. How should we treat them?`,
      options: [
        { value: '__keep__', label: 'Keep all as Required' },
        { value: '__loosen__', label: 'Move the full list to Preferred instead' },
      ],
    },
  }
}

/** Unrealistic combination: a senior-sounding title paired with an
 * entry-level years-of-experience minimum. */
export function detectTitleExperienceMismatch(roleTitle: string | null, minimumYears: number | null): ValidationFinding | null {
  if (!roleTitle || minimumYears === null) {
    return null
  }
  if (!SENIOR_TITLE_HINT.test(roleTitle)) {
    return null
  }
  if (minimumYears >= SENIOR_MINIMUM_YEARS - 2) {
    return null
  }
  return {
    id: 'titleExperienceMismatch',
    severity: 'medium',
    summary: `"${roleTitle}" implies more seniority than a ${minimumYears}+ year minimum.`,
    question: {
      id: 'titleExperienceMismatch',
      question: `"${roleTitle}" usually implies more seniority than ${minimumYears}+ years — which should we go with?`,
      options: [
        { value: '__keep__', label: `Keep ${minimumYears}+ years as written` },
        { value: String(SENIOR_MINIMUM_YEARS), label: `Use a more senior-level minimum (${SENIOR_MINIMUM_YEARS}+ years)` },
      ],
    },
  }
}

/** Contradictory experience requirements — e.g. "3+ years" in the summary
 * and "8-10 years" in the requirements section. */
export function detectExperienceConflict(conflicting: boolean, minimumYears: number | null, maximumYears: number | null): ValidationFinding | null {
  if (!conflicting) {
    return null
  }
  return {
    id: 'experienceRange',
    severity: 'high',
    summary: 'The JD states more than one experience requirement.',
    question: {
      id: 'experienceRange',
      question: 'This JD mentions more than one experience requirement — which is correct?',
      options: [
        {
          value: `${minimumYears ?? ''}-${maximumYears ?? ''}`,
          label: maximumYears ? `${minimumYears}–${maximumYears} years` : `${minimumYears}+ years`,
        },
      ],
    },
  }
}

/** Conflicting locations — the JD names more than one country. */
export function detectLocationConflict(ambiguousCountries: string[]): ValidationFinding | null {
  if (ambiguousCountries.length < 2) {
    return null
  }
  return {
    id: 'locationCountry',
    severity: 'high',
    summary: `The JD names locations in ${ambiguousCountries.length} different countries.`,
    question: {
      id: 'locationCountry',
      question: 'We found locations in multiple countries — how should we search?',
      options: [
        ...ambiguousCountries.map((country) => ({ value: country, label: `Just ${country}` })),
        { value: '__all__', label: 'All of these locations' },
      ],
    },
  }
}

/** Impossible skill combination — a genuinely ambiguous multi-language
 * signal the Technology Understanding stage couldn't resolve confidently. */
export function detectUnresolvedPrimaryTechnology(
  candidates: string[],
  languageSignal: 'polyglot' | 'acceptable-backgrounds' | 'primary-with-support' | 'ambiguous' | null,
): ValidationFinding | null {
  if (candidates.length < 2 || languageSignal !== 'ambiguous') {
    return null
  }
  return {
    id: 'primaryTechnology',
    severity: 'high',
    summary: `${candidates.length} major technologies were mentioned with no clear signal for how they relate.`,
    question: {
      id: 'primaryTechnology',
      question: 'Multiple major technologies were detected — how should we treat them?',
      options: [
        ...candidates.map((candidate) => ({ value: candidate, label: `${candidate} is the primary technology` })),
        { value: '__multiple__', label: 'This is a polyglot role — treat them all as required' },
      ],
    },
  }
}

/** Unclear work mode — both remote and onsite mentioned without an explicit "hybrid". */
export function detectWorkModeConflict(workModes: string[]): ValidationFinding | null {
  if (!workModes.includes('remote') || !workModes.includes('onsite') || workModes.includes('hybrid')) {
    return null
  }
  return {
    id: 'workMode',
    severity: 'medium',
    summary: 'The JD mentions both remote and onsite work with no hybrid clarification.',
    question: {
      id: 'workMode',
      question: 'This JD mentions both remote and onsite work — which applies?',
      options: [
        { value: 'remote', label: 'Remote' },
        { value: 'hybrid', label: 'Hybrid' },
        { value: 'onsite', label: 'Onsite' },
      ],
    },
  }
}

const GENERIC_TITLES = new Set(['ai engineer', 'software engineer', 'engineer', 'developer', 'full stack engineer'])

/** A generic title with no seniority signal anywhere in the JD leaves the
 * experience-level targeting effectively unset. */
export function detectMissingSeniority(roleTitle: string | null, seniority: string | null): ValidationFinding | null {
  if (!roleTitle || seniority || !GENERIC_TITLES.has(roleTitle.trim().toLowerCase())) {
    return null
  }
  return {
    id: 'seniority',
    severity: 'low',
    summary: `"${roleTitle}" is a broad title with no seniority signal in the JD.`,
    question: {
      id: 'seniority',
      question: `"${roleTitle}" is a fairly broad title — what level are you hiring for?`,
      options: IC_LADDER.map((level) => ({ value: level, label: level })),
    },
  }
}
