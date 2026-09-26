// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CONTRADICTION_QUESTION, EXPERIENCE_QUESTION, HYBRID_TORONTO, TITLE_NOTE, makeBrief, makeIntakeResult } from '../models/livingBriefFixtures'
import type { IntakeResult } from '../models/intake'
import type { SearchBoundary } from '../models/searchBoundary'
import { LivingBrief } from './LivingBrief'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let root: Root
let container: HTMLElement

const handlers = {
  onAnswer: vi.fn(),
  onSearch: vi.fn(),
  onApplyBoundary: vi.fn((_boundary: SearchBoundary) => Promise.resolve()),
  onChangeBrief: vi.fn(),
}

async function render(result: IntakeResult, extra: { boundary?: SearchBoundary; searchErrors?: string[]; isSearching?: boolean } = {}) {
  await act(async () => {
    root.render(
      <LivingBrief
        result={result}
        boundary={extra.boundary ?? HYBRID_TORONTO}
        brief={makeBrief()}
        onChangeBrief={handlers.onChangeBrief}
        onAnswer={handlers.onAnswer}
        isAnswering={false}
        onApplyBoundary={handlers.onApplyBoundary}
        onSearch={handlers.onSearch}
        isSearching={extra.isSearching ?? false}
        searchErrors={extra.searchErrors}
      />,
    )
  })
}

const $ = (selector: string) => container.querySelector(selector) as HTMLElement | null
const $$ = (selector: string) => Array.from(container.querySelectorAll(selector)) as HTMLElement[]
const button = (label: RegExp) => $$('button').find((b) => label.test(b.textContent ?? '')) as HTMLButtonElement
const click = (element: Element | null | undefined) =>
  act(() => {
    element!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })

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

describe('structure', () => {
  it('shows the sections in the agreed order', async () => {
    await render(makeIntakeResult({ issues: [EXPERIENCE_QUESTION, TITLE_NOTE], warnings: ['Something to be aware of.'] }))
    const order = [
      '.lb-header',
      '.lb-decision',
      '#lb-read',
      '#lb-boundary',
      '#lb-level',
      '#lb-requirements',
      '#lb-tech',
      '#lb-notes',
      '#lb-warnings',
      '#lb-confirm',
      '.lb-adjust',
    ].map((selector) => $(selector))
    expect(order.every(Boolean)).toBe(true)
    for (let i = 1; i < order.length; i++) {
      expect(order[i - 1]!.compareDocumentPosition(order[i]!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    }
  })

  it('names Core, Supporting and Preferred like the rest of the product, and never "Differentiators"', async () => {
    await render(makeIntakeResult())
    expect($$('.lb-subheading').map((e) => e.textContent?.replace(/\s*\d+$/, ''))).toEqual(['Core', 'Supporting', 'Preferred'])
    expect(container.textContent).not.toMatch(/Differentiator/)
  })

  it('shows the posted title and the candidate identity as two separate things', async () => {
    await render(makeIntakeResult())
    expect($('.lb-title')?.textContent).toBe('AI Engineer')
    expect($('.lb-identity')?.textContent).toBe('Backend-heavy AI Engineer')
    expect(container.textContent).toContain('As you wrote it')
    expect(container.textContent).toContain('Searched for instead of the posted title')
  })

  it('offers the editable form without location or work mode, which belong to the boundary', async () => {
    await render(makeIntakeResult())
    const adjust = $('.lb-adjust')!.textContent!
    expect(adjust).toMatch(/Experience/)
    expect(adjust).toMatch(/Companies/)
    expect(adjust).not.toMatch(/Search geography|Work Mode|Radius Search/)
  })

  it('uses no search machinery or provider language anywhere', async () => {
    await render(makeIntakeResult({ issues: [EXPERIENCE_QUESTION, TITLE_NOTE] }))
    expect(container.textContent).not.toMatch(/crustdata|harvest|provider|boolean|natural.language|search plan|retrieval/i)
  })
})

describe('provenance', () => {
  it('only ever uses the five agreed labels', async () => {
    await render(makeIntakeResult({ warnings: ['Something to be aware of.'] }))
    const labels = new Set($$('.lb-tag').map((tag) => tag.textContent))
    const allowed = new Set(['Stated in JD', 'Inferred', 'Confirmed by you', 'Warning', 'System limitation'])
    expect([...labels].every((label) => allowed.has(label ?? ''))).toBe(true)
    expect(labels.has('Stated in JD') && labels.has('Inferred') && labels.has('Confirmed by you') && labels.has('Warning') && labels.has('System limitation')).toBe(true)
  })

  it('tags each requirement with where it came from', async () => {
    await render(makeIntakeResult())
    const rows = $$('.lb-list li').map((li) => [li.querySelector('span')?.textContent, li.querySelector('.lb-tag')?.textContent])
    expect(rows).toContainEqual(['Python backend services', 'Stated in JD'])
    expect(rows).toContainEqual(['PostgreSQL', 'Inferred'])
  })

  it('marks a requirement changed by an answer as confirmed', async () => {
    const result = makeIntakeResult()
    result.confirmed = [{ field: 'requirement', description: 'PostgreSQL: now core', item: 'PostgreSQL', issue: 'q', answer: 'a' }]
    await render(result)
    const row = $$('.lb-list li').find((li) => li.textContent?.startsWith('PostgreSQL'))!
    expect(row.querySelector('.lb-tag')?.textContent).toBe('Confirmed by you')
  })

  it('reports work mode as a system limitation, not a warning', async () => {
    await render(makeIntakeResult())
    expect($('.lb-limitation .lb-tag--limitation')?.textContent).toBe('System limitation')
    expect($('.lb-limitation')?.textContent).toContain('cannot filter candidates by work mode')
    expect($('#lb-warnings')).toBeNull()
  })
})

describe('draft and ready', () => {
  it('is a draft while a question is open: the card, the reason, and no search', async () => {
    await render(makeIntakeResult({ issues: [EXPERIENCE_QUESTION] }))
    expect($('.lb-state')?.textContent).toBe('Draft')
    expect($('.lb-decision__question')?.textContent).toContain('3+ years and also 8-10 years')
    expect($('#lb-confirm')?.textContent).toBe('Not ready to search yet')
    expect($('.lb-confirm')?.textContent).toContain('1 decision still needs your answer.')
    expect(button(/^Search$/).disabled).toBe(true)
  })

  it('passes the exact answer up when an option is chosen', async () => {
    await render(makeIntakeResult({ issues: [EXPERIENCE_QUESTION] }))
    await click(button(/8-10 years/))
    expect(handlers.onAnswer).toHaveBeenCalledTimes(1)
    expect(handlers.onAnswer.mock.calls[0].slice(1)).toEqual(['8to10', '8-10 years'])
  })

  it('asks one question at a time and says how many are left', async () => {
    await render(makeIntakeResult({ issues: [CONTRADICTION_QUESTION, EXPERIENCE_QUESTION] }))
    expect($$('.lb-decision')).toHaveLength(1)
    expect($('.lb-decision--contradiction')).toBeTruthy()
    expect($('.lb-more')?.textContent).toBe('1 more decision after this one.')
  })

  it('is ready when nothing is open: what will be searched, no further questions, and Search works', async () => {
    await render(makeIntakeResult())
    expect($('.lb-state')?.textContent).toBe('Ready to search')
    expect($('#lb-confirm')?.textContent).toContain('This is what I will search for')
    expect($('.lb-confirm')?.textContent).toContain("I don't need to ask anything else.")
    expect($('.lb-decision')).toBeNull()
    const search = button(/^Search$/)
    expect(search.disabled).toBe(false)
    await click(search)
    expect(handlers.onSearch).toHaveBeenCalledTimes(1)
  })

  it('does not block a search that has no core requirements, and says so plainly', async () => {
    await render(makeIntakeResult({ core: [] }))
    expect($('#lb-requirements')?.parentElement?.textContent).toContain('No core requirements were identified. The search can still run.')
    expect(button(/^Search$/).disabled).toBe(false)
  })

  it('is a draft when the boundary is incomplete', async () => {
    await render(makeIntakeResult(), { boundary: { ...HYBRID_TORONTO, city: '' } })
    expect($('.lb-state')?.textContent).toBe('Draft')
    expect($('.lb-confirm')?.textContent).toContain('The search boundary is incomplete.')
    expect(button(/^Search$/).disabled).toBe(true)
  })

  it('shows why the last attempt was refused, and a busy state while searching', async () => {
    await render(makeIntakeResult(), { searchErrors: ['1 question still needs your answer.'], isSearching: true })
    expect($('.lb-errors')?.textContent).toContain('1 question still needs your answer.')
    expect(button(/Searching the market/).disabled).toBe(true)
  })
})

describe('the boundary', () => {
  it('is read-only until Edit, and Apply sends the draft up without touching the questions or the search', async () => {
    await render(makeIntakeResult())
    expect($('.lb-boundary')?.textContent).toContain('Toronto, Ontario, Canada · 25 mi radius')
    expect($('#boundary-hiring-company')).toBeNull()

    await click(button(/Edit boundary/))
    expect($('#boundary-hiring-company')).toBeTruthy()
    await click(button(/^Apply$/))
    expect(handlers.onApplyBoundary).toHaveBeenCalledTimes(1)
    expect(handlers.onApplyBoundary.mock.calls[0][0].city).toBe('Toronto')
    expect(handlers.onAnswer).not.toHaveBeenCalled()
    expect(handlers.onSearch).not.toHaveBeenCalled()
    expect($('#boundary-hiring-company')).toBeNull() // closed after a successful apply
  })

  it('shows the server\'s plain-language refusal and stays open', async () => {
    handlers.onApplyBoundary.mockRejectedValueOnce(Object.assign(new Error('x'), { messages: ['Enter a search radius greater than zero.'] }))
    await render(makeIntakeResult())
    await click(button(/Edit boundary/))
    await click(button(/^Apply$/))
    expect($('.lb-errors')?.textContent).toContain('Enter a search radius greater than zero.')
    expect($('#boundary-hiring-company')).toBeTruthy()
  })

  it('"Let me reconsider" opens the boundary and does not answer the question', async () => {
    const conflict = { ...EXPERIENCE_QUESTION, id: 'backstop-location_boundary_conflict', injected_by_backstop: true, backstop_category: 'location_boundary_conflict',
      options: [{ value: 'keep_selected_location', label: 'Keep my selected location' }, { value: 'recruiter_will_clarify', label: 'Let me reconsider' }] }
    await render(makeIntakeResult({ issues: [conflict] }))
    await click(button(/Let me reconsider/))
    expect(handlers.onAnswer).not.toHaveBeenCalled()
    expect($('#boundary-hiring-company')).toBeTruthy()
  })
})
