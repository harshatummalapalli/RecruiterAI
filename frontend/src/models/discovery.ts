// Candidate Discovery — pure, local-only view model. Zips the backend's
// index-aligned `candidates` / `explanations` / `evidence` arrays into one
// shape the UI binds to directly. Every field here traces back to something
// the backend actually returned; nothing is scored, classified, or labeled
// again on the client — that used to produce a second, disagreeing
// evidence system (computeMatchScore/classifyMatchScore) alongside the
// backend's own ranking. There is now exactly one evidence model, and the
// frontend only formats it.

import type { CandidateEvidenceRaw, MatchExplanationRaw, SearchResponse } from '../types'

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
}

export type DiscoveryCandidate = {
  id: string
  name: string
  title: string
  company: string
  location: string
  profileUrl: string | null

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

export function buildDiscoveryCandidates(response: SearchResponse): DiscoveryCandidate[] {
  const candidates = response.candidates ?? []
  const explanations = response.explanations ?? []
  const evidenceList = response.evidence ?? []

  return candidates.map((candidate, index) => {
    const explanation = explanations[index] ?? emptyExplanation()
    const evidence = evidenceList[index] ?? emptyEvidence()

    return {
      id: readString(candidate.profile_url) ?? `${candidate.name ?? 'candidate'}-${index}`,
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
      education: (evidence.education ?? []).map((e) => ({
        institution: readString(e.institution),
        degree: readString(e.degree),
        fieldOfStudy: readString(e.field_of_study),
      })),
      contactEmail: readString(evidence.contact?.email),
      contactPhone: readString(evidence.contact?.phone),
      hasBusinessEmail: typeof evidence.contact?.has_business_email === 'boolean' ? evidence.contact.has_business_email : null,
      updatedAt: readString(evidence.updated_at),

      sortScore: typeof explanation.final_score === 'number' ? explanation.final_score : 0,
    }
  })
}

export type SortKey = 'relevance' | 'updated' | 'name'

export function sortDiscoveryCandidates(candidates: DiscoveryCandidate[], sortKey: SortKey): DiscoveryCandidate[] {
  const sorted = [...candidates]
  switch (sortKey) {
    case 'relevance':
      // The backend already returns candidates in relevance order; sorting
      // here re-applies the same score so re-sorting after a client-side
      // filter stays consistent, without recomputing anything.
      sorted.sort((a, b) => b.sortScore - a.sortScore)
      break
    case 'updated':
      // Candidates with no updated_at (the common case today — see the
      // report) sort to the end rather than being treated as "oldest."
      sorted.sort((a, b) => {
        if (a.updatedAt && b.updatedAt) return b.updatedAt.localeCompare(a.updatedAt)
        if (a.updatedAt) return -1
        if (b.updatedAt) return 1
        return 0
      })
      break
    case 'name':
      sorted.sort((a, b) => a.name.localeCompare(b.name))
      break
  }
  return sorted
}
