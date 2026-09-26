// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HYBRID_TORONTO, makeBrief, makeIntakeResult } from '../models/livingBriefFixtures'
import { makeResponse } from '../models/workspaceFixtures'
import type { SearchIntent } from '../types'

const service = vi.hoisted(() => ({
  runCandidateSearch: vi.fn(),
  loadPersistedSearch: vi.fn(),
  loadIntakeSession: vi.fn(),
  logout: vi.fn(),
  startIntake: vi.fn(),
  answerIntake: vi.fn(),
  confirmIntake: vi.fn(),
  createConfirmation: vi.fn(),
  updateIntakeBoundary: vi.fn(),
  setWorkspaceArranged: vi.fn(() => Promise.resolve()),
  updateCandidateRecord: vi.fn(() => Promise.resolve({})),
}))
vi.mock('../services/recruiterWorkflow', () => service)

import { RecruiterWorkspaceScreen } from './RecruiterWorkspaceScreen'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let root: Root
let container: HTMLElement

const $ = (selector: string) => container.querySelector(selector) as HTMLElement | null
const button = (label: RegExp) => Array.from(container.querySelectorAll('button')).find((b) => label.test(b.textContent ?? '')) as HTMLButtonElement
const click = (element: Element | null | undefined) =>
  act(async () => {
    element!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })

// What the server proposes for the confirmed brief, as a SearchIntent.
const PROPOSED: SearchIntent = {
  role: { title: 'Backend-heavy AI Engineer', seniority: 'Senior' },
  location: { countries: ['Canada'], states: ['Ontario'], cities: ['Toronto'], radius_miles: 25, work_mode: 'hybrid' },
  experience: { minimum_years: 8, maximum_years: 10 },
  titles: { include_titles: ['Backend Engineer'], exclude_titles: [] },
  skills: { required_skills: [], preferred_skills: [] },
  previous_background: { preferred_technologies: [], preferred_companies: [] },
  ai_focus: {},
  company_preferences: { exclude_current_companies: ['Northwind Payments'], preferred_company_types: [] },
  ranking: { must_have: [], nice_to_have: [], bonus: [] },
  core_signals: ['Python backend services'],
  supporting_signals: [],
  differentiator_signals: [],
}

const CONFIRMED_BRIEF = {
  confirmation_id: 'conf-1',
  session_id: 'session-1',
  posted_title: 'AI Engineer',
  posted_title_source: 'recruiter' as const,
  candidate_identity: 'Backend-heavy AI Engineer',
  content_hash: 'abc',
}

type ConfirmedBriefFixture = Omit<typeof CONFIRMED_BRIEF, 'posted_title' | 'posted_title_source'> & {
  posted_title: string | null
  posted_title_source: 'recruiter' | 'jd' | null
}

async function mountRestoredSearch(confirmedBrief: ConfirmedBriefFixture | null = CONFIRMED_BRIEF, intake = makeIntakeResult()) {
  window.localStorage.setItem(
    'recruiterai:lastSearch',
    JSON.stringify({ searchId: 'search-1', jdText: 'Some JD', brief: makeBrief(), intakeSessionId: 'session-1' }),
  )
  service.loadPersistedSearch.mockResolvedValue(
    makeResponse([{ name: 'Ada', core: [true, true], years: 'met' }], { workspace_arranged: true, confirmed_brief: confirmedBrief }),
  )
  service.loadIntakeSession.mockResolvedValue({ session_id: 'session-1', result: intake, boundary: HYBRID_TORONTO, posted_title_input: intake.role_understanding.posted_title })
  service.confirmIntake.mockResolvedValue(PROPOSED)
  await act(async () => {
    root.render(<RecruiterWorkspaceScreen />)
  })
  await act(async () => {})
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  vi.clearAllMocks()
  window.localStorage.clear()
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
})

describe('the workspace header', () => {
  it('shows the POSTED title as the role and the candidate identity separately', async () => {
    await mountRestoredSearch()
    expect($('.workspace__greeting h1')?.textContent).toBe('AI Engineer')
    expect($('.workspace__identity')?.textContent).toContain('Backend-heavy AI Engineer')
    expect($('.workspace__identity-label')?.textContent).toBe('Searching for')
  })

  it('names the role after a reload from the stored search alone, with no browser state about the title', async () => {
    await mountRestoredSearch()
    window.localStorage.setItem(
      'recruiterai:lastSearch',
      JSON.stringify({ searchId: 'search-1', jdText: '', brief: makeBrief({ role: { ...makeBrief().role, primaryTitle: '' } }) }),
    )
    act(() => root.unmount())
    root = createRoot(container)
    await act(async () => {
      root.render(<RecruiterWorkspaceScreen />)
    })
    await act(async () => {})
    expect($('.workspace__greeting h1')?.textContent).toBe('AI Engineer')
  })

  it('does not show a second line when the identity is the posted title', async () => {
    await mountRestoredSearch({ ...CONFIRMED_BRIEF, candidate_identity: 'ai engineer' })
    expect($('.workspace__identity')).toBeNull()
  })

  it('falls back to the identity, never invents a posted title, when there is none', async () => {
    const intake = makeIntakeResult()
    intake.role_understanding.posted_title = null
    intake.role_understanding.posted_title_source = null
    await mountRestoredSearch({ ...CONFIRMED_BRIEF, posted_title: null, posted_title_source: null }, intake)
    expect($('.workspace__greeting h1')?.textContent).toBe('Backend-heavy AI Engineer')
    expect($('.workspace__identity')).toBeNull()
  })
})

describe('searching again goes through a confirmation, never a browser-built intent', () => {
  it('confirms first, then searches by confirmation id alone', async () => {
    service.createConfirmation.mockResolvedValue({ ...CONFIRMED_BRIEF, confirmation_id: 'conf-2' })
    service.runCandidateSearch.mockResolvedValue(makeResponse([{ name: 'Ada', core: [true], years: 'met', state: 'building_context' }], { status: 'running', confirmed_brief: { ...CONFIRMED_BRIEF, confirmation_id: 'conf-2' } }))
    await mountRestoredSearch()

    await click(button(/Edit Brief/))
    await click(button(/Run Search Again/))

    expect(service.createConfirmation).toHaveBeenCalledTimes(1)
    const [sessionId, edits] = service.createConfirmation.mock.calls[0]
    expect(sessionId).toBe('session-1')
    expect(service.runCandidateSearch).toHaveBeenCalledTimes(1)
    const [confirmationId, options] = service.runCandidateSearch.mock.calls[0]
    expect(confirmationId).toBe('conf-2')
    // The only things sent are the id and bookkeeping: no intent, no location, no requirements.
    expect(service.runCandidateSearch.mock.calls[0]).toHaveLength(2)
    expect(Object.keys(options).sort()).toEqual(['debug', 'searchId'])
    // The stored working copy differs from the proposal only in ways the recruiter did not touch, so nothing is edited.
    expect(Object.keys(edits as object).every((key) => !/location|work_mode|company$/.test(key))).toBe(true)
  })

  it('explains a refusal in plain words and does not search', async () => {
    service.createConfirmation.mockRejectedValue(Object.assign(new Error('x'), { messages: ['1 question still needs your answer.'] }))
    await mountRestoredSearch()
    await click(button(/Edit Brief/))
    await click(button(/Run Search Again/))
    expect(service.runCandidateSearch).not.toHaveBeenCalled()
    expect($('.workspace__status--error')?.textContent).toContain('1 question still needs your answer.')
  })
})

describe('editing the boundary from the workspace', () => {
  it('is deterministic: it calls the boundary endpoint, not the search or an answer', async () => {
    service.updateIntakeBoundary.mockResolvedValue({ session_id: 'session-1', result: makeIntakeResult(), boundary: { ...HYBRID_TORONTO, radius_miles: 40 } })
    await mountRestoredSearch()
    await click(button(/Edit Brief/))
    await click(button(/Edit boundary/))
    await click(button(/^Apply$/))
    expect(service.updateIntakeBoundary).toHaveBeenCalledTimes(1)
    expect(service.updateIntakeBoundary.mock.calls[0][0]).toBe('session-1')
    expect(service.answerIntake).not.toHaveBeenCalled()
    expect(service.startIntake).not.toHaveBeenCalled()
    expect(service.runCandidateSearch).not.toHaveBeenCalled()
  })

  it('offers no location or work-mode fields in the brief editor, only the boundary', async () => {
    await mountRestoredSearch()
    await click(button(/Edit Brief/))
    const panel = $('.discovery-edit-panel')!.textContent!
    expect(panel).toContain('Search boundary')
    expect(panel).not.toMatch(/Search geography|Work Mode\b(?!.*boundary)/)
  })
})
