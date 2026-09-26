// Candidate Discovery — pure, local-only view model. Zips the backend's
// index-aligned `candidates` / `explanations` / `evidence` arrays into one
// shape the UI binds to directly. Every field here traces back to something
// the backend actually returned; nothing is scored, classified, or labeled
// again on the client — that used to produce a second, disagreeing
// evidence system (computeMatchScore/classifyMatchScore) alongside the
// backend's own ranking. There is now exactly one evidence model, and the
// frontend only formats it.

import type { CandidateEvidenceRaw, MatchExplanationRaw, RequirementJudgmentRaw, SearchResponse } from '../types'

export type MatchedSignal = { signalText: string; matchedTerm: string; source: string }

export type RelevanceTier = 'direct' | 'adjacent' | 'tangential' | 'unclear'

export type PastRole = {
  title: string
  company: string
  industries: string[]
  function: string | null
  seniority: string | null
}

export type EducationEntry = {
  institution: string | null
  degree: string | null
  fieldOfStudy: string | null
  /** "2018" or "2014–2018", exactly the years the source gave; null when none. */
  years: string | null
}

export type CareerItem = {
  title: string
  company: string
  start: string | null
  end: string | null
  current: boolean
  duration: string | null
  description: string | null
}

// The requirement ledger: one row per confirmed requirement, with the proof
// beside it. Built only from judgments the backend has already verified.
export type LedgerVerdict = 'met' | 'partly' | 'not_evidenced'
export type LedgerRow = {
  tier: 'core' | 'supporting' | 'differentiator'
  requirement: string
  verdict: LedgerVerdict
  quote: string | null
  /** Recruiter wording for where the quote came from, e.g. "role description · Engineer at Acme". */
  sourceLabel: string | null
  /** True for the years requirement: computed from role dates, not quoted from the profile. */
  derived: boolean
  /** Short verified phrase inside the quote (the judge's `term`), when it gave one. */
  term: string | null
  /** True when the proof is in described work (a role description or project), not just a listed skill or title. */
  described: boolean
}
export type LedgerGroup = {
  tier: 'core' | 'supporting' | 'differentiator'
  label: string
  total: number
  evidenced: number
  rows: LedgerRow[]
}

export type CandidateLifecycleState = 'surfaced' | 'building_context' | 'review_ready'

export type DiscoveryCandidate = {
  id: string
  name: string
  title: string
  company: string
  location: string
  profileUrl: string | null

  // System-driven processing state (Progressive Candidate Workspace) —
  // completely separate from the recruiter's own shortlist/reject decision
  // (see CandidateReviewScreen.tsx's `decisions` state). Defaults to
  // 'review_ready' for a search response that predates this field (a
  // finished, non-progressive search has nothing further to process).
  lifecycleState: CandidateLifecycleState

  relevanceTier: RelevanceTier
  whyThisCandidate: string
  strongEvidence: string[]
  potentialConcerns: string[]
  whatWeDontKnow: string[]
  matchedSignals: MatchedSignal[]
  seniorityAlignment: boolean | null
  providerFit: string | null
  convergence: boolean

  currentIndustries: string[]
  currentFunction: string | null
  currentSeniority: string | null
  pastRoles: PastRole[]
  education: EducationEntry[]
  contactEmail: string | null
  contactPhone: string | null
  hasBusinessEmail: boolean | null
  updatedAt: string | null

  // Candidate record (Release 2)
  headline: string
  photoUrl: string | null
  /** True only when the profile itself says so; null (unknown) and false are both simply not shown. */
  openToWork: boolean | null
  career: CareerItem[]
  skills: string[]
  certifications: string[]
  aboutExcerpt: string | null
  reviewFirst: string[]
  ledger: LedgerGroup[]
  experienceLine: string | null
  levelLine: string | null
  levelFit: 'aligned' | 'above' | 'below' | 'unclear' | null
  /** false only when role dates show fewer years than the brief asks; null when it cannot be checked. */
  experienceFloor: boolean | null

  /** Internal sort key only — never rendered as a score/percentage. */
  sortScore: number
}

const RELEVANCE_LABEL: Record<RelevanceTier, string> = {
  direct: 'Direct title match',
  adjacent: 'Adjacent title match',
  tangential: 'Tangential title match',
  unclear: 'Unclear title relevance',
}

export function relevanceLabel(tier: RelevanceTier): string {
  return RELEVANCE_LABEL[tier] ?? 'Unclear title relevance'
}

/** Precise contact wording — distinguishes a verified negative fact (the
 * provider explicitly returned has_business_email: false) from genuinely
 * unknown (the field wasn't returned at all), rather than the previous
 * one-size-fits-all "No contact information returned." */
export function emailStatusLine(candidate: DiscoveryCandidate): string {
  if (candidate.contactEmail) return candidate.contactEmail
  if (candidate.hasBusinessEmail === false) return 'No verified business email on file'
  return 'Not returned for this candidate'
}

export function phoneStatusLine(candidate: DiscoveryCandidate): string {
  if (candidate.contactPhone) return candidate.contactPhone
  return 'Not returned for this candidate'
}

function readString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function readStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function emptyExplanation(): MatchExplanationRaw {
  return {
    relevance_tier: 'unclear',
    why_this_candidate: '',
    strong_evidence: [],
    potential_concerns: [],
    what_we_dont_know: [],
    matched_signals: [],
    seniority_alignment: null,
    provider_fit: null,
    convergence: false,
    matched_queries: [],
    final_score: null,
  }
}

function emptyEvidence(): CandidateEvidenceRaw {
  return {
    current_company: '',
    current_industries: [],
    current_function: null,
    current_seniority: null,
    current_headcount: null,
    current_company_type: null,
    past_roles: [],
    education: [],
    contact: { email: null, phone: null, has_business_email: null },
    updated_at: null,
    uncertainty: [],
  }
}

const TIER_LABEL: Record<'core' | 'supporting' | 'differentiator', string> = {
  core: 'Core requirements',
  supporting: 'Supporting',
  differentiator: 'Preferred',
}

/** Where a quote came from, in recruiter language. Never names a data provider. */
export function sourceLabel(judgment: RequirementJudgmentRaw): string | null {
  const source = (judgment.source ?? '').toLowerCase()
  const detail = judgment.evidence_detail?.trim()
  if (!source) return null
  if (source === 'career dates') return 'derived from role dates'
  if (source.endsWith('employment description')) return detail ? `role description · ${detail}` : 'role description'
  if (source.endsWith('project')) return detail ? `project · ${detail}` : 'project'
  if (source.endsWith('certification')) return detail ? `certification · ${detail}` : 'certification'
  if (source.endsWith('skill')) return 'listed skill'
  if (source === 'headline') return 'profile headline'
  if (source === 'current title') return 'current title'
  if (source.startsWith('past role')) return 'earlier job title'
  return source.replace(/^harvest:\s*/, '')
}

export function buildLedger(judgments: RequirementJudgmentRaw[] | null | undefined): LedgerGroup[] {
  if (!judgments || judgments.length === 0) return []
  const groups: LedgerGroup[] = []
  for (const tier of ['core', 'supporting', 'differentiator'] as const) {
    const rows: LedgerRow[] = judgments
      .filter((judgment) => judgment.tier === tier)
      .map((judgment) => ({
        tier,
        requirement: judgment.signal_text,
        verdict: judgment.verdict,
        quote: judgment.verdict === 'not_evidenced' ? null : readString(judgment.quote),
        sourceLabel: judgment.verdict === 'not_evidenced' ? null : sourceLabel(judgment),
        derived: (judgment.source ?? '').toLowerCase() === 'career dates',
        term: readString(judgment.term),
        described:
          judgment.verdict === 'met' && (judgment.source ?? '').toLowerCase() !== 'career dates' && judgment.strength === 'strong',
      }))
    if (rows.length) {
      groups.push({ tier, label: TIER_LABEL[tier], total: rows.length, evidenced: rows.filter((row) => row.verdict === 'met').length, rows })
    }
  }
  return groups
}

function educationYears(start: unknown, end: unknown): string | null {
  const from = readString(start)
  const to = readString(end)
  if (from && to) return from === to ? to : `${from}–${to}`
  return to ?? from
}

export function initialsOf(name: string): string {
  const parts = name.split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  return ((parts[0][0] ?? '') + (parts.length > 1 ? (parts[parts.length - 1][0] ?? '') : '')).toUpperCase()
}

const ABOUT_EXCERPT_CHARS = 320

function aboutExcerpt(about: unknown): string | null {
  const text = readString(about)
  if (!text) return null
  const flat = text.replace(/\s+/g, ' ').trim()
  return flat.length > ABOUT_EXCERPT_CHARS ? `${flat.slice(0, ABOUT_EXCERPT_CHARS).trimEnd()}…` : flat
}

export function buildDiscoveryCandidates(response: SearchResponse): DiscoveryCandidate[] {
  const candidates = response.candidates ?? []
  const explanations = response.explanations ?? []
  const evidenceList = response.evidence ?? []
  const candidateStates = response.candidate_states ?? {}

  return candidates.map((candidate, index) => {
    const explanation = explanations[index] ?? emptyExplanation()
    const evidence = evidenceList[index] ?? emptyEvidence()
    // The provider's own stable identity — the ONLY safe key for
    // lifecycle/decisions/notes across a progressively-updating response.
    // profile_url/name-index are no longer used as identity (they aren't
    // guaranteed stable across polls that reorder the list — see the
    // Progressive Candidate Workspace's single post-Harvest rerank).
    const id = readString(candidate.candidate_id) ?? `${candidate.name ?? 'candidate'}-${index}`

    return {
      id,
      // Defaults to review_ready: a search response with no candidate_states
      // at all predates this field (nothing left to process).
      lifecycleState: candidateStates[id] ?? 'review_ready',
      name: candidate.name?.trim() || 'Unnamed candidate',
      title: candidate.title?.trim() || 'Title not available',
      company: candidate.company?.trim() || 'Not specified',
      location: candidate.location?.trim() || 'Not specified',
      profileUrl: readString(candidate.profile_url),

      relevanceTier: explanation.relevance_tier ?? 'unclear',
      whyThisCandidate: explanation.why_this_candidate ?? '',
      strongEvidence: readStringArray(explanation.strong_evidence),
      potentialConcerns: readStringArray(explanation.potential_concerns),
      // Self-reported claims (e.g. a candidate's own "11+ years" in their
      // profile summary) are appended here, not into strongEvidence — this
      // is the existing "What We Don't Know" section, which already reads
      // as "unverified/uncertain" to a recruiter, so a self-reported note
      // fits it without a new UI section.
      whatWeDontKnow: [...readStringArray(explanation.what_we_dont_know), ...readStringArray(explanation.self_reported_notes)],
      matchedSignals: (explanation.matched_signals ?? []).map((s) => ({
        signalText: s.signal_text,
        matchedTerm: s.matched_term,
        source: s.source ?? '',
      })),
      seniorityAlignment: explanation.seniority_alignment ?? null,
      providerFit: readString(explanation.provider_fit),
      convergence: Boolean(explanation.convergence),

      currentIndustries: readStringArray(evidence.current_industries),
      currentFunction: readString(evidence.current_function),
      currentSeniority: readString(evidence.current_seniority),
      pastRoles: (evidence.past_roles ?? []).map((r) => ({
        title: r.title ?? '',
        company: r.company ?? '',
        industries: readStringArray(r.industries),
        function: readString(r.function),
        seniority: readString(r.seniority),
      })),
      education: (evidence.education ?? [])
        .map((e) => ({
          institution: readString(e.institution),
          degree: readString(e.degree),
          fieldOfStudy: readString(e.field_of_study),
          years: educationYears(e.start_date, e.end_date),
        }))
        // Most recent first; entries with no end year keep their order after the dated ones.
        .map((entry, order) => ({ entry, order, end: Number((entry.years ?? '').split('–').pop()) || 0 }))
        .sort((a, b) => b.end - a.end || a.order - b.order)
        .map(({ entry }) => entry),
      contactEmail: readString(evidence.contact?.email),
      contactPhone: readString(evidence.contact?.phone),
      hasBusinessEmail: typeof evidence.contact?.has_business_email === 'boolean' ? evidence.contact.has_business_email : null,
      updatedAt: readString(evidence.updated_at),

      headline: readString(evidence.headline) ?? '',
      photoUrl: readString(evidence.photo_url),
      openToWork: typeof evidence.open_to_work === 'boolean' ? evidence.open_to_work : null,
      career: (evidence.career ?? []).map((entry) => ({
        title: entry.title ?? '',
        company: entry.company ?? '',
        start: readString(entry.start),
        end: readString(entry.end),
        current: Boolean(entry.current),
        duration: readString(entry.duration),
        description: readString(entry.description),
      })),
      skills: readStringArray(evidence.harvest_skills),
      certifications: readStringArray(evidence.harvest_certifications),
      aboutExcerpt: aboutExcerpt(evidence.harvest_about),
      reviewFirst: readStringArray(explanation.review_first),
      ledger: buildLedger(evidence.requirement_judgments),
      experienceLine: readString(evidence.role_alignment?.experience_floor_basis),
      levelLine: readString(evidence.role_alignment?.level_basis),
      levelFit: evidence.role_alignment?.level_fit ?? explanation.level_fit ?? null,
      experienceFloor:
        typeof evidence.role_alignment?.experience_floor === 'boolean'
          ? evidence.role_alignment.experience_floor
          : typeof explanation.experience_floor === 'boolean'
            ? explanation.experience_floor
            : null,

      sortScore: typeof explanation.final_score === 'number' ? explanation.final_score : 0,
    }
  })
}

