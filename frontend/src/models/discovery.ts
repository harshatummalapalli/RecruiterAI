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
      bio: readString(raw.summary),
      explanation,
    }
  })
}

export type SortKey = 'match' | 'experience' | 'recent' | 'name'

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
      sorted.sort((a, b) => (b.candidate.matchScore ?? -Infinity) - (a.candidate.matchScore ?? -Infinity))
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

export function formatMatchScore(score: number | null): string {
  return score === null ? 'Not scored' : score.toFixed(1)
}

export function formatExperienceYears(years: number | null): string {
  return years === null ? 'Not specified' : `${years} yr${years === 1 ? '' : 's'}`
}
