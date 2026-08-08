// Part of the Recruiter Intelligence Layer.
//
// Title expansion by recruiter reasoning, not a static synonym table: strip
// the seniority word to find the role's core, swap the Engineer/Developer
// convention, walk the IC ladder one step down for past titles, and ask
// recruiter knowledge for any known title equivalence group. This
// intentionally stays conservative — it only ever proposes titles derived
// from the recruiter's own words or from recruiter knowledge, never
// invents an unrelated title.

import { IC_LADDER, stepDownIcLadder } from './knowledge/careerProgression'
import { equivalentTitlesFor } from './knowledge/semanticTitles'

/** The seniority word actually present in the title text, if any — checked
 * against the IC ladder rather than trusting a separately-resolved
 * seniority value, which can disagree with the title itself (e.g. the
 * backend's own JD parse guessing a different level than the title states). */
function seniorityWordIn(title: string): string | null {
  return IC_LADDER.find((level) => new RegExp(`\\b${level}\\b`, 'i').test(title)) ?? null
}

function stripSeniority(title: string, seniority: string): string {
  const result = seniority.trim() ? title.replace(new RegExp(`\\b${seniority.trim()}\\b`, 'i'), '') : title
  return result.replace(/\s{2,}/g, ' ').trim()
}

function swapEngineerDeveloper(title: string): string | null {
  if (/engineer/i.test(title)) {
    return title.replace(/engineer/i, (match) => (match[0] === 'E' ? 'Developer' : 'developer'))
  }
  if (/developer/i.test(title)) {
    return title.replace(/developer/i, (match) => (match[0] === 'D' ? 'Engineer' : 'engineer'))
  }
  return null
}

export type TitleExpansion = {
  equivalentTitles: string[]
  pastTitles: string[]
}

export function expandTitle(primaryTitle: string, seniority: string): TitleExpansion {
  const trimmed = primaryTitle.trim()
  if (!trimmed) {
    return { equivalentTitles: [], pastTitles: [] }
  }

  const titleSeniority = seniorityWordIn(trimmed) ?? seniority
  const core = stripSeniority(trimmed, titleSeniority) || trimmed
  const equivalents = new Set<string>()

  const swapped = swapEngineerDeveloper(trimmed)
  if (swapped && swapped.toLowerCase() !== trimmed.toLowerCase()) {
    equivalents.add(swapped)
  }
  if (core.toLowerCase() !== trimmed.toLowerCase()) {
    equivalents.add(core)
  }
  // Recruiter knowledge: known equivalence groups (e.g. "Applied AI
  // Engineer" ≈ "LLM Engineer" ≈ "Generative AI Engineer"), checked against
  // both the full title and the seniority-stripped core.
  for (const known of [...equivalentTitlesFor(trimmed), ...equivalentTitlesFor(core)]) {
    equivalents.add(known)
  }
  equivalents.delete(trimmed)

  const pastTitles = new Set<string>()
  const stepDown = stepDownIcLadder(titleSeniority)
  if (stepDown) {
    pastTitles.add(`${stepDown} ${core}`.trim())
  } else if (!titleSeniority.trim() && core) {
    // No recognized seniority word in the title — the bare role itself is
    // still a reasonable signal for an earlier career stage.
    pastTitles.add(core)
  }
  pastTitles.delete(trimmed)

  return { equivalentTitles: Array.from(equivalents), pastTitles: Array.from(pastTitles) }
}
