// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createEmptySearchBrief } from '../models/searchBrief'
import { makeRoleResponse } from '../models/roleFixtures'
import { makeResponse, type CandidateSpec } from '../models/workspaceFixtures'
import type { SearchResponse } from '../types'

vi.mock('../services/recruiterWorkflow', () => ({
  updateCandidateRecord: vi.fn(() => Promise.resolve({})),
}))

import { CandidateReviewScreen } from './CandidateReviewScreen'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let root: Root
let container: HTMLElement
const $$ = (selector: string) => Array.from(container.querySelectorAll(selector)) as HTMLElement[]
const names = () => $$('article.ws-card .ws-card__name').map((element) => element.textContent)
const click = (element: Element | undefined) =>
  act(async () => {
    element!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
const button = (label: RegExp, within: ParentNode = container) => Array.from(within.querySelectorAll('button')).find((b) => label.test(b.textContent ?? ''))

async function render(response: SearchResponse) {
  await act(async () => {
    root.render(
      <CandidateReviewScreen
        brief={createEmptySearchBrief()}
        onChangeBrief={() => undefined}
        searchResponse={response}
        searchState="done"
        onRunSearch={() => undefined}
        searchId="role-1"
        searchGeneration={1}
        boundary={null}
        onApplyBoundary={async () => undefined}
        onShowMore={async () => undefined}
      />,
    )
  })
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
})

// The search returned them in this order; the number of core requirements shown differs.
const SCRAMBLED: CandidateSpec[] = [
  { name: 'One shown', core: [true, false, false, false], years: 'met' },
  { name: 'Four shown', core: [true, true, true, true], years: 'met' },
  { name: 'Zero shown', core: [false, false, false, false], years: 'met' },
  { name: 'Three shown A', core: [true, true, true, false], years: 'met' },
  { name: 'Three shown B', core: [true, true, false, true], years: 'met' },
]

describe('the order of the candidates on screen', () => {
  it('starts with the candidate showing the most core requirements, ties in the order the search returned them', async () => {
    await render(makeRoleResponse(SCRAMBLED, { presented: 5 }))
    expect(names()).toEqual(['Four shown', 'Three shown A', 'Three shown B', 'One shown', 'Zero shown'])
  })

  it('adds no rank number, no superlative, no sort control and no evidence filter', async () => {
    await render(makeRoleResponse(SCRAMBLED, { presented: 5 }))
    expect(container.textContent).toContain('Most core requirements shown first.')
    expect(container.textContent).not.toMatch(/#\d|\b1st\b|\bTop\b|\bBest\b|Excellent|\bscore\b/i)
    expect(container.querySelector('select')).toBeNull()
    expect(Array.from(container.querySelectorAll('.ws-filter__option')).map((option) => option.textContent?.replace(/\s*\d+$/, ''))).toEqual(['All', 'To review', 'Shortlisted', 'Maybe', 'Rejected'])
  })

  it('does not move when the recruiter decides', async () => {
    await render(makeRoleResponse(SCRAMBLED, { presented: 5 }))
    const before = names()
    const card = $$('article.ws-card')[0]
    await click(button(/^Shortlist$/, card))
    expect(names()).toEqual(before)
    await click(button(/^Maybe$/, $$('article.ws-card')[2]))
    expect(names()).toEqual(before)
  })

  it('keeps each set where it was shown: a stronger candidate arriving later goes below the first set', async () => {
    const specs: CandidateSpec[] = [...SCRAMBLED, { name: 'Later strongest', core: [true, true, true, true], years: 'met' }, { name: 'Later weakest', core: [false, false, false, false], years: 'met' }]
    const response = makeRoleResponse(specs, { presented: 5 })
    response.presentation!.c6 = { state: 'presented', source: 'initial', seen: true, stale: false, batch: 2 }
    response.presentation!.c7 = { state: 'presented', source: 'initial', seen: true, stale: false, batch: 2 }
    await render(response)
    expect(names()).toEqual(['Four shown', 'Three shown A', 'Three shown B', 'One shown', 'Zero shown', 'Later strongest', 'Later weakest'])
  })

  it('keeps the filters working on the ordered list', async () => {
    const response = makeRoleResponse(SCRAMBLED, { presented: 5, extra: { recruiter_decisions: { c1: 'shortlist', c4: 'shortlist' } } })
    await render(response)
    await click(button(/^Shortlisted/))
    expect(names()).toEqual(['Three shown A', 'One shown'])
  })

  it('does not re-order a search stored before roles existed', async () => {
    await render(makeResponse(SCRAMBLED))
    expect(names()).toEqual(SCRAMBLED.map((spec) => spec.name))
    expect(container.textContent).toContain('In the order they were read.')
  })
})
