// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createEmptySearchBrief } from '../models/searchBrief'
import { makeRole, makeRoleResponse, manySpecs } from '../models/roleFixtures'
import { makeResponse } from '../models/workspaceFixtures'
import type { SearchResponse } from '../types'

vi.mock('../services/recruiterWorkflow', () => ({
  updateCandidateRecord: vi.fn(() => Promise.resolve({})),
  setWorkspaceArranged: vi.fn(() => Promise.resolve()),
}))

import { updateCandidateRecord } from '../services/recruiterWorkflow'
import { CandidateReviewScreen } from './CandidateReviewScreen'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let root: Root
let container: HTMLElement

const $ = (selector: string) => container.querySelector(selector) as HTMLElement | null
const $$ = (selector: string) => Array.from(container.querySelectorAll(selector)) as HTMLElement[]
const click = (element: Element | null | undefined) =>
  act(async () => {
    element!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
const button = (label: RegExp, within: ParentNode = container) => Array.from(within.querySelectorAll('button')).find((b) => label.test(b.textContent ?? '')) as HTMLButtonElement
const names = () => $$('article.ws-card .ws-card__name').map((element) => element.textContent)
const card = (name: string) => $$('article.ws-card').find((element) => element.querySelector('.ws-card__name')?.textContent === name)!

const handlers = {
  onShowMore: vi.fn(() => Promise.resolve()),
  onRoleAction: vi.fn(() => Promise.resolve()),
  onCorrectCalibration: vi.fn(() => Promise.resolve()),
  onSearchResponse: vi.fn(),
  onRunSearch: vi.fn(),
}

async function render(response: SearchResponse, extra: { searchState?: 'searching' | 'done'; roleMessage?: string | null; searchNotice?: string | null } = {}) {
  await act(async () => {
    root.render(
      <CandidateReviewScreen
        brief={createEmptySearchBrief()}
        onChangeBrief={() => undefined}
        searchResponse={response}
        searchState={extra.searchState ?? 'done'}
        onRunSearch={handlers.onRunSearch}
        searchId="role-1"
        searchGeneration={1}
        boundary={null}
        onApplyBoundary={async () => undefined}
        onShowMore={handlers.onShowMore}
        onRoleAction={handlers.onRoleAction}
        onCorrectCalibration={handlers.onCorrectCalibration}
        onSearchResponse={handlers.onSearchResponse}
        roleMessage={extra.roleMessage ?? null}
        searchNotice={extra.searchNotice ?? null}
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

describe('the first five and the rest that were read', () => {
  it('shows five candidates to review and keeps the other reviewed candidates collapsed', async () => {
    await render(makeRoleResponse(manySpecs(25)))
    expect(names()).toHaveLength(5)
    const other = $('.role-other')!
    expect(other.textContent).toContain('20 other reviewed candidates')
    expect(other.querySelectorAll('article')).toHaveLength(0) // collapsed
  })

  it('opens the other reviewed candidates without calling them rejected, keeping their decisions available', async () => {
    await render(makeRoleResponse(manySpecs(25)))
    await click(button(/20 other reviewed candidates/))
    const section = $('.role-other')!
    expect(section.querySelectorAll('article.ws-card')).toHaveLength(20)
    expect(section.textContent).toContain('They are not rejected')
    expect(section.querySelector('.ws-funnel, .ws-filter')).toBeNull() // no second workspace: just the reviewed cards
    expect(section.textContent).not.toMatch(/\btop\b|\bbest\b|excellent|ranked/i)
  })

  it('never shows a rank, a score or a superlative', async () => {
    await render(makeRoleResponse(manySpecs(25)))
    expect(container.textContent).not.toMatch(/\bTop \d|\bBest\b|Excellent|\bscore\b|#\d/i)
  })

  it('shows every candidate of a search stored before roles existed, with no Show me more', async () => {
    await render(makeResponse(manySpecs(12)))
    expect(names()).toHaveLength(12)
    expect($('.role-other')).toBeNull()
    expect(button(/Show me more/)).toBeUndefined()
    expect($('.role-bar')).toBeNull()
  })

  it('counts what is still to review as decisions are made', async () => {
    await render(makeRoleResponse(manySpecs(25)))
    await click(button(/Shortlist/, card('Person 1')))
    expect(button(/To review/)?.querySelector('.ws-filter__count')?.textContent).toBe('4')
  })

  it('while the first candidates are still being read, shows progress and no cards', async () => {
    const response = makeRoleResponse(manySpecs(25), { presented: 0, extra: { status: 'running', progress: { admitted: 25, review_ready: 9, building_context: 16, surfaced: 0 } } })
    await render(response, { searchState: 'searching' })
    expect(names()).toHaveLength(0)
    expect(container.textContent).toContain('Reading profiles: 9 of 25')
  })
})

describe('Maybe and Reject ask why, once and quickly', () => {
  it('asks what makes the recruiter unsure after Maybe, and saves the reason they pick', async () => {
    await render(makeRoleResponse(manySpecs(25)))
    await click(button(/^Maybe$/, card('Person 1')))
    const prompt = card('Person 1').querySelector('.ws-feedback')!
    expect(prompt.textContent).toContain('What makes you unsure?')
    expect(Array.from(prompt.querySelectorAll('.role-chip')).map((c) => c.textContent)).toEqual([
      "Relevant experience isn't clear",
      "Required skill isn't demonstrated",
      'Seniority is unclear',
      "Type of work doesn't quite fit",
      'Other',
    ])
    await click(button(/Seniority is unclear/, prompt as HTMLElement))
    expect(updateCandidateRecord).toHaveBeenCalledWith('role-1', 'c1', { decision: 'maybe' })
    expect(updateCandidateRecord).toHaveBeenCalledWith('role-1', 'c1', { feedback_reason: 'seniority_unclear', feedback_note: undefined })
    expect(card('Person 1').querySelector('.ws-feedback')).toBeNull()
    expect(card('Person 1').textContent).toContain('Reason: Seniority is unclear')
  })

  it("asks what's missing after Reject and lets the reject collapse once answered", async () => {
    await render(makeRoleResponse(manySpecs(25)))
    await click(button(/^Reject$/, card('Person 2')))
    const prompt = card('Person 2').querySelector('.ws-feedback')!
    expect(prompt.textContent).toContain("What's missing?")
    expect(prompt.querySelectorAll('.role-chip')).toHaveLength(7)
    await click(button(/Required technology/, prompt as HTMLElement))
    expect(updateCandidateRecord).toHaveBeenCalledWith('role-1', 'c2', { feedback_reason: 'required_technology', feedback_note: undefined })
    expect($$('.ws-slim')).toHaveLength(1) // now collapsed, as a reject always was
  })

  it('a note is optional and saved on its own', async () => {
    await render(makeRoleResponse(manySpecs(25)))
    await click(button(/^Maybe$/, card('Person 3')))
    await click(button(/Add a note/, card('Person 3')))
    const box = card('Person 3').querySelector('textarea') as HTMLTextAreaElement
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(box, 'Unsure about the level')
      box.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await click(button(/Save note/, card('Person 3')))
    expect(updateCandidateRecord).toHaveBeenCalledWith('role-1', 'c3', { feedback_reason: undefined, feedback_note: 'Unsure about the level' })
  })

  it('can be skipped, and a shortlist never asks anything', async () => {
    await render(makeRoleResponse(manySpecs(25)))
    await click(button(/^Maybe$/, card('Person 4')))
    await click(button(/^Skip$/, card('Person 4')))
    expect(card('Person 4').querySelector('.ws-feedback')).toBeNull()
    await click(button(/^Shortlist$/, card('Person 5')))
    expect(card('Person 5').querySelector('.ws-feedback')).toBeNull()
    expect(updateCandidateRecord).not.toHaveBeenCalledWith('role-1', 'c4', expect.objectContaining({ feedback_reason: expect.anything() }))
  })

  it('does not ask again once a reason is on record', async () => {
    const response = makeRoleResponse(manySpecs(25), { extra: { recruiter_decisions: { c1: 'maybe' }, feedback: { c1: { decision: 'maybe', reason: 'type_of_work', note: null } } } })
    await render(response)
    expect(card('Person 1').querySelector('.ws-feedback')).toBeNull()
    expect(card('Person 1').textContent).toContain("Reason: Type of work doesn't quite fit")
  })

  it('does not ask for feedback on a search stored before roles existed', async () => {
    await render(makeResponse(manySpecs(6)))
    await click(button(/^Maybe$/, card('Person 1')))
    expect($('.ws-feedback')).toBeNull()
  })
})

describe('calibration, once', () => {
  it('shows the summary only while it is ready and lets the recruiter remove what is wrong', async () => {
    const ready = makeRoleResponse(manySpecs(25), {
      extra: { calibration: { state: 'ready', summary: { text: "Got it. I'll look for stronger evidence of Kafka.", dimensions: ['technology', 'seniority'], requirements: ['Kafka'] }, dismissed: [] } },
    })
    await render(ready)
    expect($('.role-calibration__text')?.textContent).toBe("Got it. I'll look for stronger evidence of Kafka.")
    await click(button(/Seniority/, $('.role-calibration')!))
    expect(handlers.onCorrectCalibration).toHaveBeenCalledWith(['seniority'])
  })

  it('shows nothing while pending and nothing again once closed', async () => {
    await render(makeRoleResponse(manySpecs(25)))
    expect($('.role-calibration')).toBeNull()
    await render(makeRoleResponse(manySpecs(25), { extra: { calibration: { state: 'closed', summary: { text: 'Got it.', dimensions: [], requirements: [] }, dismissed: [] } } }))
    expect($('.role-calibration')).toBeNull()
  })

  it('has no questionnaire: the only prompts are the ones on a Maybe or a Reject', async () => {
    await render(makeRoleResponse(manySpecs(25)))
    expect(container.textContent).not.toMatch(/What do you like|What should we find more of|What do you think/i)
  })
})

describe('Show me more', () => {
  it('asks for more without another question', async () => {
    await render(makeRoleResponse(manySpecs(25)))
    await click(button(/Show me more/))
    expect(handlers.onShowMore).toHaveBeenCalledTimes(1)
    expect(container.textContent).not.toMatch(/What do you think/i)
  })

  it('says it is finding more while the next retrieval runs, and keeps the candidates on screen', async () => {
    await render(makeRoleResponse(manySpecs(25), { extra: { status: 'running' } }), { searchState: 'searching' })
    expect(names()).toHaveLength(5)
    expect(button(/Finding more candidates/).disabled).toBe(true)
  })

  it('says so plainly, without claiming no one else exists, when nothing more is found', async () => {
    await render(makeRoleResponse(manySpecs(5), { extra: { retrieval_exhausted: true } }))
    const notice = $('.role-more__message')!.textContent!
    expect(notice).toBe("We haven't found additional candidates in the current search.")
    expect(notice).not.toMatch(/no one|nobody|exist|market/i)
  })

  it('shows why a request was refused', async () => {
    await render(makeRoleResponse(manySpecs(25)), { roleMessage: 'RecruiterAI is still working on this search.' })
    expect($('.role-more__message')?.textContent).toBe('RecruiterAI is still working on this search.')
  })
})

describe('search availability', () => {
  it('says nothing when 50 or more profiles were returned', async () => {
    await render(makeRoleResponse(manySpecs(25)))
    expect($('.role-notice')).toBeNull()
  })

  it('reports fewer than 50 as profiles returned, and keeps the separate evidence facts', async () => {
    await render(makeRoleResponse(manySpecs(12), { extra: { availability: { kind: 'narrow', profiles_returned: 12, retrieved: 12 } } }))
    const text = $('.role-notice')!.textContent!
    expect(text).toContain('12 profiles returned for this search.')
    expect(text).toContain('This is a relatively narrow search.')
    expect(text).not.toMatch(/qualified|only 12|market/i)
    expect(names()).toHaveLength(5) // candidates are still reviewed normally
  })

  it('reports zero, offers the brief, and does not also say nothing matched', async () => {
    await render(makeRoleResponse([], { extra: { availability: { kind: 'zero', profiles_returned: 0, retrieved: 0 } } }))
    expect($('.role-notice')!.textContent).toContain('No profiles were returned for this search.')
    expect($('.role-notice')!.textContent).toContain('This search may be too restrictive.')
    expect(container.textContent).not.toContain('No candidates matched this search.')
    await click(button(/Review search criteria/))
    expect($('.discovery-edit-panel')).not.toBeNull()
  })
})

describe('new candidates found in the background', () => {
  const withNew = () => makeRoleResponse(manySpecs(30), { extra: { new_candidates: 5 }, sources: { c26: 'daily', c27: 'daily', c28: 'daily', c29: 'daily', c30: 'daily' } })

  it('is a quiet notice that does not change what is on screen', async () => {
    await render(makeRoleResponse(manySpecs(30)))
    const before = names()
    await render(withNew())
    expect($('.role-new')?.textContent).toContain('5 new candidates ready to review')
    expect(names()).toEqual(before)
  })

  it('shows them only when the recruiter asks', async () => {
    await render(withNew())
    await click(button(/^Review$/))
    expect(handlers.onShowMore).toHaveBeenCalledWith(true)
  })
})

describe('the role and its lifecycle', () => {
  it('shows a searching role and lets the recruiter pause it', async () => {
    await render(makeRoleResponse(manySpecs(25)))
    expect($('.role-bar')?.textContent).toContain('Searching')
    await click(button(/Pause role/))
    expect(handlers.onRoleAction).toHaveBeenCalledWith('pause')
  })

  it('a paused role can be resumed', async () => {
    await render(makeRoleResponse(manySpecs(25), { role: { status: 'paused', pause_reason: 'manual', pause_kind: 'no_engagement' } }))
    expect($('.role-bar')?.textContent).toContain('Paused')
    await click(button(/Resume search/, $('.role-bar')!))
    expect(handlers.onRoleAction).toHaveBeenCalledWith('resume')
  })

  it('a role paused with no engagement asks the recruiter to review, and does not pressure', async () => {
    await render(makeRoleResponse(manySpecs(25), { role: { status: 'paused', pause_reason: 'window_ended', pause_kind: 'no_engagement' } }))
    const panel = $('.role-paused')!.textContent!
    expect(panel).toContain('Your role is paused.')
    expect(panel).toContain("tell us what you're looking for more or less of")
    expect(button(/Review candidates/)).toBeDefined()
    expect(panel).not.toMatch(/expired|days|hurry/i)
  })

  it('a role paused with feedback offers to resume', async () => {
    await render(makeRoleResponse(manySpecs(25), { role: makeRole({ status: 'paused', pause_reason: 'window_ended', pause_kind: 'feedback', has_feedback: true }) }))
    expect($('.role-paused')!.textContent).toContain('Based on your feedback, RecruiterAI has a clearer direction for the search.')
    await click(button(/^Resume search$/, $('.role-paused')!))
    expect(handlers.onRoleAction).toHaveBeenCalledWith('resume')
  })

  it('a narrow role points to the criteria, suggests changes and changes nothing itself', async () => {
    await render(makeRoleResponse(manySpecs(12), { role: { status: 'paused', pause_reason: 'window_ended', pause_kind: 'narrow' }, extra: { availability: { kind: 'narrow', profiles_returned: 12, retrieved: 12 } } }))
    const panel = $('.role-paused')!
    expect(panel.textContent).toContain('This search is very narrow.')
    expect(Array.from(panel.querySelectorAll('li')).map((li) => li.textContent)).toContain('Move a requirement from Core to Supporting')
    await click(button(/Review search criteria/, panel))
    expect($('.discovery-edit-panel')).not.toBeNull()
    expect(handlers.onRunSearch).not.toHaveBeenCalled()
  })

  it('an exhausted search offers to review it or keep the role paused', async () => {
    await render(makeRoleResponse(manySpecs(25), { role: { status: 'paused', pause_reason: 'window_ended', pause_kind: 'exhausted' } }))
    expect($('.role-paused')!.textContent).toContain("We haven't found additional candidates in the current search.")
    expect(button(/^Review search$/)).toBeDefined()
    await click(button(/Keep role paused/))
    expect($('.role-paused')).toBeNull()
    expect($('.role-bar')?.textContent).toContain('Paused')
  })

  it('tells the recruiter when a re-run changed nothing that is searched', async () => {
    await render(makeRoleResponse(manySpecs(25)), { searchNotice: 'Nothing that changes the search was edited, so no new search was run.' })
    expect(container.textContent).toContain('Nothing that changes the search was edited')
  })
})
