// Living Brief view model. Pure functions over what the server already decided: nothing here interprets a role,
// scores anything or invents a claim. It only arranges facts and says where each one came from.
//
// Provenance is not decoration. Each tag answers one question the recruiter would otherwise have to guess:
//   stated       the job description says it (the SERVER matched the requirement to a sentence of the input)
//   inferred     the model concluded it; the input does not say it
//   confirmed    the recruiter answered a question that set it
//   warning      something argues against the brief as written
//   limitation   something the system cannot enforce

import type { ConfirmationEdits, FieldValue, IntakeIssue, IntakeResult } from './intake'
import { pendingAskIssues, tellInsights } from './intake'
import type { SearchBoundary } from './searchBoundary'
import { isSearchBoundaryComplete } from './searchBoundary'
import type { SearchBrief } from './searchBrief'

export type ProvenanceKind = 'stated' | 'inferred' | 'confirmed' | 'warning' | 'limitation'

export const PROVENANCE_LABEL: Record<ProvenanceKind, string> = {
  stated: 'Stated in JD',
  inferred: 'Inferred',
  confirmed: 'Confirmed by you',
  warning: 'Warning',
  limitation: 'System limitation',
}

export type RequirementTier = 'core' | 'supporting' | 'preferred'

export const TIER_LABEL: Record<RequirementTier, string> = { core: 'Core', supporting: 'Supporting', preferred: 'Preferred' }

export type RequirementItem = { text: string; provenance: 'stated' | 'inferred' | 'confirmed'; evidence: string | null }
export type RequirementGroup = { tier: RequirementTier; label: string; items: RequirementItem[] }

function normalize(text: string): string {
  return (text ?? '')
    .toLowerCase()
    .replace(/[^a-z0-9+#.]+/g, ' ')
    .trim()
}

/** Core / Supporting / Preferred exactly as the search will use them, each with where it came from. */
export function requirementGroups(result: IntakeResult): RequirementGroup[] {
  const draft = result.decision.final_search_intent
  const evidence = draft.evidence ?? {}
  const confirmed = new Set(
    (result.confirmed ?? []).filter((change) => change.field === 'requirement' && change.item).map((change) => normalize(change.item as string)),
  )
  const build = (tier: RequirementTier, texts: string[]): RequirementGroup => ({
    tier,
    label: TIER_LABEL[tier],
    items: texts.map((text) => {
      const quote = evidence[text] ?? null
      const provenance = confirmed.has(normalize(text)) ? 'confirmed' : quote ? 'stated' : 'inferred'
      return { text, provenance, evidence: quote }
    }),
  })
  return [
    build('core', draft.hard_requirements ?? []),
    build('supporting', draft.strong_signals ?? []),
    build('preferred', draft.preferred_differentiators ?? []),
  ]
}

export function fieldProvenance(value: FieldValue | null | undefined): 'stated' | 'inferred' | 'confirmed' | null {
  if (!value || !value.value) return null
  if (value.source === 'recruiter') return 'confirmed'
  if (value.source === 'explicit') return 'stated'
  if (value.source === 'inferred') return 'inferred'
  return null
}

export function experienceView(result: IntakeResult): { text: string; provenance: 'stated' | 'confirmed' } | null {
  const { experience_minimum_years: minimum, experience_maximum_years: maximum } = result.role_understanding.explicit_constraints
  const confirmed = (result.confirmed ?? []).some((change) => change.field === 'experience')
  let text: string | null = null
  if (minimum && maximum) text = `${minimum}–${maximum} years`
  else if (minimum) text = `${minimum}+ years`
  else if (maximum) text = `Up to ${maximum} years`
  return text ? { text, provenance: confirmed ? 'confirmed' : 'stated' } : null
}

export type TitleView = {
  posted: string | null
  postedNote: 'As you wrote it' | 'As written in the JD' | null
  identity: string | null
  identityProvenance: 'stated' | 'inferred' | 'confirmed' | null
  /** True only when the candidate identity materially differs from the posted title. Then, and only then, the brief
   * explains the difference. */
  identityDiffers: boolean
  identityReason: string | null
}

/** The posted title and the candidate identity are two things and are never merged: the posted title is what the role
 * was called; the identity is what RecruiterAI believes should be searched for. */
export function titleView(result: IntakeResult): TitleView {
  const role = result.role_understanding
  const posted = role.posted_title?.trim() || null
  const identity = role.primary_candidate_identity.value?.trim() || null
  const differs = Boolean(posted && identity && normalize(posted) !== normalize(identity))
  return {
    posted,
    postedNote: posted ? (role.posted_title_source === 'recruiter' ? 'As you wrote it' : 'As written in the JD') : null,
    identity,
    identityProvenance: fieldProvenance(role.primary_candidate_identity),
    identityDiffers: differs,
    identityReason: differs ? role.primary_candidate_identity.evidence?.trim() || null : null,
  }
}

export type BriefState = 'draft' | 'ready'

export type ReadyStatus = {
  state: BriefState
  /** Recruiter-readable reasons the search cannot start yet. Empty when ready. */
  blockers: string[]
  /** All the questions still open, in the order they will be asked. */
  questions: IntakeIssue[]
}

/** Ready means exactly this and nothing more: a valid boundary, no open question of any origin, and the reading is
 * complete. A zero-core brief or a narrow search does not block. */
export function readyStatus(result: IntakeResult | null, boundary: SearchBoundary | null): ReadyStatus {
  if (!result) return { state: 'draft', blockers: ['The role has not been read yet.'], questions: [] }
  const questions = pendingAskIssues(result)
  const blockers: string[] = []
  if (!boundary || !isSearchBoundaryComplete(boundary)) blockers.push('The search boundary is incomplete.')
  if (questions.length) blockers.push(`${questions.length} decision${questions.length === 1 ? '' : 's'} still need${questions.length === 1 ? 's' : ''} your answer.`)
  return { state: blockers.length ? 'draft' : 'ready', blockers, questions }
}

/** Up to two notes the recruiter should read (TELL issues that carry text). */
export function recruiterNotes(result: IntakeResult): string[] {
  return tellInsights(result)
    .map((issue) => issue.insight_text as string)
    .slice(0, 3)
}

export function formatBoundaryLocation(boundary: SearchBoundary): string {
  if (boundary.work_mode === 'onsite' || boundary.work_mode === 'hybrid') {
    const place = [boundary.city, boundary.state, boundary.country].filter(Boolean).join(', ')
    return boundary.radius_miles ? `${place} · ${boundary.radius_miles} mi radius` : place
  }
  if (boundary.remote_scope === 'states' && boundary.remote_states.length) return `${boundary.remote_states.join(', ')}, ${boundary.country}`
  if (boundary.remote_scope === 'cities' && boundary.remote_cities.length) return `${boundary.remote_cities.join(', ')}, ${boundary.country}`
  return `Anywhere in ${boundary.country}`
}

export function workModeLabel(boundary: SearchBoundary): string {
  return boundary.work_mode ? boundary.work_mode.charAt(0).toUpperCase() + boundary.work_mode.slice(1) : ''
}

function sameList(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((value, index) => value === b[index])
}

function years(value: string): number | null {
  const parsed = Number(value)
  return value.trim() && Number.isFinite(parsed) ? parsed : null
}

/**
 * Only what the recruiter actually changed on the "Adjust before searching" panel, compared with what the server
 * proposed. Location, work mode and company are the Search Boundary's, so they are never here. Sending only real
 * changes keeps an unedited brief identical to what the server built.
 */
export function diffBriefEdits(baseline: SearchBrief, current: SearchBrief): ConfirmationEdits {
  const edits: ConfirmationEdits = {}
  if (current.role.primaryTitle.trim() !== baseline.role.primaryTitle.trim() && current.role.primaryTitle.trim()) {
    edits.candidate_identity = current.role.primaryTitle.trim()
  }
  if (current.role.seniority !== baseline.role.seniority) edits.seniority = current.role.seniority.trim() || null
  if (!sameList(current.role.equivalentTitles, baseline.role.equivalentTitles)) edits.include_titles = current.role.equivalentTitles
  if (!sameList(current.role.excludedTitles, baseline.role.excludedTitles)) edits.exclude_titles = current.role.excludedTitles
  if (current.experience.minimumYears !== baseline.experience.minimumYears) edits.minimum_years = years(current.experience.minimumYears)
  if (current.experience.maximumYears !== baseline.experience.maximumYears) edits.maximum_years = years(current.experience.maximumYears)

  const before = baseline.requirements ?? { core: [], supporting: [], differentiators: [] }
  const after = current.requirements ?? before
  if (!sameList(after.core, before.core)) edits.core_signals = after.core
  if (!sameList(after.supporting, before.supporting)) edits.supporting_signals = after.supporting
  if (!sameList(after.differentiators, before.differentiators)) edits.differentiator_signals = after.differentiators

  if (!sameList(current.companies.exclude, baseline.companies.exclude)) edits.exclude_current_companies = current.companies.exclude
  if (!sameList(current.companies.include, baseline.companies.include)) edits.preferred_companies = current.companies.include
  if (current.employmentTypes[0] !== baseline.employmentTypes[0]) edits.employment_type = current.employmentTypes[0] ?? null
  return edits
}

export type ConfirmationLine = { label: string; value: string }

/** "This is what I will search for": the executable brief in the recruiter's own terms. No queries, no filters, no
 * provider language. */
export function confirmationSummary(result: IntakeResult, boundary: SearchBoundary, brief: SearchBrief): ConfirmationLine[] {
  const title = titleView(result)
  const groups = requirementGroups(result)
  const core = brief.requirements?.core ?? groups[0].items.map((item) => item.text)
  const supporting = brief.requirements?.supporting ?? groups[1].items.map((item) => item.text)
  const preferred = brief.requirements?.differentiators ?? groups[2].items.map((item) => item.text)
  const minimum = brief.experience.minimumYears
  const maximum = brief.experience.maximumYears
  const experience = minimum && maximum ? `${minimum}–${maximum} years` : minimum ? `${minimum}+ years` : maximum ? `up to ${maximum} years` : null

  const lines: ConfirmationLine[] = [
    { label: 'Looking for', value: [brief.role.primaryTitle || title.identity || title.posted || 'Role not named', brief.role.seniority].filter(Boolean).join(' · ') },
  ]
  if (experience) lines.push({ label: 'Experience', value: experience })
  lines.push({ label: 'Where', value: `${formatBoundaryLocation(boundary)} · ${workModeLabel(boundary)}` })
  lines.push({
    label: 'Requirements',
    value: `${core.length} core · ${supporting.length} supporting · ${preferred.length} preferred`,
  })
  if (brief.companies.exclude.length) lines.push({ label: 'Not from', value: `Current employees of ${brief.companies.exclude.join(', ')}` })
  return lines
}
