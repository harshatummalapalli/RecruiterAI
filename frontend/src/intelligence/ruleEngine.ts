// Part of the Recruiter Intelligence Layer.
//
// Reusable recruiter rules that catch unrealistic or over-constrained
// searches. A rule either stays silent (nothing worth flagging) or produces
// a structured clarifying question — it never renders freeform "guidance
// text" of its own; the UI only ever needs to know how to render a
// ClarificationQuestion, which it already does.

import type { ClarificationQuestion } from '../models/clarification'

const SENIOR_TITLE_HINT = /\b(staff|principal|director|head of)\b/i
const MAX_REASONABLE_REQUIRED_SKILLS = 8
const SENIOR_MINIMUM_YEARS = 8

/** Over-constrained search: requiring a very long list of skills all at
 * once usually narrows the candidate pool to near zero. */
export function detectOverConstrainedSkills(requiredSkillCount: number): ClarificationQuestion | null {
  if (requiredSkillCount <= MAX_REASONABLE_REQUIRED_SKILLS) {
    return null
  }
  return {
    id: 'overConstrainedSkills',
    question: `This JD lists ${requiredSkillCount} required skills — requiring all of them at once will narrow the pool sharply. How should we treat them?`,
    options: [
      { value: '__keep__', label: 'Keep all as Required' },
      { value: '__loosen__', label: 'Move the full list to Preferred instead' },
    ],
  }
}

/** Unrealistic combination: a senior-sounding title paired with an
 * entry-level years-of-experience minimum. */
export function detectTitleExperienceMismatch(roleTitle: string | null, minimumYears: number | null): ClarificationQuestion | null {
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
    question: `"${roleTitle}" usually implies more seniority than ${minimumYears}+ years — which should we go with?`,
    options: [
      { value: '__keep__', label: `Keep ${minimumYears}+ years as written` },
      { value: String(SENIOR_MINIMUM_YEARS), label: `Use a more senior-level minimum (${SENIOR_MINIMUM_YEARS}+ years)` },
    ],
  }
}
