// Part of the Recruiter Intelligence Layer.
//
// Title expansion by recruiter reasoning, not a static synonym table: strip
// the seniority word to find the role's core, swap the Engineer/Developer
// convention, and walk the seniority ladder one step down for past titles.
// This intentionally stays conservative — it only ever proposes titles
// derived from the recruiter's own words, never invents an unrelated title.

const SENIORITY_LADDER = ['Junior', 'Mid-level', 'Senior', 'Staff', 'Principal']

function stripSeniority(title: string): string {
  let result = title
  for (const level of SENIORITY_LADDER) {
    result = result.replace(new RegExp(`\\b${level}\\b`, 'i'), '')
  }
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

  const core = stripSeniority(trimmed) || trimmed
  const equivalents = new Set<string>()

  const swapped = swapEngineerDeveloper(trimmed)
  if (swapped && swapped.toLowerCase() !== trimmed.toLowerCase()) {
    equivalents.add(swapped)
  }
  if (core.toLowerCase() !== trimmed.toLowerCase()) {
    equivalents.add(core)
  }
  equivalents.delete(trimmed)

  const ladderIndex = SENIORITY_LADDER.findIndex((level) => level.toLowerCase() === seniority.trim().toLowerCase())
  const pastTitles = new Set<string>()
  if (ladderIndex > 0) {
    pastTitles.add(`${SENIORITY_LADDER[ladderIndex - 1]} ${core}`.trim())
  } else if (ladderIndex === -1 && core) {
    // No recognized seniority word in the title — the bare role itself is
    // still a reasonable signal for an earlier career stage.
    pastTitles.add(core)
  }
  pastTitles.delete(trimmed)

  return { equivalentTitles: Array.from(equivalents), pastTitles: Array.from(pastTitles) }
}
