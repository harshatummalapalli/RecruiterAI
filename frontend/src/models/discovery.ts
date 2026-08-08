// Candidate Discovery — pure, local-only view model. Zips the backend's
// parallel `candidates` / `explanations` arrays into one shape the UI binds
// to directly, and formats the handful of fields recruiters actually need
// for a first decision. No provider metadata, no diagnostics.

import type { SearchResponse } from '../types'

export type MatchExplanation = {
  finalScore: number | null
  matchedRequiredSkills: string[]
  missingRequiredSkills: string[]
  matchedPreferredSkills: string[]
  missingPreferredSkills: string[]
  matchedLocation: string | null
  matchedExperience: string | null
  missingExperience: string | null
  potentialRisks: string[]
  summary: string | null
  titleMatch: boolean | null
  locationMatch: boolean | null
  companyMatch: boolean | null
  experienceMatch: boolean | null
}

export type DiscoveryCandidate = {
  id: string
  name: string
  title: string
  company: string
  location: string
  experienceYears: number | null
  matchScore: number | null
  /** The candidate's professional network (LinkedIn) profile URL, when the
   * provider returned one. Recruiter-facing action only — never surfaced
   * alongside any provider name. */
  profileUrl: string | null
  bio: string | null
  explanation: MatchExplanation
}

function readString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function readNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function readStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function readBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null
}

export function buildDiscoveryCandidates(response: SearchResponse): DiscoveryCandidate[] {
  const candidates = response.candidates ?? []
  const explanations = response.explanations ?? []

  return candidates.map((candidate, index) => {
    const raw = (candidate.raw_data ?? {}) as Record<string, unknown>
    const explanationRaw = (explanations[index] ?? {}) as Record<string, unknown>

    const explanation: MatchExplanation = {
      finalScore: readNumber(explanationRaw.final_score),
      matchedRequiredSkills: readStringArray(explanationRaw.matched_required_skills),
      missingRequiredSkills: readStringArray(explanationRaw.missing_required_skills),
      matchedPreferredSkills: readStringArray(explanationRaw.matched_preferred_skills),
      missingPreferredSkills: readStringArray(explanationRaw.missing_preferred_skills),
      matchedLocation: readString(explanationRaw.matched_location),
      matchedExperience: readString(explanationRaw.matched_experience),
      missingExperience: readString(explanationRaw.missing_experience),
      potentialRisks: readStringArray(explanationRaw.potential_risks),
      summary: readString(explanationRaw.summary),
      titleMatch: readBoolean(explanationRaw.title_match),
      locationMatch: readBoolean(explanationRaw.location_match),
      companyMatch: readBoolean(explanationRaw.company_match),
      experienceMatch: readBoolean(explanationRaw.experience_match),
    }

    return {
      id: readString(candidate.profile_url) ?? `${candidate.name ?? 'candidate'}-${index}`,
      name: candidate.name?.trim() || 'Unnamed candidate',
      title: candidate.title?.trim() || 'Title not available',
      company: candidate.company?.trim() || 'Not specified',
      location: candidate.location?.trim() || 'Not specified',
      experienceYears: readNumber(raw.years_experience),
      matchScore: readNumber(candidate.final_score) ?? readNumber(candidate.provider_score),
      profileUrl: readString(candidate.profile_url),
      bio: readString(raw.summary),
      explanation,
    }
  })
}

export type SortKey = 'match' | 'experience' | 'recent' | 'name'

// Match classification — the single source of truth for how "good" a match
// is, used for BOTH sorting and the recruiter-facing badge everywhere it
// appears (list row, profile header, comparison). Deterministic, from real
// evidence only: required/preferred skill coverage, title match, experience
// match, location match. Never a raw provider score — that's what produced
// the old "Match = 4.0" next to "Weak Match" contradiction, since the list
// and the profile used to compute two different, disagreeing signals.
export type MatchVerdict = 'Excellent Match' | 'Strong Match' | 'Good Match' | 'Partial Match' | 'Weak Match' | 'Poor Match'

const REQUIRED_SKILLS_WEIGHT = 0.4
const PREFERRED_SKILLS_WEIGHT = 0.15
const TITLE_WEIGHT = 0.15
const EXPERIENCE_WEIGHT = 0.15
const LOCATION_WEIGHT = 0.15

/** 0–1 composite. A boolean signal that's genuinely unknown (null) is
 * excluded and the remaining weights renormalized, rather than guessed at —
 * an unknown location match should never silently count as a failure. */
export function computeMatchScore(candidate: DiscoveryCandidate): number {
  const e = candidate.explanation
  const requiredTotal = e.matchedRequiredSkills.length + e.missingRequiredSkills.length
  const preferredTotal = e.matchedPreferredSkills.length + e.missingPreferredSkills.length

  const components: Array<{ weight: number; score: number }> = [
    { weight: REQUIRED_SKILLS_WEIGHT, score: requiredTotal > 0 ? e.matchedRequiredSkills.length / requiredTotal : 1 },
    { weight: PREFERRED_SKILLS_WEIGHT, score: preferredTotal > 0 ? e.matchedPreferredSkills.length / preferredTotal : 1 },
  ]
  if (e.titleMatch !== null) components.push({ weight: TITLE_WEIGHT, score: e.titleMatch ? 1 : 0 })
  if (e.experienceMatch !== null) components.push({ weight: EXPERIENCE_WEIGHT, score: e.experienceMatch ? 1 : 0 })
  if (e.locationMatch !== null) components.push({ weight: LOCATION_WEIGHT, score: e.locationMatch ? 1 : 0 })

  const totalWeight = components.reduce((sum, component) => sum + component.weight, 0)
  if (totalWeight === 0) {
    return 0
  }
  return components.reduce((sum, component) => sum + component.weight * component.score, 0) / totalWeight
}

export function classifyMatchScore(score: number): MatchVerdict {
  if (score >= 0.92) return 'Excellent Match'
  if (score >= 0.78) return 'Strong Match'
  if (score >= 0.6) return 'Good Match'
  if (score >= 0.4) return 'Partial Match'
  if (score >= 0.2) return 'Weak Match'
  return 'Poor Match'
}

export function matchVerdictFor(candidate: DiscoveryCandidate): MatchVerdict {
  return classifyMatchScore(computeMatchScore(candidate))
}

export function sortDiscoveryCandidates(
  candidates: DiscoveryCandidate[],
  sortKey: SortKey,
  recencyById: Record<string, number>,
): DiscoveryCandidate[] {
  const withRecency = candidates.map((candidate, index) => ({
    candidate,
    recency: recencyById[candidate.id] ?? candidates.length - index,
  }))

  const sorted = [...withRecency]
  switch (sortKey) {
    case 'match':
      sorted.sort((a, b) => computeMatchScore(b.candidate) - computeMatchScore(a.candidate))
      break
    case 'experience':
      sorted.sort((a, b) => (b.candidate.experienceYears ?? -Infinity) - (a.candidate.experienceYears ?? -Infinity))
      break
    case 'recent':
      sorted.sort((a, b) => b.recency - a.recency)
      break
    case 'name':
      sorted.sort((a, b) => a.candidate.name.localeCompare(b.candidate.name))
      break
  }
  return sorted.map((entry) => entry.candidate)
}

export function formatExperienceYears(years: number | null): string {
  return years === null ? 'Not specified' : `${years} yr${years === 1 ? '' : 's'}`
}
