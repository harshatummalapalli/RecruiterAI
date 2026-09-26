import { describe, expect, it } from 'vitest'
import { buildDiscoveryCandidates } from './discovery'
import { approximateCount, buildWorkspaceCandidates, funnelCopy, groupBySection, proofLabel, readFunnel, stableOrder, type CardFacts } from './workspace'
import { makeResponse, type CandidateSpec } from './workspaceFixtures'

function factsFor(spec: CandidateSpec): CardFacts {
  return buildWorkspaceCandidates(buildDiscoveryCandidates(makeResponse([spec])))[0].facts
}

const filled = (n: number, shown: number) => Array.from({ length: n }, (_, i) => i < shown)

describe('evidence dots follow the brief', () => {
  // One dot per NON-years core requirement, for any number of requirements. The years requirement is never a dot.
  it.each([2, 3, 4, 5, 6, 8, 12, 15])('%i core requirements give exactly %i dots', (n) => {
    const facts = factsFor({ name: 'A', core: filled(n, Math.floor(n / 2)), years: 'met' })
    expect(facts.dots).toHaveLength(n)
    expect(facts.dots.filter((dot) => dot.shown)).toHaveLength(Math.floor(n / 2))
    expect(facts.coreTotal).toBe(n)
  })

  it('keeps the brief order: filled and empty dots land where the requirements are', () => {
    const facts = factsFor({ name: 'A', core: [true, true, true, false, true], years: 'met' })
    expect(facts.dots.map((dot) => dot.shown)).toEqual([true, true, true, false, true])
    const eight = factsFor({ name: 'A', core: [true, true, true, true, false, true, false, false], years: 'met' })
    expect(eight.dots.map((dot) => dot.shown)).toEqual([true, true, true, true, false, true, false, false])
  })

  it('never counts the years requirement as a dot, whether it is met or not', () => {
    expect(factsFor({ name: 'A', core: [true, false], years: 'met' }).dots).toHaveLength(2)
    expect(factsFor({ name: 'A', core: [true, false], years: 'not' }).dots).toHaveLength(2)
    expect(factsFor({ name: 'A', core: [true, false] }).dots).toHaveLength(2)
  })

  it('has no dots and is not claimed weak when the brief has no non-years core requirement', () => {
    const facts = factsFor({ name: 'A', core: [], years: 'met' })
    expect(facts.dots).toHaveLength(0)
    expect(facts.section).toBe('unchecked')
    expect(facts.why).toBe('Requirements were not checked against this profile')
  })

  it('does not drop or cap the underlying evidence for a very large brief', () => {
    const facts = factsFor({ name: 'A', core: filled(20, 13), years: 'met' })
    expect(facts.dots).toHaveLength(20)
    expect(facts.shown).toBe(13)
    expect(facts.notProven).toHaveLength(7)
  })
})

describe('coverage copy', () => {
  it('says the count is of core requirements, not "x of y"', () => {
    expect(factsFor({ name: 'A', core: [true, true, true, true], years: 'met' }).why).toBe('4 core requirements shown · 4 in described work')
    expect(factsFor({ name: 'A', core: [true, false, false, false, false], years: 'met' }).why).toBe('1 core requirement shown · 1 in described work')
  })

  it('omits the described-work clause when the proof is only a listed skill', () => {
    expect(factsFor({ name: 'A', core: [true, true, false], years: 'met', described: false }).why).toBe('2 core requirements shown')
  })

  it('states zero evidence plainly, without judging the person', () => {
    const why = factsFor({ name: 'A', core: [false, false, false, false], years: 'met' }).why
    expect(why).toBe('Nothing beyond total years is shown on the profile.')
    expect(why).not.toMatch(/weak|poor|bad|low/i)
  })

  it('does not mention total years when the brief has no years requirement', () => {
    expect(factsFor({ name: 'A', core: [false, false] }).why).toBe('No core requirement is shown on the profile.')
  })
})

describe('sections use the fixed evidence rules', () => {
  const section = (core: boolean[], extra: Partial<CandidateSpec> = {}) => factsFor({ name: 'A', core, years: 'met', ...extra }).section

  it('Start here: at least 60% of non-years core requirements', () => {
    expect(section([true, true, true, false, false])).toBe('start') // exactly 60%
    expect(section([true, true, false, false, false])).toBe('worth') // 40%
    expect(section([true, true, true, true, false, true, false, false])).toBe('start') // 5 of 8
    expect(section([true, true, true, true, false, false, false, false])).toBe('worth') // 4 of 8
    expect(section([true, false])).toBe('worth') // 50%
    expect(section([true, true])).toBe('start')
  })

  it('Worth a look: at least one; Not much shown yet: none', () => {
    expect(section([false, false, false, true])).toBe('worth')
    expect(section([false, false, false, false])).toBe('thin')
  })

  it('years alone never moves a candidate out of "Not much shown yet"', () => {
    expect(factsFor({ name: 'A', core: [false, false, false], years: 'met' }).section).toBe('thin')
  })

  it('Still being prepared: profile not yet read', () => {
    expect(factsFor({ name: 'A', core: [true, true], years: 'met', state: 'building_context' }).section).toBe('preparing')
    expect(factsFor({ name: 'A', core: [true, true], years: 'met', state: 'surfaced' }).why).toBeNull()
  })

  it('a candidate that was not judged is not called "not much shown"', () => {
    expect(factsFor({ name: 'A', core: [true], years: 'met', judged: false }).section).toBe('unchecked')
  })

  it('Open to work, level and updated dates never change the section or the card facts', () => {
    const base = factsFor({ name: 'A', core: [true, false, false], years: 'met' })
    const flagged = factsFor({ name: 'A', core: [true, false, false], years: 'met', openToWork: true, updatedAt: '2026-01-01' })
    expect(flagged).toEqual(base)
    expect(factsFor({ name: 'A', core: [true, false, false], years: 'met', levelFit: 'above' }).section).toBe(base.section)
  })

  it('groups keep the order the search returned inside each group', () => {
    const specs: CandidateSpec[] = [
      { name: 'one', core: [false, false], years: 'met' },
      { name: 'two', core: [true, true], years: 'met' },
      { name: 'three', core: [true, false, false], years: 'met' },
      { name: 'four', core: [true, true], years: 'met' },
    ]
    const groups = groupBySection(buildWorkspaceCandidates(buildDiscoveryCandidates(makeResponse(specs))))
    expect(groups.map((g) => [g.key, g.items.map((i) => i.candidate.name)])).toEqual([
      ['start', ['two', 'four']],
      ['worth', ['three']],
      ['thin', ['one']],
    ])
  })
})

describe('concerns are separate from missing information', () => {
  it('shows level and years concerns, at most two', () => {
    const facts = factsFor({ name: 'A', core: [true], years: 'not', levelFit: 'above', experienceFloor: false })
    expect(facts.watch.map((w) => w.key)).toEqual(['floor', 'level'])
  })

  it('does not turn an unclear level into a warning', () => {
    expect(factsFor({ name: 'A', core: [true], years: 'met', levelFit: 'unclear' }).watch).toEqual([])
    expect(factsFor({ name: 'A', core: [true], years: 'met' }).watch).toEqual([])
  })

  it('lists unmet core requirements as "not proven", by name, not as a concern', () => {
    const facts = factsFor({ name: 'A', core: [true, false, false], years: 'met' })
    expect(facts.notProven).toEqual(['Experience with capability 2', 'Experience with capability 3'])
    expect(facts.watch).toEqual([])
  })
})

describe('proof chips', () => {
  it('use the verified phrase from the quote, at most three', () => {
    const facts = factsFor({ name: 'A', core: [true, true, true, true, true], years: 'met' })
    expect(facts.chips).toHaveLength(3)
    expect(facts.chips[0].label).toBe('capability 1')
    expect(facts.chips[0].quote).toContain('capability 1')
  })

  it('fall back to the brief wording when the term is only the opening words of a long quote', () => {
    expect(proofLabel({ term: 'Write and', quote: 'Write and maintain unit tests for the payments service', requirement: 'Experience with automated testing' })).toBe('Automated testing')
    expect(proofLabel({ term: 'zzz', quote: '• Built REST APIs', requirement: 'Experience with REST API design' })).toBe('REST API design')
    expect(proofLabel({ term: 'REST APIs', quote: 'REST APIs enabling data exchange', requirement: 'REST API design' })).toBe('REST APIs')
  })

  it('never ends on a dangling connector when shortened', () => {
    const label = proofLabel({ term: '', quote: 'x', requirement: 'Experience with infrastructure-as-code tools such as Terraform or Pulumi' }) ?? ''
    expect(label).not.toMatch(/\b(such as|as|and|or|of|to|the)…?$/i)
    expect(label.length).toBeLessThanOrEqual(46)
  })
})

describe('funnel copy reports facts only', () => {
  const funnel = { in_scope: 724204, has_location_scope: true, retrieved: 50, selected: 25, read_in_depth: 25, presented: 25 }

  it('states what happened without explaining how the 25 were chosen', () => {
    const copy = funnelCopy(funnel, 25)
    expect(copy.headline).toBe('25 profiles were selected from the 50 retrieved and read in full.')
    expect(copy.headline + (copy.notRead ?? '')).not.toMatch(/title|headline|because|decided|best|top/i)
  })

  it('describes the search area as a size, never a match count', () => {
    const copy = funnelCopy(funnel, 25)
    expect(copy.scope).toBe('The search area holds about 724,000 profiles. That is the size of the area, not the number of matches.')
    expect(funnelCopy({ ...funnel, has_location_scope: false }, 25).scope).toBeNull()
  })

  it('states a shortfall in reads and copes with older searches', () => {
    expect(funnelCopy({ ...funnel, read_in_depth: 20 }, 25).headline).toBe('25 profiles were selected from the 50 retrieved. 20 were read in full.')
    expect(funnelCopy(null, 12).headline).toBe('12 profiles were retrieved and read in full.')
    expect(readFunnel({})).toBeNull()
    expect(approximateCount(724204)).toBe('about 724,000')
  })

  it('names no provider', () => {
    expect(JSON.stringify(funnelCopy(funnel, 25))).not.toMatch(/crustdata|harvest|provider/i)
  })
})

describe('order stays stable while a search fills in', () => {
  it('keeps arrival order, appends newcomers, drops departures', () => {
    expect(stableOrder(['a', 'b', 'c'], ['c', 'a', 'd', 'b'])).toEqual(['a', 'b', 'c', 'd'])
    expect(stableOrder(['a', 'b', 'c'], ['b', 'a'])).toEqual(['a', 'b'])
  })
})

// The real Toronto search, when its (git-ignored) preview data is present. Skipped on a clean checkout.
const toronto = import.meta.glob('../preview-data/response.json', { eager: true }) as Record<string, { default: Parameters<typeof buildDiscoveryCandidates>[0] }>
describe.skipIf(Object.keys(toronto).length === 0)('real Toronto search', () => {
  const response = Object.values(toronto)[0]?.default
  const items = response ? buildWorkspaceCandidates(buildDiscoveryCandidates(response)) : []

  it('groups 25 candidates as 3 / 10 / 12', () => {
    expect(items).toHaveLength(25)
    expect(groupBySection(items).map((g) => g.items.length)).toEqual([3, 10, 12])
  })

  it('gives every candidate exactly as many dots as the brief has non-years core requirements', () => {
    for (const item of items) expect(item.facts.dots).toHaveLength(4)
  })
})
