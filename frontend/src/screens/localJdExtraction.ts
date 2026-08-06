// Lightweight, heuristic, fully local job-description scan.
// No AI, no network calls — this exists only to give the recruiter
// instant visual feedback while typing, before they ever click Parse.

export type LocationEntry = {
  city: string
  state: string
  country: string
  zip: string
}

export type LocalExtraction = {
  roleTitle: string | null
  locations: LocationEntry[]
  workModes: Array<'remote' | 'hybrid' | 'onsite'>
  experience: {
    minimumYears: number | null
    maximumYears: number | null
  }
  requiredSkills: string[]
  preferredSkills: string[]
  /** Root technology names (e.g. "Python", ".NET") mentioned often enough to be
   * candidates for a recruiter-chosen "primary technology" — only non-empty
   * when 2+ distinct major technologies are mentioned, i.e. genuinely ambiguous. */
  primaryTechCandidates: string[]
  employmentTypes: string[]
  seniority: string | null
}

const SENIORITY_LEVELS = ['Principal', 'Staff', 'Senior', 'Lead', 'Junior', 'Entry-level', 'Mid-level']

const KNOWN_SKILLS = [
  'Python', 'Java', 'JavaScript', 'TypeScript', 'Go', 'Golang', 'Rust', 'C\\+\\+', 'C#', 'Ruby', 'PHP', 'Swift', 'Kotlin',
  'React', 'Angular', 'Vue', 'Node\\.js', 'Next\\.js', 'Django', 'Flask', 'FastAPI', 'Spring',
  'AWS', 'GCP', 'Azure', 'Kubernetes', 'Docker', 'Terraform',
  'SQL', 'PostgreSQL', 'MySQL', 'MongoDB', 'Redis', 'GraphQL', 'REST',
  'Machine Learning', 'Deep Learning', 'LLM', 'RAG', 'NLP', 'PyTorch', 'TensorFlow', 'LangChain', 'MCP', 'GenAI',
  'CI/CD', 'Microservices', 'Distributed Systems',
]

// A handful of skills recruiters write as one bundled mention (e.g. "C# (.NET / ASP.NET)")
// but that actually represent a family of distinct, individually-searchable skills.
const SKILL_FAMILIES: Record<string, string[]> = {
  'c#': ['C#', '.NET', '.NET Core', 'ASP.NET', 'ASP.NET Core'],
  '.net': ['C#', '.NET', '.NET Core', 'ASP.NET', 'ASP.NET Core'],
}

// The "programming language" cluster — when a JD mentions two or more of
// these, it's genuinely ambiguous which one the recruiter actually wants as
// the primary stack, so we ask rather than dumping all of them into Required.
const PRIMARY_TECH_CANDIDATES: Array<{ label: string; pattern: RegExp }> = [
  { label: 'Python', pattern: /\bpython\b/i },
  { label: 'Java', pattern: /\bjava\b(?!script)/i },
  { label: '.NET', pattern: /\bc#\b|\.net\b/i },
  { label: 'Go', pattern: /\bgo(lang)?\b/i },
  { label: 'Ruby', pattern: /\bruby\b/i },
  { label: 'PHP', pattern: /\bphp\b/i },
  { label: 'JavaScript', pattern: /\bjavascript\b|\btypescript\b/i },
  { label: 'Rust', pattern: /\brust\b/i },
  { label: 'Swift', pattern: /\bswift\b/i },
  { label: 'Kotlin', pattern: /\bkotlin\b/i },
]

/** Maps an individual (possibly already-expanded) skill string back to the
 * primary-tech root label it belongs to, if any. */
export function rootTechLabelForSkill(skill: string): string | null {
  const s = skill.trim().toLowerCase()
  if (s === 'python') return 'Python'
  if (s === 'java') return 'Java'
  if (['c#', '.net', '.net core', 'asp.net', 'asp.net core'].includes(s)) return '.NET'
  if (s === 'go' || s === 'golang') return 'Go'
  if (s === 'ruby') return 'Ruby'
  if (s === 'php') return 'PHP'
  if (s === 'javascript' || s === 'typescript') return 'JavaScript'
  if (s === 'rust') return 'Rust'
  if (s === 'swift') return 'Swift'
  if (s === 'kotlin') return 'Kotlin'
  return null
}

export function detectPrimaryTechCandidates(text: string): string[] {
  const found: string[] = []
  for (const candidate of PRIMARY_TECH_CANDIDATES) {
    if (candidate.pattern.test(text)) {
      found.push(candidate.label)
    }
  }
  return found
}

/** Character offset of a primary-tech candidate's first mention, for callers
 * that need to reason about nearby words (e.g. "primarily", "nice to have"). */
export function findPrimaryTechMentionIndex(text: string, label: string): number {
  const candidate = PRIMARY_TECH_CANDIDATES.find((entry) => entry.label === label)
  if (!candidate) {
    return -1
  }
  const match = candidate.pattern.exec(text)
  return match ? match.index : -1
}

const US_STATE_CODES = new Set([
  'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME',
  'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA',
  'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
])

const COUNTRY_HINTS: Array<[RegExp, string]> = [
  [/\b(united states|usa|u\.s\.)\b/i, 'United States'],
  [/\bunited kingdom|\buk\b/i, 'United Kingdom'],
  [/\bcanada\b/i, 'Canada'],
  [/\bindia\b/i, 'India'],
  [/\bgermany\b/i, 'Germany'],
  [/\baustralia\b/i, 'Australia'],
]

/** Every distinct country explicitly named in the JD (not just the first) —
 * used to detect a genuinely ambiguous, multi-country JD. */
export function detectAllCountryHints(text: string): string[] {
  const found: string[] = []
  for (const [pattern, label] of COUNTRY_HINTS) {
    if (pattern.test(text)) {
      found.push(label)
    }
  }
  return found
}

/** Splits a bundled skill mention ("X (Y / Z)") into its parts; expands known
 * skill families (e.g. "C#") into their full set of individually-searchable skills. */
export function normalizeSkillList(skills: string[]): string[] {
  const expanded = skills.flatMap((raw) => {
    const skill = raw.trim()
    const directFamily = SKILL_FAMILIES[skill.toLowerCase()]
    if (directFamily) {
      return directFamily
    }

    const bundleMatch = skill.match(/^(.+?)\s*\(([^)]+)\)$/)
    if (bundleMatch) {
      const [, base, inner] = bundleMatch
      const baseFamily = SKILL_FAMILIES[base.trim().toLowerCase()]
      if (baseFamily) {
        return baseFamily
      }
      const innerParts = inner.split('/').map((part) => part.trim()).filter(Boolean)
      return [base.trim(), ...innerParts]
    }

    return [skill]
  })

  return Array.from(new Set(expanded.filter(Boolean)))
}

/** Removes any skill belonging to an ambiguous primary-tech family — those are
 * held back for the recruiter's explicit Primary Technology choice instead of
 * being dumped straight into Required/Preferred. */
function withholdAmbiguousTech(skills: string[], ambiguousCandidates: string[]): string[] {
  if (ambiguousCandidates.length < 2) {
    return skills
  }
  return skills.filter((skill) => !ambiguousCandidates.includes(rootTechLabelForSkill(skill) ?? ''))
}

function findSkills(text: string): string[] {
  const found: string[] = []
  for (const pattern of KNOWN_SKILLS) {
    const regex = new RegExp(`\\b${pattern}\\b`, 'i')
    const match = text.match(regex)
    if (match) {
      found.push(match[0])
    }
  }
  return normalizeSkillList(found).slice(0, 12)
}

function extractRoleTitle(text: string): string | null {
  const firstLine = text.split('\n').map((line) => line.trim()).find((line) => line.length > 0)
  if (!firstLine) {
    return null
  }

  const title = firstLine.split(/[–—]| - /)[0].trim()
  if (!title || title.length > 70) {
    return null
  }

  return title
}

function extractWorkModes(text: string): LocalExtraction['workModes'] {
  const modes: LocalExtraction['workModes'] = []
  if (/\bremote\b/i.test(text)) modes.push('remote')
  if (/\bhybrid\b/i.test(text)) modes.push('hybrid')
  if (/\bon-?site\b|\bin-office\b/i.test(text)) modes.push('onsite')
  return modes
}

/** Finds every distinct "City, ST" mention in the JD, not just the first —
 * a JD open to several offices should populate all of them. */
function extractLocations(text: string): LocationEntry[] {
  const entries: LocationEntry[] = []
  const seen = new Set<string>()
  const cityStateMatches = text.matchAll(/([A-Z][a-zA-Z.]+(?:\s[A-Z][a-zA-Z.]+)*),\s*([A-Z]{2})\b/g)

  for (const match of cityStateMatches) {
    if (!US_STATE_CODES.has(match[2])) {
      continue
    }
    const key = `${match[1]}|${match[2]}`
    if (seen.has(key)) {
      continue
    }
    seen.add(key)
    // A recognized 2-letter US state code unambiguously implies "United
    // States" for THIS entry, regardless of what other country words (e.g.
    // a second office's country) appear elsewhere in the same JD.
    entries.push({ city: match[1], state: match[2], country: 'United States', zip: '' })
  }

  if (entries.length === 0) {
    let country: string | null = null
    for (const [pattern, label] of COUNTRY_HINTS) {
      if (pattern.test(text)) {
        country = label
        break
      }
    }

    const remoteParenMatch = text.match(/remote\s*\(([^)]+)\)/i)
    if (!country && remoteParenMatch) {
      const hint = remoteParenMatch[1].trim()
      country = /^us$/i.test(hint) || /united states/i.test(hint) ? 'United States' : hint
    }
    if (country) {
      entries.push({ city: '', state: '', country, zip: '' })
    }
  }

  return entries
}

function extractExperience(text: string): LocalExtraction['experience'] {
  const rangeMatch = text.match(/(\d+)\s*(?:-|–|to)\s*(\d+)\+?\s*years?/i)
  if (rangeMatch) {
    return { minimumYears: Number(rangeMatch[1]), maximumYears: Number(rangeMatch[2]) }
  }

  const plusMatch = text.match(/(\d+)\+\s*years?/i)
  if (plusMatch) {
    return { minimumYears: Number(plusMatch[1]), maximumYears: null }
  }

  const bareMatch = text.match(/(\d+)\s*years?\s*(?:of\s+)?experience/i)
  if (bareMatch) {
    return { minimumYears: Number(bareMatch[1]), maximumYears: null }
  }

  return { minimumYears: null, maximumYears: null }
}

/** Finds every distinct experience-year mention in the JD (not just the
 * first) so conflicting requirements — e.g. "5+ years" in one place and
 * "8-10 years" in another — can be surfaced for the recruiter to resolve. */
export function detectAllExperienceRanges(text: string): Array<{ minimumYears: number | null; maximumYears: number | null }> {
  const found: Array<{ minimumYears: number | null; maximumYears: number | null }> = []
  const seen = new Set<string>()

  for (const match of text.matchAll(/(\d+)\s*(?:-|–|to)\s*(\d+)\+?\s*years?/gi)) {
    const key = `${match[1]}-${match[2]}`
    if (!seen.has(key)) {
      seen.add(key)
      found.push({ minimumYears: Number(match[1]), maximumYears: Number(match[2]) })
    }
  }

  for (const match of text.matchAll(/(\d+)\+\s*years?/gi)) {
    const key = `${match[1]}-plus`
    if (!seen.has(key)) {
      seen.add(key)
      found.push({ minimumYears: Number(match[1]), maximumYears: null })
    }
  }

  return found
}

function extractSkillSections(text: string, ambiguousCandidates: string[]): { requiredSkills: string[]; preferredSkills: string[] } {
  const requiredHeading = text.search(/requirements?\s*:?/i)
  const preferredHeading = text.search(/nice to have|preferred|bonus/i)

  if (requiredHeading === -1 && preferredHeading === -1) {
    return { requiredSkills: withholdAmbiguousTech(findSkills(text), ambiguousCandidates), preferredSkills: [] }
  }

  let requiredSection = text
  let preferredSection = ''

  if (requiredHeading !== -1 && preferredHeading !== -1) {
    if (requiredHeading < preferredHeading) {
      requiredSection = text.slice(requiredHeading, preferredHeading)
      preferredSection = text.slice(preferredHeading)
    } else {
      preferredSection = text.slice(preferredHeading, requiredHeading)
      requiredSection = text.slice(requiredHeading)
    }
  } else if (preferredHeading !== -1) {
    requiredSection = text.slice(0, preferredHeading)
    preferredSection = text.slice(preferredHeading)
  }

  return {
    requiredSkills: withholdAmbiguousTech(findSkills(requiredSection), ambiguousCandidates),
    preferredSkills: withholdAmbiguousTech(findSkills(preferredSection), ambiguousCandidates),
  }
}

function extractSeniority(text: string): string | null {
  for (const level of SENIORITY_LEVELS) {
    if (new RegExp(`\\b${level}\\b`, 'i').test(text)) {
      return level
    }
  }
  return null
}

function extractEmploymentTypes(text: string): string[] {
  const types: string[] = []
  if (/\bfull-?time\b/i.test(text)) types.push('Full-time')
  if (/\bpart-?time\b/i.test(text)) types.push('Part-time')
  if (/\bcontract-to-hire\b|\bcontract\s+to\s+hire\b/i.test(text)) types.push('Contract-to-hire')
  else if (/\bcontract(or)?\b/i.test(text)) types.push('Contract')
  if (/\bintern(ship)?\b/i.test(text)) types.push('Internship')
  return types
}

export function extractLocally(jdText: string): LocalExtraction {
  const text = jdText.trim()

  if (!text) {
    return {
      roleTitle: null,
      locations: [],
      workModes: [],
      experience: { minimumYears: null, maximumYears: null },
      requiredSkills: [],
      preferredSkills: [],
      primaryTechCandidates: [],
      employmentTypes: [],
      seniority: null,
    }
  }

  const primaryTechCandidates = detectPrimaryTechCandidates(text)
  const { requiredSkills, preferredSkills } = extractSkillSections(text, primaryTechCandidates)

  return {
    roleTitle: extractRoleTitle(text),
    locations: extractLocations(text),
    workModes: extractWorkModes(text),
    experience: extractExperience(text),
    requiredSkills,
    preferredSkills,
    primaryTechCandidates: primaryTechCandidates.length > 1 ? primaryTechCandidates : [],
    employmentTypes: extractEmploymentTypes(text),
    seniority: extractSeniority(text),
  }
}
