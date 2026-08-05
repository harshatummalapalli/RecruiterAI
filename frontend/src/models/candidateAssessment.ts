// Turns a candidate's MatchExplanation into a recruiter-style assessment —
// a verdict, a narrative, and Strengths/Concerns bullets. Every sentence
// here is assembled from fields the backend actually returned. Nothing is
// invented, scored by a hidden model, or inferred beyond that evidence.

import type { DiscoveryCandidate } from './discovery'

export type Verdict = 'Strong Match' | 'Good Match' | 'Partial Match' | 'Weak Match'

export type CandidateAssessment = {
  verdict: Verdict
  narrative: string
  strengths: string[]
  concerns: string[]
}

function toSentence(clause: string): string {
  const trimmed = clause.trim()
  if (!trimmed) return ''
  const capitalized = trimmed.charAt(0).toUpperCase() + trimmed.slice(1)
  return capitalized.endsWith('.') ? capitalized : `${capitalized}.`
}

// The backend's MatchExplanation.summary is already a semicolon-joined,
// evidence-based sentence (see backend/services/match_explainer.py). We only
// reformat it into readable sentences — we never add claims to it.
function buildNarrative(candidate: DiscoveryCandidate): string {
  const { summary } = candidate.explanation
  if (!summary) {
    return 'Not enough information was returned to assess this candidate.'
  }
  return summary
    .split(';')
    .map((clause) => toSentence(clause))
    .filter(Boolean)
    .join(' ')
}

function buildVerdict(candidate: DiscoveryCandidate): Verdict {
  const { matchedRequiredSkills, missingRequiredSkills, titleMatch, experienceMatch } = candidate.explanation
  const requiredTotal = matchedRequiredSkills.length + missingRequiredSkills.length
  const requiredRatio = requiredTotal > 0 ? matchedRequiredSkills.length / requiredTotal : 0
  const positives = [titleMatch, experienceMatch].filter((value) => value === true).length

  if (requiredTotal > 0 && missingRequiredSkills.length === 0 && experienceMatch !== false) {
    return 'Strong Match'
  }
  if (requiredRatio >= 0.5 || positives >= 1) {
    return 'Good Match'
  }
  if (requiredRatio > 0 || matchedRequiredSkills.length > 0) {
    return 'Partial Match'
  }
  return 'Weak Match'
}

function buildStrengths(candidate: DiscoveryCandidate): string[] {
  const e = candidate.explanation
  const strengths: string[] = []

  if (e.matchedRequiredSkills.length) {
    strengths.push(`Required skills matched: ${e.matchedRequiredSkills.join(', ')}`)
  }
  if (e.matchedPreferredSkills.length) {
    strengths.push(`Preferred skills matched: ${e.matchedPreferredSkills.join(', ')}`)
  }
  if (e.titleMatch) {
    strengths.push('Title matches the target role')
  }
  if (e.experienceMatch && e.matchedExperience) {
    strengths.push(`Experience meets requirement (${e.matchedExperience})`)
  }
  if (e.locationMatch && e.matchedLocation) {
    strengths.push(`Located in ${e.matchedLocation} — matches target geography`)
  }
  if (e.companyMatch) {
    strengths.push('Background includes a preferred company')
  }

  return strengths
}

function buildConcerns(candidate: DiscoveryCandidate): string[] {
  const e = candidate.explanation
  const concerns: string[] = []

  if (e.missingRequiredSkills.length) {
    concerns.push(`Missing required skills: ${e.missingRequiredSkills.join(', ')}`)
  }
  if (e.missingPreferredSkills.length) {
    concerns.push(`Missing preferred skills: ${e.missingPreferredSkills.join(', ')}`)
  }
  if (e.titleMatch === false) {
    concerns.push('Title does not clearly match the target role')
  }
  if (e.locationMatch === false) {
    concerns.push('Location does not align with the target geography')
  }
  if (e.experienceMatch === false && e.missingExperience) {
    concerns.push(e.missingExperience)
  }
  for (const risk of e.potentialRisks) {
    if (!concerns.includes(risk)) {
      concerns.push(risk)
    }
  }

  return concerns
}

export function buildAssessment(candidate: DiscoveryCandidate): CandidateAssessment {
  return {
    verdict: buildVerdict(candidate),
    narrative: buildNarrative(candidate),
    strengths: buildStrengths(candidate),
    concerns: buildConcerns(candidate),
  }
}
