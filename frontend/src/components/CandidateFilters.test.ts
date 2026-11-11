import { describe, it, expect } from 'vitest'
import { candidatePassesFilters, filtersActive, EMPTY_FILTERS, type CandidateFilterState } from './candidateFilterModel'
import type { DiscoveryCandidate } from '../models/discovery'

// Minimal candidate: candidatePassesFilters reads only attributes + openToWork.
const cand = (openToWork: boolean | null): DiscoveryCandidate =>
  ({ openToWork, attributes: null } as unknown as DiscoveryCandidate)

const withOpenToWork = (v: CandidateFilterState['openToWork']): CandidateFilterState => ({ ...EMPTY_FILTERS, openToWork: v })

describe('Open to work soft filter', () => {
  it('is neutral by default — every candidate passes', () => {
    expect(filtersActive(EMPTY_FILTERS)).toBe(false)
    for (const c of [cand(true), cand(false), cand(null)]) {
      expect(candidatePassesFilters(c, EMPTY_FILTERS)).toBe(true)
    }
  })

  it('include keeps only confirmed open-to-work (unknowns are dropped, not kept)', () => {
    const f = withOpenToWork('include')
    expect(filtersActive(f)).toBe(true)
    expect(candidatePassesFilters(cand(true), f)).toBe(true)
    expect(candidatePassesFilters(cand(false), f)).toBe(false)
    expect(candidatePassesFilters(cand(null), f)).toBe(false)
  })

  it('exclude drops only confirmed open-to-work — unknowns are never force-dropped', () => {
    const f = withOpenToWork('exclude')
    expect(candidatePassesFilters(cand(true), f)).toBe(false)
    expect(candidatePassesFilters(cand(false), f)).toBe(true)
    expect(candidatePassesFilters(cand(null), f)).toBe(true) // soft signal: unknown stays
  })
})
