// Role workspace view model: multiple searches, the first five, reserve, availability, pause messages and the wording
// of decision feedback. Pure functions over what the server already decided. Nothing here scores, ranks or interprets a
// candidate; it only chooses which stored facts to show and in which words.

import type { CalibrationState, PauseKind, RoleState, SearchAvailability, SearchListItem, SearchResponse } from '../types'

// ---- decision feedback -------------------------------------------------------------------------------------------------

export type FeedbackOption = { value: string; label: string }

export const MAYBE_PROMPT = 'What makes you unsure?'
export const REJECT_PROMPT = "What's missing?"

export const MAYBE_REASONS: FeedbackOption[] = [
  { value: 'experience_unclear', label: "Relevant experience isn't clear" },
  { value: 'skill_not_demonstrated', label: "Required skill isn't demonstrated" },
  { value: 'seniority_unclear', label: 'Seniority is unclear' },
  { value: 'type_of_work', label: "Type of work doesn't quite fit" },
  { value: 'other', label: 'Other' },
]

export const REJECT_REASONS: FeedbackOption[] = [
  { value: 'required_experience', label: 'Required experience' },
  { value: 'required_technology', label: 'Required technology' },
  { value: 'type_of_work', label: 'Relevant type of work' },
  { value: 'seniority', label: 'Seniority' },
  { value: 'domain', label: 'Domain/industry' },
  { value: 'career_background', label: 'Career background' },
  { value: 'other', label: 'Other' },
]

export function feedbackPrompt(decision: 'maybe' | 'reject'): { question: string; options: FeedbackOption[] } {
  return decision === 'maybe' ? { question: MAYBE_PROMPT, options: MAYBE_REASONS } : { question: REJECT_PROMPT, options: REJECT_REASONS }
}

export function reasonLabel(decision: string | null | undefined, reason: string | null | undefined): string | null {
  if (!reason) return null
  const options = decision === 'maybe' ? MAYBE_REASONS : decision === 'reject' ? REJECT_REASONS : []
  return options.find((option) => option.value === reason)?.label ?? null
}

// ---- what is shown, and what is kept -------------------------------------------------------------------------------------

/** A search stored before roles existed has no presentation: every candidate is shown, as it always was. */
export function isRoleSearch(response: SearchResponse | null | undefined): boolean {
  return Boolean(response?.role)
}

export function splitByPresentation<T extends { candidate: { id: string } }>(items: T[], response: SearchResponse | null | undefined): { presented: T[]; reserve: T[] } {
  if (!isRoleSearch(response)) return { presented: items, reserve: [] }
  const presentation = response?.presentation ?? {}
  const presented: T[] = []
  const reserve: T[] = []
  for (const item of items) {
    // A candidate the server has not classified yet (a cycle still filling in) is held back, never shown early.
    if (presentation[item.candidate.id]?.state === 'presented') presented.push(item)
    else reserve.push(item)
  }
  return { presented, reserve }
}

/**
 * The display order of the candidates on screen, and nothing else. Sets stay in the order they were shown (the first
 * five, then each "Show me more"), so nothing already on screen moves when more arrives. Inside a set, the candidate with
 * the most core requirements shown on their profile comes first (the same non-years core count the cards already show).
 * Ties keep the order the search returned them in, which is the existing evidence ordering (score, demonstrated work,
 * freshness). No score is computed, no candidate is added or removed, and decisions never change the order.
 */
export function orderPresented<T extends { candidate: { id: string }; facts: { shown: number } }>(items: T[], response: SearchResponse | null | undefined): T[] {
  const presentation = response?.presentation ?? {}
  return items
    .map((item, index) => ({ item, index, batch: presentation[item.candidate.id]?.batch ?? 0 }))
    .sort((a, b) => a.batch - b.batch || b.item.facts.shown - a.item.facts.shown || a.index - b.index)
    .map((entry) => entry.item)
}

export const ROLE_ORDER_NOTE = 'Most core requirements shown first.'

export function reviewHeading(presentedCount: number, undecidedCount: number): string | null {
  if (presentedCount === 0) return null
  if (undecidedCount === 0) return 'Everyone shown so far has a decision'
  return `${undecidedCount} candidate${undecidedCount === 1 ? '' : 's'} to review`
}

export function otherReviewedLabel(count: number): string {
  return `${count} other reviewed candidate${count === 1 ? '' : 's'}`
}

// ---- search availability: what the provider returned, never a count of qualified candidates ---------------------------------------

export type Notice = { title: string; body: string }

export function availabilityNotice(availability: SearchAvailability | null | undefined): Notice | null {
  if (!availability) return null
  if (availability.kind === 'zero') {
    return {
      title: 'No profiles were returned for this search.',
      body: 'This search may be too restrictive. Review the brief or broaden the search criteria.',
    }
  }
  if (availability.kind === 'narrow') {
    const n = availability.profiles_returned
    return {
      title: `${n} ${n === 1 ? 'profile' : 'profiles'} returned for this search.`,
      body: 'This is a relatively narrow search. RecruiterAI will work through the available profiles and show the strongest evidence first.',
    }
  }
  return null
}

// ---- role status and the paused messages ---------------------------------------------------------------------------------------

export type PauseAction = 'review' | 'resume' | 'criteria' | 'more'

export type PauseCopy = {
  title: string
  body: string
  primary: { action: PauseAction; label: string }
  secondary: { action: 'keep_paused' | 'criteria'; label: string } | null
  suggestions: string[]
}

const NARROW_SUGGESTIONS = [
  'Broaden the location',
  'Relax the experience',
  'Move a requirement from Core to Supporting',
  'Remove a narrow requirement',
  'Broaden the title family',
]

export function isPaused(role: RoleState | null | undefined): boolean {
  return role?.status === 'paused'
}

/** What a paused role says and offers. Only facts the server observed; nothing claims the market is exhausted. */
export function pauseCopy(role: RoleState): PauseCopy | null {
  if (!isPaused(role)) return null
  const kind: PauseKind | null = role.pause_kind
  if (kind === 'narrow') {
    return {
      title: 'This search is very narrow.',
      body: "The current brief is returning very few profiles. RecruiterAI doesn't have enough additional candidates to continue without changing the criteria.",
      primary: { action: 'criteria', label: 'Review search criteria' },
      secondary: null,
      suggestions: NARROW_SUGGESTIONS,
    }
  }
  if (kind === 'exhausted') {
    return {
      title: "We haven't found additional candidates in the current search.",
      body: 'You can review the search, or leave the role paused.',
      primary: { action: 'criteria', label: 'Review search' },
      secondary: { action: 'keep_paused', label: 'Keep role paused' },
      suggestions: [],
    }
  }
  if (role.pause_reason === 'manual') {
    return {
      title: 'Your role is paused.',
      body: 'Searching is paused. Your candidates, decisions and feedback are kept.',
      primary: role.can_resume ? { action: 'resume', label: 'Resume search' } : { action: 'more', label: 'Show me more' },
      secondary: null,
      suggestions: [],
    }
  }
  if (kind === 'feedback') {
    return {
      title: 'Your role is paused.',
      body: 'Based on your feedback, RecruiterAI has a clearer direction for the search.',
      primary: role.can_resume ? { action: 'resume', label: 'Resume search' } : { action: 'more', label: 'Show me more' },
      secondary: null,
      suggestions: [],
    }
  }
  return {
    title: 'Your role is paused.',
    body: "Review the candidates and tell us what you're looking for more or less of. That will help RecruiterAI refine the next search.",
    primary: { action: 'review', label: 'Review candidates' },
    secondary: null,
    suggestions: [],
  }
}

export function roleStatusLabel(role: RoleState | null | undefined, running: boolean): string | null {
  if (!role) return null
  if (role.status === 'paused') return 'Paused'
  return running ? 'Finding candidates' : 'Searching'
}

// ---- calibration ---------------------------------------------------------------------------------------------------------------------

export const DIMENSION_LABEL: Record<string, string> = {
  technology: 'Required technology',
  experience: 'Relevant experience',
  seniority: 'Seniority',
  work_type: 'Type of work',
}

/** The one-time note is shown while it is ready; once the recruiter asks for more it is closed for good. */
export function calibrationNote(calibration: CalibrationState | null | undefined): { text: string; dimensions: string[] } | null {
  if (!calibration || calibration.state !== 'ready' || !calibration.summary) return null
  return { text: calibration.summary.text, dimensions: calibration.summary.dimensions }
}

// ---- the sidebar --------------------------------------------------------------------------------------------------------------------

export function sidebarSubtitle(item: Pick<SearchListItem, 'company' | 'place'>): string {
  return [item.company, item.place].filter(Boolean).join(' · ')
}

export type SidebarBadge = { text: string; tone: 'new' | 'paused' | 'draft' } | null

export function sidebarBadge(item: SearchListItem): SidebarBadge {
  if (item.kind === 'draft') return { text: 'Draft', tone: 'draft' }
  if (item.new_count > 0) return { text: `${item.new_count} new`, tone: 'new' }
  if (item.role_status === 'paused') return { text: 'Paused', tone: 'paused' }
  return null
}

export type ActiveSearch = { kind: 'search' | 'draft'; id: string }

export function isActive(item: SearchListItem, active: ActiveSearch | null): boolean {
  return Boolean(active) && active?.id === item.id && active?.kind === item.kind
}

// ---- new candidates found in the background -------------------------------------------------------------------------------------------

export function newCandidatesNotice(count: number): string | null {
  if (count <= 0) return null
  return count === 1 ? '1 new candidate ready to review' : `${count} new candidates ready to review`
}
