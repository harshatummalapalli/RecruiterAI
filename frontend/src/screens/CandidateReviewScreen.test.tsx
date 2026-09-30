// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createEmptySearchBrief } from '../models/searchBrief'
import { makeResponse, type CandidateSpec } from '../models/workspaceFixtures'
import type { SearchResponse } from '../types'

vi.mock('../services/recruiterWorkflow', () => ({
  updateCandidateRecord: vi.fn(() => Promise.resolve({})),
}))

import { updateCandidateRecord } from '../services/recruiterWorkflow'
import { CandidateReviewScreen } from './CandidateReviewScreen'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const SPECS: CandidateSpec[] = [
  { name: 'Heavy Evidence', core: [true, true, true, true, true], years: 'met', openToWork: true },
  { name: 'Partial Evidence', core: [true, false, false, false, false, false], years: 'met', levelFit: 'above' },
  { name: 'Under The Years', core: [true, true, false], years: 'not', experienceFloor: false },
  { name: 'Zero Evidence', core: [false, false, false, false, false], years: 'met' },
  {
    name: 'Long Headline',
    core: [true, true, false, false],
    years: 'met',
    headline: 'Experienced backend engineer with a very long headline that goes on and on about scalable distributed systems, cloud, and much more',
  },
  { name: 'Still Reading', core: [true], years: 'met', state: 'building_context' },
]


let root: Root
let container: HTMLElement

const $ = (selector: string) => container.querySelector(selector) as HTMLElement | null
const $$ = (selector: string) => Array.from(container.querySelectorAll(selector)) as HTMLElement[]
const click = (element: Element | null | undefined) =>
  act(() => {
    element!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
const press = (element: Element, key: string) =>
  act(() => {
    element.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }))
  })
const button = (label: RegExp, within: ParentNode = container) => Array.from(within.querySelectorAll('button')).find((b) => label.test(b.textContent ?? '')) as HTMLElement
const cardIds = () => $$('[data-card-id]').map((element) => element.dataset.cardId)
const card = (name: string) => $$('article.ws-card').find((element) => element.querySelector('.ws-card__name')?.textContent === name)!

async function render(response: SearchResponse, searchState: 'searching' | 'done' = 'done') {
  await act(async () => {
    root.render(
      <CandidateReviewScreen
        brief={createEmptySearchBrief()}
        onChangeBrief={() => undefined}
        searchResponse={response}
        searchState={searchState}
        onRunSearch={() => undefined}
        searchId="test"
        searchGeneration={1}
        boundary={null}
        onApplyBoundary={async () => undefined}
      />,
    )
  })
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  vi.clearAllMocks()
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
})

describe('cards', () => {
  it('render identity, headline, coverage, dots, chips, and actions for an evidence-heavy candidate', async () => {
    await render(makeResponse(SPECS, { workspace_arranged: true }))
    const heavy = card('Heavy Evidence')
    expect(heavy.querySelector('.ws-card__role')?.textContent).toBe('Backend Engineer · Acme · Toronto, Ontario, Canada')
    // The card is deliberately compact (frozen spec): no separate headline line, only name/title/company/location.
    expect(heavy.querySelector('.ws-card__headline')).toBeNull()
    // The dots are the ONLY evidence fingerprint on the card now — no
    // "N core requirements shown · M in described work" sentence beside
    // them (that detail lives one click away, in the Candidate Record).
    expect(heavy.querySelector('.ws-card__why')?.textContent).toBe('')
    expect(heavy.querySelectorAll('.ws-dot')).toHaveLength(5)
    expect(heavy.querySelectorAll('.ws-dot.is-shown')).toHaveLength(5)
    expect(heavy.querySelectorAll('.ws-chip--proof')).toHaveLength(3)
    for (const label of ['Shortlist', 'Maybe', 'Reject']) expect(button(new RegExp(`^${label}`), heavy)).toBeTruthy()
  })

  it('build one dot per non-years core requirement whatever the brief asks for', async () => {
    await render(makeResponse(SPECS, { workspace_arranged: true }))
    expect(card('Partial Evidence').querySelectorAll('.ws-dot')).toHaveLength(6)
    expect(card('Partial Evidence').querySelectorAll('.ws-dot.is-shown')).toHaveLength(1)
    expect(card('Under The Years').querySelectorAll('.ws-dot')).toHaveLength(3)
    expect(card('Zero Evidence').querySelectorAll('.ws-dot')).toHaveLength(5)
    expect(card('Zero Evidence').querySelectorAll('.ws-dot.is-shown')).toHaveLength(0)
  })

  it('keep every dot for a very large brief, in a compact form', async () => {
    await render(makeResponse([{ name: 'Big Brief', core: Array.from({ length: 14 }, (_, i) => i % 3 === 0), years: 'met' }], { workspace_arranged: true }))
    expect(card('Big Brief').querySelectorAll('.ws-dot')).toHaveLength(14)
    expect(card('Big Brief').querySelector('.ws-dots.is-dense')).toBeTruthy()
  })

  it('say zero evidence plainly, with the dots alone (no shown-count sentence)', async () => {
    await render(makeResponse(SPECS, { workspace_arranged: true }))
    expect(card('Zero Evidence').querySelectorAll('.ws-dot.is-shown')).toHaveLength(0)
    expect(card('Zero Evidence').querySelector('.ws-card__why')?.textContent).toBe('')
    expect(card('Zero Evidence').querySelector('.ws-chip--watch')).toBeNull()
  })

  it('flag only real concerns in amber', async () => {
    await render(makeResponse(SPECS, { workspace_arranged: true }))
    expect(card('Partial Evidence').querySelector('.ws-chip--watch')?.textContent).toBe('Level may be above this role')
    expect(card('Under The Years').querySelector('.ws-chip--watch')?.textContent).toBe('Under the years asked')
    expect(card('Heavy Evidence').querySelector('.ws-chip--watch')).toBeNull()
  })

  it('shows no open-to-work chip or date on the compact card (that lives in the full record instead)', async () => {
    await render(makeResponse(SPECS.map((spec) => ({ ...spec, updatedAt: '2026-03-04' })), { workspace_arranged: true }))
    expect($$('article.ws-card .ws-chip--neutral')).toHaveLength(0)
    expect($$('article.ws-card').map((element) => element.textContent).join(' ')).not.toMatch(/updated|2026|Mar/i)
  })

  it('show a profile still being read as a quiet row with no actions', async () => {
    await render(makeResponse(SPECS), 'searching')
    const pending = $('.ws-pending[data-card-id="c6"]')!
    expect(pending.textContent).toMatch(/Reading profile/)
    expect(pending.querySelectorAll('button')).toHaveLength(0)
  })
})

describe('a flat list, never grouped', () => {
  it('stays in arrival order while reading', async () => {
    await render(
      makeResponse(SPECS, { status: 'running', progress: { admitted: 6, review_ready: 5, building_context: 1, surfaced: 0 } }),
      'searching',
    )
    expect(cardIds()).toEqual(['c1', 'c2', 'c3', 'c4', 'c5', 'c6'])
  })

  it('never offers grouping, sorting or comparing, even for a search that was grouped before', async () => {
    await render(makeResponse(SPECS.slice(0, 5)))
    expect($('.ws-banner')).toBeNull()
    expect(container.textContent).not.toMatch(/Group them|Grouped by|Start here|Worth a look|Not much shown yet/)
    expect($$('.ws-section')).toHaveLength(0)
    await render(makeResponse(SPECS.slice(0, 5), { workspace_arranged: true }))
    expect($$('.ws-section')).toHaveLength(0)
    expect($('.ws-banner')).toBeNull()
    expect(cardIds()).toEqual(['c1', 'c2', 'c3', 'c4', 'c5'])
  })

  // The funnel/"how this list was made" exposition (retrieved/selected counts, provider methodology) was
  // deliberately removed from the recruiter-facing workspace — the recruiter sees what was found, not how the
  // retrieval pipeline worked. funnelCopy() itself (models/workspace.test.ts) is untouched and still tested.
})

describe('decisions and filter', () => {
  it('persist by candidate id and never move a card', async () => {
    await render(makeResponse(SPECS.slice(0, 5), { workspace_arranged: true }))
    const before = cardIds()
    await click(button(/^Shortlist/, card('Partial Evidence')))
    expect(updateCandidateRecord).toHaveBeenCalledWith('test', 'c2', { decision: 'shortlist' })
    expect(cardIds()).toEqual(before)
    await click(button(/^Reject/, card('Heavy Evidence')))
    expect(cardIds()).toEqual(before)
    expect($('.ws-slim[data-card-id="c1"]')?.textContent).toMatch(/Rejected/)
  })

  it('collapse a decided card in place under "To review", with Undo', async () => {
    await render(makeResponse(SPECS.slice(0, 5), { workspace_arranged: true }))
    await click(button(/^To review/))
    const before = cardIds()
    await click(button(/^Maybe/, card('Heavy Evidence')))
    expect(cardIds()).toEqual(before)
    const slim = $('.ws-slim[data-card-id="c1"]')!
    expect(slim.textContent).toMatch(/Maybe/)
    await click(button(/Undo/, slim))
    expect(updateCandidateRecord).toHaveBeenLastCalledWith('test', 'c1', { decision: '' })
    expect($('article.ws-card[data-card-id="c1"]')).toBeTruthy()
  })

  it('offers exactly the five filters, no sort, no compare, no second filter', async () => {
    await render(makeResponse(SPECS.slice(0, 5), { workspace_arranged: true }))
    expect($$('.ws-filter__option').map((option) => option.textContent?.replace(/\s*\d+$/, ''))).toEqual(['All', 'To review', 'Shortlisted', 'Maybe', 'Rejected'])
    expect(container.textContent).not.toMatch(/Sort|Compare|Profile Updated|Relevance/)
    expect($('select')).toBeNull()
    expect($('input[type="checkbox"]')).toBeNull()
  })

  it('filters to the decided candidates', async () => {
    await render(makeResponse(SPECS.slice(0, 5), { workspace_arranged: true, recruiter_decisions: { c2: 'shortlist', c4: 'maybe' } }))
    await click(button(/^Shortlisted/))
    expect(cardIds()).toEqual(['c2'])
    await click(button(/^Maybe/))
    expect(cardIds()).toEqual(['c4'])
    await click(button(/^To review/))
    expect(cardIds().sort()).toEqual(['c1', 'c3', 'c5'])
  })

  it('works from the keyboard', async () => {
    await render(makeResponse(SPECS.slice(0, 5), { workspace_arranged: true }))
    const first = $('article.ws-card') as HTMLElement
    act(() => first.focus())
    press(first, 'j')
    const second = document.activeElement as HTMLElement
    expect(second.dataset.cardId).not.toBe(first.dataset.cardId)
    press(second, 's')
    expect(updateCandidateRecord).toHaveBeenCalledWith('test', second.dataset.cardId, { decision: 'shortlist' })
  })
})

describe('proof and record', () => {
  it('one click on a candidate opens the full record, with quotes and their source', async () => {
    await render(makeResponse(SPECS, { workspace_arranged: true }))
    await click(card('Partial Evidence'))
    const record = $('aside.record')!
    expect(record.textContent).toContain('“Built systems using capability 1 for production”')
    expect(record.textContent).toMatch(/role description · Engineer at Acme/)
  })

  it('open the full record without any "listed N of M" rank claim or provider wording', async () => {
    await render(makeResponse(SPECS, { workspace_arranged: true }))
    await click(card('Heavy Evidence'))
    const record = $('aside.record')!
    expect(record.textContent).toContain('Heavy Evidence')
    expect(record.textContent).toMatch(/Evidence for this role/)
    expect(container.textContent).not.toMatch(/listed \d+ of \d+/i)
    expect(container.textContent).not.toMatch(/crustdata|harvest|provider|natural_language/i)
    expect(container.textContent).not.toMatch(/updated \w{3} \d/i)
  })

  it('shows the evidence fingerprint exactly once, with no score/rank/match% language anywhere', async () => {
    await render(makeResponse(SPECS, { workspace_arranged: true }))
    await click(card('Heavy Evidence'))
    const record = $('aside.record')!
    // Exactly one fingerprint, right after identity, before the decision.
    expect(record.querySelectorAll('.record-fingerprint')).toHaveLength(1)
    const dotsInRecord = record.querySelectorAll('.record-fingerprint .ws-dot')
    expect(dotsInRecord.length).toBe(5)
    expect(record.querySelectorAll('.ws-dots')).toHaveLength(1) // never a second dots row elsewhere in the record
    expect(record.textContent).not.toMatch(/\d+%|match score|match %|confidence score|rank(ed|ing)?\b/i)
    expect(record.textContent).not.toMatch(/excellent|poor fit/i)
  })
})

describe('evidence state: met / not_evidenced / unknown', () => {
  // Builds a single-candidate response via the shared fixture, then
  // overrides requirement_judgments directly so each test controls
  // evidence_state precisely (the fixture itself never sets it).
  function responseWithJudgments(judgments: Record<string, unknown>[]) {
    const response = makeResponse([{ name: 'Evidence Candidate', core: [] }])
    ;(response.evidence![0] as unknown as Record<string, unknown>).requirement_judgments = judgments
    return response
  }

  const MET_JUDGMENT = {
    tier: 'core',
    signal_text: 'Has recruited software engineers',
    verdict: 'met',
    evidence_state: 'met',
    quote: 'Lead Recruiter at Nitor Infotech — “Recruited software engineers for the platform team.”',
    source: 'employment record',
    strength: 'strong',
  }
  const NOT_EVIDENCED_JUDGMENT = {
    tier: 'core',
    signal_text: 'Has recruited AI/ML teams',
    verdict: 'not_evidenced',
    evidence_state: 'not_evidenced',
    source: 'employment record',
  }
  const UNKNOWN_JUDGMENT = {
    tier: 'core',
    signal_text: 'Has recruited engineering leaders',
    verdict: 'not_evidenced',
    evidence_state: 'unknown',
    source: 'employment record',
  }
  const LEGACY_JUDGMENT = {
    // No evidence_state at all — exactly the shape of every judgment
    // persisted before this release.
    tier: 'core',
    signal_text: 'Proficiency in Python',
    verdict: 'not_evidenced',
  }

  it('1. met renders as affirmative evidence with its real quote', async () => {
    await render(responseWithJudgments([MET_JUDGMENT]))
    await click(card('Evidence Candidate'))
    const record = $('aside.record')!
    const row = $$('.record-ledger__row--met').find((r) => r.textContent?.includes('Has recruited software engineers'))!
    expect(row).toBeTruthy()
    expect(row.querySelector('.record-ledger__quote')?.textContent).toContain('Recruited software engineers for the platform team')
    expect(record.textContent).not.toMatch(/not demonstrated|unavailable/i)
  })

  it('2. not_evidenced renders distinctly from met', async () => {
    await render(responseWithJudgments([NOT_EVIDENCED_JUDGMENT]))
    await click(card('Evidence Candidate'))
    const row = $$('.record-ledger__row--missing').find((r) => r.textContent?.includes('Has recruited AI/ML teams'))!
    expect(row).toBeTruthy()
    expect(row.classList.contains('record-ledger__row--unknown')).toBe(false)
    expect(row.textContent).toContain('Not demonstrated in available role evidence.')
    // Never a false-negative implication.
    expect(row.textContent?.toLowerCase()).not.toMatch(/doesn't have|failed|not qualified|no experience/)
  })

  it('3. unknown renders distinctly from not_evidenced', async () => {
    await render(responseWithJudgments([NOT_EVIDENCED_JUDGMENT, UNKNOWN_JUDGMENT]))
    await click(card('Evidence Candidate'))
    const notEvidencedRow = $$('.record-ledger__row--missing').find((r) => r.textContent?.includes('Has recruited AI/ML teams'))!
    const unknownRow = $$('.record-ledger__row--missing').find((r) => r.textContent?.includes('Has recruited engineering leaders'))!
    expect(unknownRow.classList.contains('record-ledger__row--unknown')).toBe(true)
    expect(notEvidencedRow.classList.contains('record-ledger__row--unknown')).toBe(false)
    expect(unknownRow.textContent).toContain('Role evidence unavailable.')
    expect(unknownRow.textContent).not.toContain('Not demonstrated in available role evidence.')
    expect(unknownRow.textContent?.toLowerCase()).not.toMatch(/doesn't have|not qualified|no experience/)
  })

  it('4. legacy judgment without evidence_state renders exactly as verdict alone always has (never "unknown")', async () => {
    await render(responseWithJudgments([LEGACY_JUDGMENT]))
    await click(card('Evidence Candidate'))
    const row = $$('.record-ledger__row--missing').find((r) => r.textContent?.includes('Proficiency in Python'))!
    expect(row).toBeTruthy()
    expect(row.classList.contains('record-ledger__row--unknown')).toBe(false)
    expect(row.textContent).toContain('Not demonstrated in available role evidence.')
  })

  it('5. existing recruiter actions (Shortlist/Maybe/Reject) are unaffected', async () => {
    await render(responseWithJudgments([MET_JUDGMENT, NOT_EVIDENCED_JUDGMENT, UNKNOWN_JUDGMENT]))
    await click(card('Evidence Candidate'))
    for (const label of ['Shortlist', 'Maybe', 'Reject']) {
      expect(button(new RegExp(`^${label}`), $('aside.record')!)).toBeTruthy()
    }
  })

  it('6. candidate ordering is unaffected by evidence_state', async () => {
    await render(makeResponse(SPECS, { workspace_arranged: true }))
    // Arrival order, exactly as the existing "flat list, never grouped"
    // contract already requires — evidence_state adds no reordering.
    expect(cardIds()).toEqual(SPECS.map((_, i) => `c${i + 1}`))
  })

  it('7. existing Candidate Record sections remain intact', async () => {
    await render(responseWithJudgments([MET_JUDGMENT, NOT_EVIDENCED_JUDGMENT, UNKNOWN_JUDGMENT]))
    await click(card('Evidence Candidate'))
    const record = $('aside.record')!
    for (const heading of ['Why this candidate', 'Evidence for this role', 'Experience', 'Education', 'Recruiter Notes']) {
      expect(record.textContent).toContain(heading)
    }
  })

  it('8. no score, rank, or match percentage appears anywhere in the record', async () => {
    await render(responseWithJudgments([MET_JUDGMENT, NOT_EVIDENCED_JUDGMENT, UNKNOWN_JUDGMENT]))
    await click(card('Evidence Candidate'))
    const record = $('aside.record')!
    expect(record.textContent).not.toMatch(/\d+%|match score|confidence|rank(ed|ing)?\b/i)
  })
})
