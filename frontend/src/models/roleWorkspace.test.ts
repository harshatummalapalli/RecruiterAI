import { describe, expect, it } from 'vitest'
import type { RoleState, SearchListItem, SearchResponse } from '../types'
import {
  MAYBE_REASONS,
  REJECT_REASONS,
  availabilityNotice,
  calibrationNote,
  feedbackPrompt,
  isActive,
  newCandidatesNotice,
  otherReviewedLabel,
  pauseCopy,
  reasonLabel,
  reviewHeading,
  roleStatusLabel,
  sidebarBadge,
  sidebarSubtitle,
  splitByPresentation,
} from './roleWorkspace'

const role = (extra: Partial<RoleState> = {}): RoleState => ({
  status: 'paused',
  pause_reason: 'window_ended',
  pause_kind: 'no_engagement',
  can_resume: true,
  has_feedback: false,
  exhausted: false,
  label: {},
  ...extra,
})

const item = (id: string) => ({ candidate: { id } })

describe('what is shown and what is kept', () => {
  const response = (presentation: SearchResponse['presentation']): SearchResponse =>
    ({ role: role({ status: 'searching', pause_reason: null, pause_kind: null }), presentation } as unknown as SearchResponse)

  it('shows only the presented candidates and keeps the rest as other reviewed candidates', () => {
    const items = ['a', 'b', 'c', 'd'].map(item)
    const { presented, reserve } = splitByPresentation(items, response({ a: { state: 'presented', source: 'initial', seen: true, stale: false }, b: { state: 'reserve', source: 'initial', seen: false, stale: false }, c: { state: 'presented', source: 'initial', seen: true, stale: false }, d: { state: 'reserve', source: 'daily', seen: false, stale: true } }))
    expect(presented.map((x) => x.candidate.id)).toEqual(['a', 'c'])
    expect(reserve.map((x) => x.candidate.id)).toEqual(['b', 'd'])
  })

  it('shows everything for a search stored before roles existed', () => {
    const items = ['a', 'b'].map(item)
    const legacy = { role: null, presentation: null } as unknown as SearchResponse
    expect(splitByPresentation(items, legacy)).toEqual({ presented: items, reserve: [] })
    expect(splitByPresentation(items, null)).toEqual({ presented: items, reserve: [] })
  })

  it('holds back a candidate the server has not classified yet', () => {
    const { presented, reserve } = splitByPresentation([item('x')], response({}))
    expect(presented).toEqual([])
    expect(reserve).toHaveLength(1)
  })

  it('words the heading and the other-reviewed count from the counts, without ranking words', () => {
    expect(reviewHeading(5, 5)).toBe('5 candidates to review')
    expect(reviewHeading(5, 1)).toBe('1 candidate to review')
    expect(reviewHeading(5, 0)).toBe('Everyone shown so far has a decision')
    expect(reviewHeading(0, 0)).toBeNull()
    expect(otherReviewedLabel(20)).toBe('20 other reviewed candidates')
    expect(otherReviewedLabel(1)).toBe('1 other reviewed candidate')
    for (const text of [reviewHeading(5, 5), otherReviewedLabel(20)]) {
      expect(text).not.toMatch(/top|best|excellent|good|rank|score/i)
    }
  })
})

describe('search availability', () => {
  it('says nothing for a search that returned 50 or more profiles', () => {
    expect(availabilityNotice({ kind: 'ok', profiles_returned: 50, retrieved: 50 })).toBeNull()
    expect(availabilityNotice(null)).toBeNull()
  })

  it('reports zero factually', () => {
    expect(availabilityNotice({ kind: 'zero', profiles_returned: 0, retrieved: 0 })).toEqual({
      title: 'No profiles were returned for this search.',
      body: 'This search may be too restrictive. Review the brief or broaden the search criteria.',
    })
  })

  it('reports fewer than fifty as profiles returned, never as qualified candidates', () => {
    const notice = availabilityNotice({ kind: 'narrow', profiles_returned: 12, retrieved: 12 })!
    expect(notice.title).toBe('12 profiles returned for this search.')
    expect(notice.body).toContain('relatively narrow search')
    expect(`${notice.title} ${notice.body}`).not.toMatch(/qualified|only \d+|market|exist/i)
    expect(availabilityNotice({ kind: 'narrow', profiles_returned: 1, retrieved: 1 })!.title).toBe('1 profile returned for this search.')
  })
})

describe('paused roles', () => {
  it('asks a role with no engagement to review, without pressure', () => {
    const copy = pauseCopy(role())!
    expect(copy.title).toBe('Your role is paused.')
    expect(copy.body).toContain("tell us what you're looking for more or less of")
    expect(copy.primary).toEqual({ action: 'review', label: 'Review candidates' })
    expect(`${copy.title} ${copy.body}`).not.toMatch(/expired|days|hurry|running out/i)
  })

  it('offers to resume a role with meaningful feedback, without claiming it has learned', () => {
    const copy = pauseCopy(role({ pause_kind: 'feedback', has_feedback: true }))!
    expect(copy.body).toBe('Based on your feedback, RecruiterAI has a clearer direction for the search.')
    expect(copy.primary).toEqual({ action: 'resume', label: 'Resume search' })
    expect(copy.body).not.toMatch(/learned|understand your preferences/i)
  })

  it('offers to show more, not resume, when the automatic search has run its course', () => {
    expect(pauseCopy(role({ pause_kind: 'feedback', can_resume: false }))!.primary).toEqual({ action: 'more', label: 'Show me more' })
  })

  it('a narrow role points to the criteria and suggests changes without making them', () => {
    const copy = pauseCopy(role({ pause_kind: 'narrow' }))!
    expect(copy.title).toBe('This search is very narrow.')
    expect(copy.primary).toEqual({ action: 'criteria', label: 'Review search criteria' })
    expect(copy.suggestions).toEqual(['Broaden the location', 'Relax the experience', 'Move a requirement from Core to Supporting', 'Remove a narrow requirement', 'Broaden the title family'])
    expect(`${copy.title} ${copy.body}`).not.toMatch(/no one|exhausted|market/i)
  })

  it('an exhausted search does not claim no one else exists', () => {
    const copy = pauseCopy(role({ pause_kind: 'exhausted' }))!
    expect(copy.title).toBe("We haven't found additional candidates in the current search.")
    expect(copy.primary.label).toBe('Review search')
    expect(copy.secondary).toEqual({ action: 'keep_paused', label: 'Keep role paused' })
    expect(copy.title).not.toMatch(/no one|nobody|exist/i)
  })

  it('a manual pause keeps everything and offers to resume', () => {
    const copy = pauseCopy(role({ pause_reason: 'manual', pause_kind: 'no_engagement' }))!
    expect(copy.body).toContain('kept')
    expect(copy.primary.action).toBe('resume')
  })

  it('a searching role has no paused message', () => {
    expect(pauseCopy(role({ status: 'searching', pause_kind: null, pause_reason: null }))).toBeNull()
    expect(roleStatusLabel(role({ status: 'searching' }), false)).toBe('Searching')
    expect(roleStatusLabel(role({ status: 'searching' }), true)).toBe('Finding candidates')
    expect(roleStatusLabel(role(), false)).toBe('Paused')
    expect(roleStatusLabel(null, false)).toBeNull()
  })
})

describe('decision feedback wording', () => {
  it('asks the two questions in the agreed words with the agreed options', () => {
    expect(feedbackPrompt('maybe').question).toBe('What makes you unsure?')
    expect(feedbackPrompt('reject').question).toBe("What's missing?")
    expect(MAYBE_REASONS.map((o) => o.label)).toEqual([
      "Relevant experience isn't clear",
      "Required skill isn't demonstrated",
      'Seniority is unclear',
      "Type of work doesn't quite fit",
      'Other',
    ])
    expect(REJECT_REASONS.map((o) => o.label)).toEqual([
      'Required experience',
      'Required technology',
      'Relevant type of work',
      'Seniority',
      'Domain/industry',
      'Career background',
      'Other',
    ])
  })

  it('names a stored reason for the decision it belongs to', () => {
    expect(reasonLabel('reject', 'required_technology')).toBe('Required technology')
    expect(reasonLabel('maybe', 'seniority_unclear')).toBe('Seniority is unclear')
    expect(reasonLabel('shortlist', 'other')).toBeNull()
    expect(reasonLabel('maybe', null)).toBeNull()
  })
})

describe('calibration', () => {
  it('shows the one-time note only while it is ready', () => {
    const summary = { text: "Got it. I'll look for stronger evidence of Kafka.", dimensions: ['technology'], requirements: ['Kafka'] }
    expect(calibrationNote({ state: 'ready', summary, dismissed: [] })).toEqual({ text: summary.text, dimensions: ['technology'] })
    expect(calibrationNote({ state: 'pending', summary: null, dismissed: [] })).toBeNull()
    expect(calibrationNote({ state: 'closed', summary, dismissed: [] })).toBeNull()
    expect(calibrationNote(null)).toBeNull()
  })
})

describe('sidebar', () => {
  const base: SearchListItem = { id: 's1', kind: 'search', title: 'AI Engineer', company: 'Northwind', place: 'Toronto', status: 'complete', role_status: 'searching', pause_kind: null, new_count: 0, to_review_count: 3, updated_at: null }

  it('names a role by title, company and place', () => {
    expect(sidebarSubtitle(base)).toBe('Northwind · Toronto')
    expect(sidebarSubtitle({ company: '', place: 'Toronto' })).toBe('Toronto')
    expect(sidebarSubtitle({ company: '', place: '' })).toBe('')
  })

  it('shows one quiet badge at most', () => {
    expect(sidebarBadge(base)).toBeNull()
    expect(sidebarBadge({ ...base, role_status: 'paused' })).toEqual({ text: 'Paused', tone: 'paused' })
    expect(sidebarBadge({ ...base, new_count: 5, role_status: 'paused' })).toEqual({ text: '5 new', tone: 'new' })
    expect(sidebarBadge({ ...base, kind: 'draft', role_status: null })).toEqual({ text: 'Draft', tone: 'draft' })
  })

  it('marks the active search, and a draft and a search never share an id match', () => {
    expect(isActive(base, { kind: 'search', id: 's1' })).toBe(true)
    expect(isActive(base, { kind: 'draft', id: 's1' })).toBe(false)
    expect(isActive(base, null)).toBe(false)
  })

  it('words the quiet new-candidates signal', () => {
    expect(newCandidatesNotice(5)).toBe('5 new candidates ready to review')
    expect(newCandidatesNotice(1)).toBe('1 new candidate ready to review')
    expect(newCandidatesNotice(0)).toBeNull()
  })
})
