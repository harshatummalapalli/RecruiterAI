// Test fixtures: build a search response with exactly the evidence a test needs. Used only by tests.
import type { SearchResponse } from '../types'

export type CandidateSpec = {
  name: string
  /** One entry per NON-years core requirement: true = evidenced with a quote. */
  core: boolean[]
  /** The years requirement: absent from the brief (undefined), met, or not met. */
  years?: 'met' | 'not'
  headline?: string
  openToWork?: boolean
  levelFit?: 'aligned' | 'above' | 'below' | 'unclear'
  experienceFloor?: boolean
  state?: 'surfaced' | 'building_context' | 'review_ready'
  judged?: boolean
  /** Quote source: described work (default) or just a listed skill. */
  described?: boolean
  updatedAt?: string
}

export function makeResponse(specs: CandidateSpec[], extra: Partial<SearchResponse> = {}): SearchResponse {
  const states: Record<string, 'surfaced' | 'building_context' | 'review_ready'> = {}
  const candidates = specs.map((spec, index) => {
    const id = `c${index + 1}`
    states[id] = spec.state ?? 'review_ready'
    return {
      candidate_id: id,
      name: spec.name,
      title: 'Backend Engineer',
      company: 'Acme',
      location: 'Toronto, Ontario, Canada',
      raw_data: {},
    }
  })
  const evidence = specs.map((spec) => {
    const judgments =
      spec.judged === false
        ? null
        : [
            ...(spec.years
              ? [
                  {
                    tier: 'core',
                    signal_text: '3+ years of professional experience',
                    verdict: spec.years === 'met' ? 'met' : 'not_evidenced',
                    quote: spec.years === 'met' ? 'About 7 years of professional experience are visible in dated roles.' : undefined,
                    source: 'career dates',
                    strength: 'supporting',
                  },
                ]
              : []),
            ...spec.core.map((shown, i) => ({
              tier: 'core',
              signal_text: `Experience with capability ${i + 1}`,
              verdict: shown ? 'met' : 'not_evidenced',
              quote: shown ? `Built systems using capability ${i + 1} for production` : undefined,
              term: shown ? `capability ${i + 1}` : undefined,
              source: spec.described === false ? 'harvest: skill' : 'harvest: employment description',
              evidence_detail: 'Engineer at Acme',
              strength: spec.described === false ? 'supporting' : 'strong',
            })),
          ]
    return {
      requirement_judgments: judgments,
      headline: spec.headline ?? 'Backend Engineer | Python | Distributed systems',
      open_to_work: spec.openToWork ?? null,
      updated_at: spec.updatedAt ?? null,
      role_alignment: { level_fit: spec.levelFit ?? null, experience_floor: spec.experienceFloor ?? null },
    }
  })
  return {
    provider: 'platform',
    search_id: 'test',
    candidate_count: specs.length,
    candidates,
    explanations: specs.map(() => ({})),
    evidence,
    diagnostics: { funnel: { in_scope: 724204, has_location_scope: true, retrieved: 50, selected: specs.length, read_in_depth: specs.length, presented: specs.length } },
    status: 'complete',
    candidate_states: states,
    ...extra,
  } as unknown as SearchResponse
}
