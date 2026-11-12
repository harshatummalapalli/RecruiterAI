import { describe, expect, it } from 'vitest'
import { reconciliationGroups, type Reconciliation, type ReconciledRequirement } from './intake'

function req(text: string, source: ReconciledRequirement['source'], tier = 'core'): ReconciledRequirement {
  return { text, tier, source, when: 'any', evidence: null, jd_tier: null, hm_tier: null }
}

describe('reconciliationGroups', () => {
  it('splits requirements into both / hm / jd buckets in order', () => {
    const recon: Reconciliation = {
      requirements: [
        req('Python', 'both'),
        req('Agile', 'jd', 'supporting'),
        req('Payments', 'hm'),
        req('Comms', 'jd', 'supporting'),
      ],
      experience: null,
    }
    const { both, hm, jd } = reconciliationGroups(recon)
    expect(both.map((r) => r.text)).toEqual(['Python'])
    expect(hm.map((r) => r.text)).toEqual(['Payments'])
    expect(jd.map((r) => r.text)).toEqual(['Agile', 'Comms'])
  })

  it('handles an empty diff', () => {
    const { both, hm, jd } = reconciliationGroups({ requirements: [], experience: null })
    expect(both).toEqual([])
    expect(hm).toEqual([])
    expect(jd).toEqual([])
  })
})
