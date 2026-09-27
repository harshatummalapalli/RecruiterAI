// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HYBRID_TORONTO, makeIntakeResult } from '../models/livingBriefFixtures'
import { makeRoleResponse, manySpecs } from '../models/roleFixtures'
import type { SearchIntent, SearchListItem } from '../types'

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
  listSearches: vi.fn(),
  showMoreCandidates: vi.fn(),
  setRoleAction: vi.fn(),
  correctCalibration: vi.fn(),
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
const sidebarButton = (label: RegExp) => Array.from(container.querySelectorAll('.app-sidebar__item')).find((b) => label.test(b.textContent ?? '')) as HTMLButtonElement

const PROPOSED: SearchIntent = {
  role: { title: 'Backend-heavy AI Engineer', seniority: 'Senior' },
  location: { countries: ['Canada'], states: ['Ontario'], cities: ['Toronto'], radius_miles: 25, work_mode: 'hybrid' },
  experience: { minimum_years: 8, maximum_years: 10 },
  titles: { include_titles: ['Backend Engineer'], exclude_titles: [] },
  skills: { required_skills: [], preferred_skills: [] },
  previous_background: { preferred_technologies: [], preferred_companies: [] },
  ai_focus: {},
  company_preferences: { exclude_current_companies: [], preferred_company_types: [] },
  ranking: { must_have: [], nice_to_have: [], bonus: [] },
  core_signals: ['Python backend services'],
  supporting_signals: [],
  differentiator_signals: [],
}

const CONFIRMED = {
  confirmation_id: 'conf-1',
  session_id: 'session-1',
  posted_title: 'AI Engineer',
  posted_title_source: 'recruiter' as const,
  candidate_identity: 'Backend-heavy AI Engineer',
  content_hash: 'abc',
}

const item = (id: string, title: string, extra: Partial<SearchListItem> = {}): SearchListItem => ({
  id,
  kind: 'search',
  title,
  company: 'Northwind',
  place: 'Toronto',
  status: 'complete',
  role_status: 'searching',
  pause_kind: null,
  new_count: 0,
  to_review_count: 5,
  updated_at: null,
  ...extra,
})

const LIST = [
  item('role-a', 'AI Engineer'),
  item('role-b', 'Staff Backend Engineer', { company: 'Epiq', place: 'Hyderabad' }),
  item('draft-c', 'Data Engineer', { kind: 'draft', role_status: null }),
]

const roleResponse = (id: string, title: string) =>
  makeRoleResponse(manySpecs(25), { extra: { search_id: id, confirmed_brief: { ...CONFIRMED, session_id: `session-${id}`, posted_title: title } } })

async function mountWithSearches(active: { kind: 'search' | 'draft'; id: string } | null = null) {
  service.listSearches.mockResolvedValue(LIST)
  service.loadPersistedSearch.mockImplementation((id: string) =>
    Promise.resolve(id === 'role-a' ? roleResponse('role-a', 'AI Engineer') : id === 'role-b' ? roleResponse('role-b', 'Staff Backend Engineer') : null),
  )
  service.loadIntakeSession.mockImplementation((id: string) => Promise.resolve({ session_id: id, result: makeIntakeResult(), boundary: HYBRID_TORONTO, posted_title_input: 'Data Engineer' }))
  service.confirmIntake.mockResolvedValue(PROPOSED)
  if (active) window.localStorage.setItem('recruiterai:activeSearch', JSON.stringify(active))
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

describe('the sidebar and switching between searches', () => {
  it('lists every search by title, company and place, and opens the new-search form by default', async () => {
    await mountWithSearches()
    const rows = Array.from(container.querySelectorAll('.app-sidebar__item')).map((row) => row.textContent)
    expect(rows[0]).toContain('AI Engineer')
    expect(rows[0]).toContain('Northwind · Toronto')
    expect(rows[1]).toContain('Staff Backend Engineer')
    expect(rows[1]).toContain('Epiq · Hyderabad')
    expect(rows[2]).toContain('Draft')
    expect($('#posted-title')).not.toBeNull()
    expect($('.app-sidebar__new')?.className).toContain('is-active')
  })

  it('uses the plain intake copy', async () => {
    await mountWithSearches()
    expect(container.querySelector('label[for="posted-title"]')?.textContent?.trim()).toBe('Job Title')
    expect(($('#posted-title') as HTMLInputElement).placeholder).toBe('e.g. AI Engineer')
    expect(container.textContent).toContain("The title you're hiring for.")
    expect(container.textContent).not.toMatch(/Exactly as the role is called|Kept exactly as you type it|optional/i)
  })

  it('opens a search from the sidebar, marks it active, and shows its own candidates', async () => {
    await mountWithSearches()
    await click(sidebarButton(/AI Engineer/))
    await act(async () => {})
    expect(service.loadPersistedSearch).toHaveBeenCalledWith('role-a')
    expect($('.workspace__greeting h1')?.textContent).toBe('AI Engineer')
    expect(sidebarButton(/AI Engineer/).getAttribute('aria-current')).toBe('page')
    expect(sidebarButton(/Staff Backend/).getAttribute('aria-current')).toBeNull()
    expect(container.querySelectorAll('article.ws-card')).toHaveLength(5)
  })

  it('switching to another search restores that search, not the previous one', async () => {
    await mountWithSearches({ kind: 'search', id: 'role-a' })
    expect($('.workspace__greeting h1')?.textContent).toBe('AI Engineer')
    await click(sidebarButton(/Staff Backend/))
    await act(async () => {})
    expect($('.workspace__greeting h1')?.textContent).toBe('Staff Backend Engineer')
    expect(sidebarButton(/Staff Backend/).getAttribute('aria-current')).toBe('page')
    expect(sidebarButton(/AI Engineer/).getAttribute('aria-current')).toBeNull()
    // Each search resumes its own brief.
    expect(service.loadIntakeSession).toHaveBeenCalledWith('session-role-a')
    expect(service.loadIntakeSession).toHaveBeenCalledWith('session-role-b')
  })

  it('remembers which search was open after a reload', async () => {
    await mountWithSearches({ kind: 'search', id: 'role-b' })
    expect($('.workspace__greeting h1')?.textContent).toBe('Staff Backend Engineer')
    expect(JSON.parse(window.localStorage.getItem('recruiterai:activeSearch')!)).toEqual({ kind: 'search', id: 'role-b' })
  })

  it('New search opens a blank form without touching the open search, and Build brief needs a boundary', async () => {
    await mountWithSearches({ kind: 'search', id: 'role-a' })
    await click(button(/New search/))
    expect($('#posted-title')).not.toBeNull()
    expect(($('#posted-title') as HTMLInputElement).value).toBe('')
    expect(button(/Build brief/).disabled).toBe(true)
    expect(service.startIntake).not.toHaveBeenCalled()
    expect(service.runCandidateSearch).not.toHaveBeenCalled()
    expect(window.localStorage.getItem('recruiterai:activeSearch')).toBeNull()
    // Going back to the first search still shows it.
    await click(sidebarButton(/AI Engineer/))
    await act(async () => {})
    expect($('.workspace__greeting h1')?.textContent).toBe('AI Engineer')
  })

  it('keeps a description that was typed but not built when the recruiter looks at another search and comes back', async () => {
    await mountWithSearches()
    const editor = $('textarea[aria-label="Job description"]') as HTMLTextAreaElement
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(editor, 'We need a data engineer')
      editor.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await click(sidebarButton(/AI Engineer/))
    await act(async () => {})
    await click(button(/New search/))
    expect(($('textarea[aria-label="Job description"]') as HTMLTextAreaElement).value).toBe('We need a data engineer')
  })

  it('reopens a brief that was not searched yet, with its own boundary', async () => {
    await mountWithSearches()
    await click(sidebarButton(/Data Engineer/))
    await act(async () => {})
    expect(service.loadIntakeSession).toHaveBeenCalledWith('draft-c')
    expect($('.workspace__brief')).not.toBeNull()
    expect(sidebarButton(/Data Engineer/).getAttribute('aria-current')).toBe('page')
  })

  it('falls back to the new-search form when a remembered search no longer exists', async () => {
    await mountWithSearches({ kind: 'search', id: 'gone' })
    expect($('#posted-title')).not.toBeNull()
  })
})

describe('roles: show more and pause, wired to the server', () => {
  it('asks the server for more, then reloads the search', async () => {
    await mountWithSearches({ kind: 'search', id: 'role-a' })
    service.showMoreCandidates.mockResolvedValue({ presented: 5, cycle_started: false, exhausted: false })
    service.loadPersistedSearch.mockClear()
    await click(button(/Show me more/))
    await act(async () => {})
    expect(service.showMoreCandidates).toHaveBeenCalledWith('role-a', false)
    expect(service.loadPersistedSearch).toHaveBeenCalledWith('role-a')
  })

  it('says so when the server has nothing more to show', async () => {
    await mountWithSearches({ kind: 'search', id: 'role-a' })
    service.showMoreCandidates.mockResolvedValue({ presented: 0, cycle_started: false, exhausted: true })
    await click(button(/Show me more/))
    await act(async () => {})
    expect(container.textContent).toContain("We haven't found additional candidates in the current search.")
  })

  it('pauses the role through the server', async () => {
    await mountWithSearches({ kind: 'search', id: 'role-a' })
    service.setRoleAction.mockResolvedValue(
      makeRoleResponse(manySpecs(25), {
        role: { status: 'paused', pause_reason: 'manual', pause_kind: 'no_engagement' },
        extra: { search_id: 'role-a', confirmed_brief: { ...CONFIRMED, session_id: 'session-role-a', posted_title: 'AI Engineer' } },
      }),
    )
    await click(button(/Pause role/))
    await act(async () => {})
    expect(service.setRoleAction).toHaveBeenCalledWith('role-a', 'pause')
    expect($('.role-bar')?.textContent).toContain('Paused')
  })

  it('re-running with nothing changed says nothing was searched again', async () => {
    await mountWithSearches({ kind: 'search', id: 'role-a' })
    service.createConfirmation.mockResolvedValue({ ...CONFIRMED, confirmation_id: 'conf-9' })
    service.runCandidateSearch.mockResolvedValue(roleResponse('role-a', 'AI Engineer'))
    await click(button(/Edit Brief/))
    await click(button(/Run Search Again/))
    await act(async () => {})
    expect(container.textContent).toContain('Nothing that changes the search was edited, so no new search was run.')
  })
})
