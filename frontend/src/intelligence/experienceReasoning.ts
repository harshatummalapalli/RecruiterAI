// Stage 4 of the Recruiter Reasoning Pipeline: Experience Reasoning.
//
// A JD's years-of-experience signal can conflict with itself (e.g. "3+
// years" in the summary, "8-10 years" in the requirements). This stage
// picks the first-mentioned range as the working value — consistent with
// how the rest of the pipeline reads a JD top-to-bottom — but flags the
// conflict so Constraint Validation / Clarification Generation can ask the
// recruiter to resolve it rather than silently guessing.

import { detectAllExperienceRanges, extractExperience } from '../screens/localJdExtraction'
import type { ExperienceProfile } from './types'

export function reasonAboutExperience(text: string): ExperienceProfile {
  // extractExperience covers a broader set of phrasings (including a bare
  // "5 years experience" with no "+" or range) than detectAllExperienceRanges,
  // which exists specifically to catch conflicts — so the two are combined
  // rather than one replacing the other.
  const primary = extractExperience(text)
  const ranges = detectAllExperienceRanges(text)

  if (primary.minimumYears === null && primary.maximumYears === null) {
    return { minimumYears: null, maximumYears: null, conflicting: false, confidence: 0.3 }
  }

  return {
    minimumYears: primary.minimumYears,
    maximumYears: primary.maximumYears,
    conflicting: ranges.length > 1,
    confidence: ranges.length > 1 ? 0.4 : 0.9,
  }
}
