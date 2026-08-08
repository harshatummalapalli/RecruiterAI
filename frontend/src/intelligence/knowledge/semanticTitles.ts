// Recruiter Knowledge Engine — Semantic Title Knowledge.
//
// Groups of titles recruiters treat as effectively interchangeable, even
// though the strings don't match. This is what lets title reasoning ask
// "does recruiter knowledge say this title has known equivalents?" instead
// of only ever deriving equivalents mechanically (Engineer ↔ Developer,
// strip the seniority word).

export const TITLE_EQUIVALENCE_GROUPS: string[][] = [
  ['Applied AI Engineer', 'LLM Engineer', 'Generative AI Engineer'],
  ['Site Reliability Engineer', 'SRE', 'Platform Reliability Engineer'],
  ['Backend Engineer', 'Backend Developer', 'Server-side Engineer'],
  ['Frontend Engineer', 'Frontend Developer', 'UI Engineer'],
  ['Full Stack Engineer', 'Full Stack Developer', 'Generalist Engineer'],
  ['ML Engineer', 'Machine Learning Engineer'],
  ['Data Engineer', 'Data Pipeline Engineer'],
  ['DevOps Engineer', 'Infrastructure Engineer', 'Release Engineer'],
  ['QA Engineer', 'SDET', 'Test Engineer'],
  ['Engineering Manager', 'Team Lead, Engineering'],
]

function normalize(value: string): string {
  return value.trim().toLowerCase()
}

/** Every other title in the same equivalence group as `title`, if any. */
export function equivalentTitlesFor(title: string): string[] {
  const target = normalize(title)
  const group = TITLE_EQUIVALENCE_GROUPS.find((entry) => entry.some((candidate) => normalize(candidate) === target))
  if (!group) {
    return []
  }
  return group.filter((candidate) => normalize(candidate) !== target)
}
