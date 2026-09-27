// Test fixtures for roles: a search response with a role, its presentation, and the extras a test needs.
import type { PresentationEntry, RoleState, SearchResponse } from '../types'
import { makeResponse, type CandidateSpec } from './workspaceFixtures'

export function makeRole(extra: Partial<RoleState> = {}): RoleState {
  return { status: 'searching', pause_reason: null, pause_kind: null, can_resume: true, has_feedback: false, exhausted: false, label: { company: 'Northwind', place: 'Toronto' }, ...extra }
}

/** The first `presented` candidates are shown; the rest are reserve. */
export function makeRoleResponse(specs: CandidateSpec[], options: { presented?: number; role?: Partial<RoleState>; extra?: Partial<SearchResponse>; sources?: Record<string, string> } = {}): SearchResponse {
  const presentedCount = options.presented ?? 5
  const presentation: Record<string, PresentationEntry> = {}
  specs.forEach((_, index) => {
    const id = `c${index + 1}`
    presentation[id] = { state: index < presentedCount ? 'presented' : 'reserve', source: options.sources?.[id] ?? 'initial', seen: index < presentedCount, stale: false, batch: index < presentedCount ? 1 : null }
  })
  return makeResponse(specs, {
    role: makeRole(options.role),
    presentation,
    availability: { kind: 'ok', profiles_returned: 110577, retrieved: 50 },
    calibration: { state: 'pending', summary: null, dismissed: [] },
    feedback: {},
    new_candidates: 0,
    retrieval_exhausted: false,
    ...options.extra,
  })
}

export function manySpecs(count: number): CandidateSpec[] {
  return Array.from({ length: count }, (_, index) => ({ name: `Person ${index + 1}`, core: [true, index % 2 === 0, false], years: 'met' as const }))
}
