// Part of the Recruiter Intelligence Layer.
//
// When a JD mentions two or more primary programming languages, that is not
// automatically ambiguous. A recruiter reading the same JD would usually be
// able to tell whether it describes:
//   - a genuine polyglot requirement (all languages truly required together)
//   - multiple acceptable backgrounds (any one of them is fine)
//   - a primary language plus supporting/nice-to-have technologies
// Only when none of those can be inferred with reasonable confidence should
// the recruiter be asked. This module is the single source of truth for that
// judgment call — both the clarification engine (deciding whether to ask)
// and the Search Brief builder (deciding how to auto-resolve when not
// asking) call into it, so the two can never disagree.

import { findPrimaryTechMentionIndex } from '../screens/localJdExtraction'
import type { LanguageSignal } from './types'

export type { LanguageSignal }

export type LanguageClassification = {
  signal: LanguageSignal
  /** Only set when `signal` is 'primary-with-support' — the dominant language. */
  dominant: string | null
}

const POLYGLOT_HINTS = /\b(polyglot|full[\s-]?stack across|proficient in multiple languages|comfortable working across)\b/i
const SUPPORT_HINTS = /\b(nice to have|a plus|bonus|exposure to|familiarity with|willingness to learn|preferred but not required)\b/gi
const PRIMARY_HINTS = /\b(primarily|mainly|main language|core language|primary language|main stack)\b/gi
const MAX_HINT_DISTANCE = 70
const OR_SPAN_LIMIT = 120

type CandidatePosition = { label: string; index: number }

/** Assigns a hint match to whichever candidate mention it's physically
 * closest to — not every candidate within a fixed radius, which would let
 * one hint get double-counted for two nearby candidates. */
function nearestCandidateLabels(positions: CandidatePosition[], hintPattern: RegExp, text: string): Set<string> {
  const labels = new Set<string>()
  for (const hintMatch of text.matchAll(hintPattern)) {
    let nearest: CandidatePosition | null = null
    let nearestDistance = Infinity
    for (const position of positions) {
      const distance = Math.abs(position.index - (hintMatch.index ?? 0))
      if (distance < nearestDistance) {
        nearest = position
        nearestDistance = distance
      }
    }
    if (nearest && nearestDistance <= MAX_HINT_DISTANCE) {
      labels.add(nearest.label)
    }
  }
  return labels
}

/** Classifies a JD's intent for a set of 2+ detected primary-language
 * candidates. Callers should only invoke this once genuine ambiguity in the
 * raw candidate list has already been established (candidates.length > 1). */
export function classifyLanguageSignal(text: string, candidates: string[]): LanguageClassification {
  if (POLYGLOT_HINTS.test(text)) {
    return { signal: 'polyglot', dominant: null }
  }

  const positions = candidates
    .map((label) => ({ label, index: findPrimaryTechMentionIndex(text, label) }))
    .filter((entry) => entry.index >= 0)
    .sort((a, b) => a.index - b.index)

  if (positions.length < 2) {
    return { signal: 'ambiguous', dominant: null }
  }

  // "Python, Java, or Go" — an "or" joining the candidates in one short span
  // signals interchangeable backgrounds, not a combined requirement.
  const span = text.slice(positions[0].index, positions[positions.length - 1].index + 20)
  if (/\bor\b/i.test(span) && span.length < OR_SPAN_LIMIT) {
    return { signal: 'acceptable-backgrounds', dominant: null }
  }

  const primarySignaled = nearestCandidateLabels(positions, PRIMARY_HINTS, text)
  const supportSignaled = nearestCandidateLabels(positions, SUPPORT_HINTS, text)

  if (primarySignaled.size === 1) {
    return { signal: 'primary-with-support', dominant: [...primarySignaled][0] }
  }

  if (primarySignaled.size === 0 && supportSignaled.size === positions.length - 1) {
    const dominant = positions.find((entry) => !supportSignaled.has(entry.label))
    if (dominant) {
      return { signal: 'primary-with-support', dominant: dominant.label }
    }
  }

  return { signal: 'ambiguous', dominant: null }
}
