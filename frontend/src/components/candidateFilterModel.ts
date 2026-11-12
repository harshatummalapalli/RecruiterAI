// Pure filter model for the candidate filter rail — no React, so it's unit-testable
// in a plain node environment. The CandidateFilters component imports and re-exports these.
import type { DiscoveryCandidate } from '../models/discovery'

export type FacetState = 'include' | 'exclude'

// How the already-ranked list is ordered. 'ranked' leaves the engine's order
// (default); 'core' puts the most core-requirement evidence first.
export type CandidateSort = 'ranked' | 'core'

export type CandidateFilterState = {
  // value -> include|exclude. Absent = neutral (no constraint).
  companyType: Record<string, FacetState>
  seniority: Record<string, FacetState>
  // recently_started is a single boolean signal, so it's a tri-state of its own.
  recency: 'any' | 'include' | 'exclude'
  // "Open to work" (self-reported, from Harvest) — a soft triage signal, same tri-state.
  openToWork: 'any' | 'include' | 'exclude'
}

export const EMPTY_FILTERS: CandidateFilterState = { companyType: {}, seniority: {}, recency: 'any', openToWork: 'any' }

export function filtersActive(state: CandidateFilterState): boolean {
  return (
    Object.keys(state.companyType).length > 0 ||
    Object.keys(state.seniority).length > 0 ||
    state.recency !== 'any' ||
    state.openToWork !== 'any'
  )
}

// A candidate's facet values, read the same way the record card's AttributeTags reads them.
export function companyTypeOf(c: DiscoveryCandidate): string | null {
  const t = c.attributes?.company_type
  return t && t !== 'Unknown' ? t : null
}
export function seniorityOf(c: DiscoveryCandidate): string | null {
  return c.attributes?.ic_level || c.attributes?.seniority_band || null
}
export function recentlyStartedOf(c: DiscoveryCandidate): boolean {
  return Boolean(c.attributes?.recently_started)
}
// null = unknown (most candidates): an "include" only keeps confirmed true, an "exclude"
// only drops confirmed true — unknowns are never force-dropped by this soft signal.
export function openToWorkOf(c: DiscoveryCandidate): boolean | null {
  return c.openToWork
}

// Does a value pass a value-keyed facet map? If any value is set to "include",
// the candidate must match one of them; a value set to "exclude" rejects a
// match. Neutral values impose nothing.
export function passesFacet(value: string | null, map: Record<string, FacetState>): boolean {
  const includes = Object.entries(map).filter(([, s]) => s === 'include').map(([v]) => v)
  const excludes = Object.entries(map).filter(([, s]) => s === 'exclude').map(([v]) => v)
  if (value && excludes.includes(value)) return false
  if (includes.length > 0) return value != null && includes.includes(value)
  return true
}

export function candidatePassesFilters(c: DiscoveryCandidate, state: CandidateFilterState): boolean {
  if (!passesFacet(companyTypeOf(c), state.companyType)) return false
  if (!passesFacet(seniorityOf(c), state.seniority)) return false
  if (state.recency === 'include' && !recentlyStartedOf(c)) return false
  if (state.recency === 'exclude' && recentlyStartedOf(c)) return false
  if (state.openToWork === 'include' && openToWorkOf(c) !== true) return false
  if (state.openToWork === 'exclude' && openToWorkOf(c) === true) return false
  return true
}

// neutral -> include -> exclude -> neutral
export function nextFacet(current: FacetState | undefined): FacetState | undefined {
  if (current === undefined) return 'include'
  if (current === 'include') return 'exclude'
  return undefined
}

const SENIORITY_RANK = ['Distinguished', 'Fellow', 'Principal', 'Staff', 'Architect', 'Lead', 'Senior', 'Mid', 'Junior']

export function sortValues(dimension: 'companyType' | 'seniority', values: string[]): string[] {
  if (dimension === 'seniority') {
    return [...values].sort((a, b) => {
      const ia = SENIORITY_RANK.indexOf(a)
      const ib = SENIORITY_RANK.indexOf(b)
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib) || a.localeCompare(b)
    })
  }
  return [...values].sort((a, b) => a.localeCompare(b))
}
