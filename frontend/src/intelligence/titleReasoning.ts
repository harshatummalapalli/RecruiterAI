// Stage 3 of the Recruiter Reasoning Pipeline: Title Reasoning.
//
// Takes the extracted primary title and seniority and reasons about
// everything a Search Brief needs around it: equivalent titles, past
// titles (an earlier career stage on the same ladder), and the default
// exclusion list (leadership titles that shouldn't show up as candidates
// for an IC search). Confidence reflects how much was actually extracted
// vs. how much this stage had to reason its way to.

import { expandTitle } from './titleIntelligence'
import { DEFAULT_EXCLUDED_TITLES, type TitleProfile } from './types'

export function reasonAboutTitle(primaryTitle: string | null, seniority: string | null): TitleProfile {
  const title = primaryTitle ?? ''
  const expansion = expandTitle(title, seniority ?? '')

  const confidence = title ? (seniority ? 0.9 : 0.6) : 0.2

  return {
    primaryTitle: title,
    equivalentTitles: expansion.equivalentTitles,
    pastTitles: expansion.pastTitles,
    excludedTitles: [...DEFAULT_EXCLUDED_TITLES],
    seniority,
    confidence,
  }
}
