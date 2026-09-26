// @vitest-environment jsdom
/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createEmptySearchBrief } from '../models/searchBrief'
import { makeResponse, type CandidateSpec } from '../models/workspaceFixtures'
import type { SearchResponse } from '../types'

vi.mock('../services/recruiterWorkflow', () => ({
  updateCandidateRecord: vi.fn(() => Promise.resolve({})),
  setWorkspaceArranged: vi.fn(() => Promise.resolve()),
}))

import { setWorkspaceArranged, updateCandidateRecord } from '../services/recruiterWorkflow'
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

const workspaceCss = readFileSync('src/components/CandidateWorkspace.css', 'utf-8') // vitest runs from frontend/

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
    expect(heavy.querySelector('.ws-card__headline')?.textContent).toBe('Backend Engineer | Python | Distributed systems')
    expect(heavy.querySelector('.ws-card__why')?.textContent).toBe('5 core requirements shown · 5 in described work')
    expect(heavy.querySelectorAll('.ws-dot')).toHaveLength(5)
    expect(heavy.querySelectorAll('.ws-dot.is-shown')).toHaveLength(5)
    expect(heavy.querySelectorAll('.ws-chip--proof')).toHaveLength(3)
    for (const label of ['Shortlist', 'Maybe', 'Reject', 'Full record', 'Proof']) expect(button(new RegExp(`^${label}`), heavy)).toBeTruthy()
  })

  it('build one dot per non-years core requirement whatever the brief asks for', async () => {
    await render(makeResponse(SPECS, { workspace_arranged: true }))
    expect(card('Partial Evidence').querySelectorAll('.ws-dot')).toHaveLength(6)
    expect(card('Partial Evidence').querySelectorAll('.ws-dot.is-shown')).toHaveLength(1)
    expect(card('Under The Years').querySelectorAll('.ws-dot')).toHaveLength(3)
    await click(button(/Not much shown yet/))
    expect(card('Zero Evidence').querySelectorAll('.ws-dot')).toHaveLength(5)
    expect(card('Zero Evidence').querySelectorAll('.ws-dot.is-shown')).toHaveLength(0)
  })

  it('keep every dot for a very large brief, in a compact form', async () => {
    await render(makeResponse([{ name: 'Big Brief', core: Array.from({ length: 14 }, (_, i) => i % 3 === 0), years: 'met' }], { workspace_arranged: true }))
    expect(card('Big Brief').querySelectorAll('.ws-dot')).toHaveLength(14)
    expect(card('Big Brief').querySelector('.ws-dots.is-dense')).toBeTruthy()
  })

  it('say zero evidence plainly', async () => {
    await render(makeResponse(SPECS, { workspace_arranged: true }))
    await click(button(/Not much shown yet/))
    expect(card('Zero Evidence').querySelector('.ws-card__why')?.textContent).toBe('Nothing beyond total years is shown on the profile.')
    expect(card('Zero Evidence').querySelector('.ws-chip--watch')).toBeNull()
  })

  it('flag only real concerns in amber', async () => {
    await render(makeResponse(SPECS, { workspace_arranged: true }))
    expect(card('Partial Evidence').querySelector('.ws-chip--watch')?.textContent).toBe('Level may be above this role')
    expect(card('Under The Years').querySelector('.ws-chip--watch')?.textContent).toBe('Under the years asked')
    expect(card('Heavy Evidence').querySelector('.ws-chip--watch')).toBeNull()
  })

  it('show Open to work only where the profile says so, and no date anywhere', async () => {
    await render(makeResponse(SPECS.map((spec) => ({ ...spec, updatedAt: '2026-03-04' })), { workspace_arranged: true }))
    await click(button(/Not much shown yet/))
    expect($$('.ws-chip--neutral').map((chip) => chip.closest('article')?.querySelector('.ws-card__name')?.textContent)).toEqual(['Heavy Evidence'])
    expect($$('article.ws-card').map((element) => element.textContent).join(' ')).not.toMatch(/updated|2026|Mar/i)
  })

  it('keep a long headline to one line and the full text intact', async () => {
    await render(makeResponse(SPECS, { workspace_arranged: true }))
    const headline = card('Long Headline').querySelector('.ws-card__headline') as HTMLElement
    expect(headline.textContent).toContain('and much more')
    // jsdom cannot measure layout, so check the rule that makes it one line: nowrap + hidden overflow + ellipsis.
    expect(headline.className).toBe('ws-card__headline')
    const rule = /\.ws-card__headline\s*\{([^}]*)\}/.exec(workspaceCss)?.[1] ?? ''
    expect(rule).toMatch(/white-space:\s*nowrap/)
    expect(rule).toMatch(/overflow:\s*hidden/)
    expect(rule).toMatch(/text-overflow:\s*ellipsis/)
  })

  it('show a profile still being read as a quiet row with no actions', async () => {
    await render(makeResponse(SPECS), 'searching')
    const pending = $('.ws-pending[data-card-id="c6"]')!
    expect(pending.textContent).toMatch(/Reading profile/)
    expect(pending.querySelectorAll('button')).toHaveLength(0)
  })
})

describe('sections and grouping', () => {
  it('stay flat in arrival order while reading, with progress', async () => {
    await render(
      makeResponse(SPECS, { status: 'running', progress: { admitted: 6, review_ready: 5, building_context: 1, surfaced: 0 } }),
      'searching',
    )
    expect($('.ws-funnel__headline')?.textContent).toBe('Reading profiles: 5 of 6')
    expect($$('.ws-section')).toHaveLength(0)
    expect(cardIds()).toEqual(['c1', 'c2', 'c3', 'c4', 'c5', 'c6'])
  })

  it('announce grouping once, then group by evidence and persist the choice', async () => {
    await render(makeResponse(SPECS.slice(0, 5)))
    expect($('.ws-banner')?.textContent).toContain('All 5 profiles are read. Group them by how much of the brief each one shows?')
    expect($$('.ws-section')).toHaveLength(0)
    const before = cardIds()

    await click(button(/Group them/))
    expect(setWorkspaceArranged).toHaveBeenCalledWith('test', true)
    expect($('.ws-banner')).toBeNull()
    expect($$('.ws-section__title').map((title) => title.textContent)).toEqual(['Start here', 'Worth a look', 'Not much shown yet'])
    expect($('.ws-note')?.textContent).toMatch(/not a ranking/)
    // "Not much shown yet" starts collapsed; once opened, every candidate is still there.
    await click(button(/Not much shown yet/))
    expect(new Set(cardIds())).toEqual(new Set(before))
  })

  it('open already grouped when the search record says so, with no banner', async () => {
    await render(makeResponse(SPECS.slice(0, 5), { workspace_arranged: true }))
    expect($('.ws-banner')).toBeNull()
    expect($$('.ws-section')).toHaveLength(3)
  })

  it('offer no grouping while a profile is still being read', async () => {
    await render(makeResponse(SPECS))
    expect($('.ws-banner')).toBeNull()
  })

  it('show the honest funnel and keep methodology under "How this list was made"', async () => {
    await render(makeResponse(SPECS.slice(0, 5), { workspace_arranged: true, warnings: ['This search cannot filter by work mode (remote/hybrid/onsite), so results may include other arrangements.'] }))
    expect($('.ws-funnel__headline')?.textContent).toBe('25 profiles were selected from the 50 retrieved and read in full.'.replace('25', '5'))
    expect($('.ws-funnel__scope')?.textContent).toMatch(/size of the area, not the number of matches/)
    expect($('.ws-funnel__how')?.textContent).toMatch(/cannot filter by work mode/)
    expect($('.ws-funnel__counts')?.textContent).toMatch(/start here/)
  })
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
    await click(button(/Not much shown yet/))
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
  it('expand proof in place with quotes and their source', async () => {
    await render(makeResponse(SPECS, { workspace_arranged: true }))
    const partial = card('Partial Evidence')
    expect(partial.textContent).not.toContain('“')
    await click(button(/^Proof/, partial))
    expect(partial.textContent).toContain('“Built systems using capability 1 for production”')
    expect(partial.textContent).toMatch(/role description · Engineer at Acme/)
    expect(partial.textContent).toMatch(/Not proven on the profile:/)
    await click(button(/^Proof/, partial))
    expect(partial.textContent).not.toContain('“')
  })

  it('open the full record without any "listed N of M" rank claim or provider wording', async () => {
    await render(makeResponse(SPECS, { workspace_arranged: true }))
    await click(button(/Full record/, card('Heavy Evidence')))
    const record = $('aside.record')!
    expect(record.textContent).toContain('Heavy Evidence')
    expect(record.textContent).toMatch(/Requirement ledger/)
    expect(container.textContent).not.toMatch(/listed \d+ of \d+/i)
    expect(container.textContent).not.toMatch(/crustdata|harvest|provider|natural_language/i)
    expect(container.textContent).not.toMatch(/updated \w{3} \d/i)
  })
})
