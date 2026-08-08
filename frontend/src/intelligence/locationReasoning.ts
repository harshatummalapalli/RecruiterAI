// Stage 5 of the Recruiter Reasoning Pipeline: Location Reasoning.
//
// Decides which of the four search geographies (Global, Country, Multiple
// Locations, Radius) the JD implies, carries every distinct location that
// survived extraction, and flags when the JD names more than one country —
// the one case genuinely ambiguous enough to ask about.

import { extractLocally, detectAllCountryHints } from '../screens/localJdExtraction'
import type { LocationProfile } from './types'

export function reasonAboutLocation(text: string): LocationProfile {
  const extraction = extractLocally(text)
  const locations = extraction.locations
  const workModes = extraction.workModes

  const ambiguousCountries = Array.from(
    new Set([...locations.map((entry) => entry.country).filter(Boolean), ...detectAllCountryHints(text)]),
  )

  const geography: LocationProfile['geography'] = locations.length > 1 ? 'multiple' : locations.length === 1 ? 'multiple' : 'global'

  return {
    geography,
    country: locations[0]?.country ?? null,
    locations,
    workModes,
    ambiguousCountries,
    confidence: ambiguousCountries.length > 1 ? 0.4 : locations.length > 0 ? 0.85 : 0.3,
  }
}
