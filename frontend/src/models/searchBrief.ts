// The single canonical model for a recruiter's search brief.
//
// Every screen reads from and writes to this same shape. It is populated in
// three non-destructive stages — local extraction, AI parse, recruiter edit —
// each of which enriches the object rather than replacing it. A field, once
// manually edited by the recruiter, is "locked" and future local/AI merges
// leave it alone.

import type { SearchIntent } from '../types'
import type { LocalExtraction, LocationEntry } from '../screens/localJdExtraction'
import { extractLocally, normalizeSkillList, rootTechLabelForSkill } from '../screens/localJdExtraction'

export type WorkMode = 'remote' | 'hybrid' | 'onsite'
export type EmploymentType = 'Full-time' | 'Contract' | 'Contract-to-hire' | 'Internship' | 'Part-time'
export type SearchGeography = 'global' | 'country' | 'multiple' | 'radius'

export type { LocationEntry }

export type SearchBrief = {
  role: {
    primaryTitle: string
    equivalentTitles: string[]
    pastTitles: string[]
    excludedTitles: string[]
    seniority: string
  }
  location: {
    searchGeography: SearchGeography
    country: string
    locations: LocationEntry[]
    radius: string
    workModes: WorkMode[]
  }
  experience: {
    minimumYears: string
    maximumYears: string
  }
  skills: {
    required: string[]
    preferred: string[]
    excluded: string[]
    primaryTechnology: {
      candidates: string[]
      mode: 'single' | 'multiple' | null
      selected: string | null
    }
  }
  companies: {
    include: string[]
    exclude: string[]
  }
  industries: string[]
  education: string[]
  employmentTypes: EmploymentType[]
}

export const DEFAULT_EXCLUDED_TITLES = ['CTO', 'CIO', 'CAIO', 'VP', 'Vice President', 'Director', 'Founder', 'Head of', 'Chief Architect']

export function createEmptyLocationEntry(): LocationEntry {
  return { city: '', state: '', country: '', zip: '' }
}

export function createEmptySearchBrief(): SearchBrief {
  return {
    role: {
      primaryTitle: '',
      equivalentTitles: [],
      pastTitles: [],
      excludedTitles: [...DEFAULT_EXCLUDED_TITLES],
      seniority: '',
    },
    location: {
      searchGeography: 'multiple',
      country: '',
      locations: [],
      radius: '',
      workModes: [],
    },
    experience: { minimumYears: '', maximumYears: '' },
    skills: {
      required: [],
      preferred: [],
      excluded: [],
      primaryTechnology: { candidates: [], mode: null, selected: null },
    },
    companies: { include: [], exclude: [] },
    industries: [],
    education: [],
    employmentTypes: [],
  }
}

function normalizeWorkMode(value?: string | null): WorkMode | null {
  const normalized = value?.trim().toLowerCase()
  if (normalized === 'remote' || normalized === 'hybrid' || normalized === 'onsite') {
    return normalized
  }
  return null
}

const US_STATE_SUFFIX = /,?\s*([A-Z]{2})\s*$/

/** The parser returns city/state combined as one "cities" string (e.g. "Austin, TX").
 * Split the trailing state code back out so it can seed a proper LocationEntry. */
function splitCityState(raw: string): { city: string; state: string } {
  const match = raw.match(US_STATE_SUFFIX)
  if (!match) {
    return { city: raw.trim(), state: '' }
  }
  return { city: raw.slice(0, match.index).replace(/,\s*$/, '').trim(), state: match[1] }
}

/** Filters out any skill belonging to a still-ambiguous primary-tech family —
 * used so an AI parse can't reintroduce Python/Java/.NET etc. directly into
 * Required/Preferred while the recruiter hasn't picked a primary technology yet. */
function withholdAmbiguousTech(skills: string[], ambiguousCandidates: string[]): string[] {
  if (ambiguousCandidates.length < 2) {
    return skills
  }
  return skills.filter((skill) => !ambiguousCandidates.includes(rootTechLabelForSkill(skill) ?? ''))
}

/** Stage 1 — live, local, heuristic. Runs on every keystroke while the recruiter types the JD. */
export function applyLocalExtraction(brief: SearchBrief, jdText: string, locked: ReadonlySet<string>): SearchBrief {
  const extraction: LocalExtraction = extractLocally(jdText)

  return {
    ...brief,
    role: {
      ...brief.role,
      primaryTitle: locked.has('role.primaryTitle') ? brief.role.primaryTitle : extraction.roleTitle ?? '',
      seniority: locked.has('role.seniority') ? brief.role.seniority : extraction.seniority ?? '',
    },
    location: {
      ...brief.location,
      locations: locked.has('location.locations') ? brief.location.locations : extraction.locations,
      country: locked.has('location.country') ? brief.location.country : (extraction.locations[0]?.country ?? ''),
      workModes: locked.has('location.workModes') ? brief.location.workModes : extraction.workModes,
    },
    experience: {
      minimumYears: locked.has('experience.minimumYears')
        ? brief.experience.minimumYears
        : extraction.experience.minimumYears != null ? String(extraction.experience.minimumYears) : '',
      maximumYears: locked.has('experience.maximumYears')
        ? brief.experience.maximumYears
        : extraction.experience.maximumYears != null ? String(extraction.experience.maximumYears) : '',
    },
    skills: {
      ...brief.skills,
      required: locked.has('skills.required') ? brief.skills.required : extraction.requiredSkills,
      preferred: locked.has('skills.preferred') ? brief.skills.preferred : extraction.preferredSkills,
      primaryTechnology: locked.has('skills.primaryTechnology')
        ? brief.skills.primaryTechnology
        : { candidates: extraction.primaryTechCandidates, mode: null, selected: null },
    },
    employmentTypes: locked.has('employmentTypes')
      ? brief.employmentTypes
      : (extraction.employmentTypes as EmploymentType[]),
  }
}

/** Stage 2 — AI parse. Enriches empty/unlocked fields with the backend's understanding; never blanks a field the recruiter already has. */
export function applyAiParse(brief: SearchBrief, intent: SearchIntent, locked: ReadonlySet<string>): SearchBrief {
  const pick = (path: string, aiValue: string | undefined | null, current: string) =>
    locked.has(path) ? current : (aiValue && aiValue.trim() ? aiValue : current)

  const pickList = <T extends string>(path: string, aiValue: T[] | undefined, current: T[]): T[] =>
    locked.has(path) ? current : (aiValue && aiValue.length ? aiValue : current)

  const aiLocations: LocationEntry[] = (intent.location.cities.length ? intent.location.cities : ['']).map((rawCity) => {
    const { city, state } = splitCityState(rawCity)
    return { city, state, country: intent.location.countries[0] ?? '', zip: '' }
  }).filter((entry) => entry.city || entry.state || entry.country)

  const aiWorkMode = normalizeWorkMode(intent.location.work_mode)

  // Primary-technology ambiguity is only ever detected from the raw JD text
  // (stage 1); the AI's own required/preferred arrays are filtered through
  // whatever candidate set stage 1 already established, so the same
  // arbitration applies regardless of which stage produced the skill.
  const activeCandidates = locked.has('skills.primaryTechnology') ? [] : brief.skills.primaryTechnology.candidates

  return {
    ...brief,
    role: {
      ...brief.role,
      primaryTitle: pick('role.primaryTitle', intent.role.title, brief.role.primaryTitle),
      equivalentTitles: pickList('role.equivalentTitles', intent.titles.include_titles, brief.role.equivalentTitles),
      seniority: pick('role.seniority', intent.role.seniority, brief.role.seniority),
    },
    location: {
      ...brief.location,
      locations: locked.has('location.locations') ? brief.location.locations : (aiLocations.length ? aiLocations : brief.location.locations),
      country: locked.has('location.country') ? brief.location.country : (intent.location.countries[0] ?? brief.location.country),
      workModes: locked.has('location.workModes') ? brief.location.workModes : (aiWorkMode ? [aiWorkMode] : brief.location.workModes),
    },
    // The JD parser uses 0 as its "not specified" sentinel for experience years
    // (an open-ended "5+ years" comes back as { minimum_years: 5, maximum_years: 0 }),
    // so treat 0 the same as an absent value here.
    experience: {
      minimumYears: pick(
        'experience.minimumYears',
        intent.experience.minimum_years ? String(intent.experience.minimum_years) : null,
        brief.experience.minimumYears,
      ),
      maximumYears: pick(
        'experience.maximumYears',
        intent.experience.maximum_years ? String(intent.experience.maximum_years) : null,
        brief.experience.maximumYears,
      ),
    },
    skills: {
      required: pickList(
        'skills.required',
        normalizeSkillList(withholdAmbiguousTech(intent.skills.required_skills ?? [], activeCandidates)),
        brief.skills.required,
      ),
      preferred: pickList(
        'skills.preferred',
        normalizeSkillList(withholdAmbiguousTech(intent.skills.preferred_skills ?? [], activeCandidates)),
        brief.skills.preferred,
      ),
      excluded: brief.skills.excluded,
      primaryTechnology: brief.skills.primaryTechnology,
    },
    companies: {
      include: pickList('companies.include', intent.previous_background.preferred_companies, brief.companies.include),
      exclude: pickList('companies.exclude', intent.company_preferences.exclude_current_companies, brief.companies.exclude),
    },
    employmentTypes: pickList(
      'employmentTypes',
      intent.role.employment_type ? [intent.role.employment_type as EmploymentType] : undefined,
      brief.employmentTypes,
    ),
  }
}

/** Mode 1 — a single primary technology: it moves into Required, the rest
 * move into Preferred automatically. No manual reorganizing needed. */
export function resolveSinglePrimaryTechnology(brief: SearchBrief, selected: string): SearchBrief {
  const others = brief.skills.primaryTechnology.candidates.filter((candidate) => candidate !== selected)
  const selectedSkills = normalizeSkillList([selected])
  const otherSkills = normalizeSkillList(others)

  return {
    ...brief,
    skills: {
      ...brief.skills,
      required: Array.from(new Set([...brief.skills.required, ...selectedSkills])),
      preferred: Array.from(new Set([...brief.skills.preferred, ...otherSkills])),
      primaryTechnology: { ...brief.skills.primaryTechnology, mode: 'single', selected },
    },
  }
}

/** Mode 2 — a genuinely polyglot role: every detected candidate stays in
 * Required. Nothing is moved to Preferred automatically. */
export function resolveMultiplePrimaryTechnologies(brief: SearchBrief): SearchBrief {
  const allSkills = normalizeSkillList(brief.skills.primaryTechnology.candidates)

  return {
    ...brief,
    skills: {
      ...brief.skills,
      required: Array.from(new Set([...brief.skills.required, ...allSkills])),
      primaryTechnology: { ...brief.skills.primaryTechnology, mode: 'multiple', selected: null },
    },
  }
}

/** Applies one structured clarification answer on top of an already AI-parsed
 * brief. Runs last, after local extraction and AI parse, so nothing
 * overwrites the recruiter's explicit resolution afterward. */
export function applyClarificationAnswer(brief: SearchBrief, questionId: string, value: string): SearchBrief {
  switch (questionId) {
    case 'primaryTechnology':
      return value === '__multiple__' ? resolveMultiplePrimaryTechnologies(brief) : resolveSinglePrimaryTechnology(brief, value)

    case 'locationCountry':
      if (value === '__all__') {
        return { ...brief, location: { ...brief.location, searchGeography: 'multiple' } }
      }
      return {
        ...brief,
        location: {
          ...brief.location,
          searchGeography: 'country',
          country: value,
          locations: brief.location.locations.filter((entry) => entry.country === value),
        },
      }

    case 'experienceRange': {
      const [minRaw, maxRaw] = value.split('-')
      return { ...brief, experience: { minimumYears: minRaw || '', maximumYears: maxRaw || '' } }
    }

    case 'workMode':
      return { ...brief, location: { ...brief.location, workModes: [value as WorkMode] } }

    case 'seniority':
      return { ...brief, role: { ...brief.role, seniority: value } }

    default:
      return brief
  }
}

/** Lock paths to protect after a clarification answer is applied, so a later
 * trip back to the JD screen can't silently undo the recruiter's decision. */
export const CLARIFICATION_LOCK_PATHS: Record<string, string[]> = {
  primaryTechnology: ['skills.primaryTechnology', 'skills.required', 'skills.preferred'],
  locationCountry: ['location.searchGeography', 'location.country', 'location.locations'],
  experienceRange: ['experience.minimumYears', 'experience.maximumYears'],
  workMode: ['location.workModes'],
  seniority: ['role.seniority'],
}

/** For calling the existing /search endpoint — maps only the fields that endpoint understands today. */
export function briefToSearchIntent(brief: SearchBrief): SearchIntent {
  const geography = brief.location.searchGeography
  const locations = geography === 'multiple' || geography === 'radius' ? brief.location.locations : []

  const countries =
    geography === 'country' && brief.location.country
      ? [brief.location.country]
      : Array.from(new Set(locations.map((entry) => entry.country).filter(Boolean)))

  const cities = locations
    .map((entry) => [entry.city, entry.state, entry.zip].filter((part) => part.trim()).join(', '))
    .filter(Boolean)

  return {
    role: {
      title: brief.role.primaryTitle || undefined,
      seniority: brief.role.seniority || undefined,
      employment_type: brief.employmentTypes[0] || undefined,
    },
    location: {
      countries,
      cities,
      work_mode: brief.location.workModes[0] || undefined,
    },
    experience: {
      minimum_years: brief.experience.minimumYears ? Number(brief.experience.minimumYears) : null,
      maximum_years: brief.experience.maximumYears ? Number(brief.experience.maximumYears) : null,
    },
    titles: { include_titles: brief.role.equivalentTitles, exclude_titles: brief.role.excludedTitles },
    skills: {
      required_skills: brief.skills.required,
      preferred_skills: brief.skills.preferred,
    },
    previous_background: {
      preferred_technologies: [],
      preferred_companies: brief.companies.include,
    },
    ai_focus: {},
    company_preferences: {
      exclude_current_companies: brief.companies.exclude,
      preferred_company_types: [],
    },
    ranking: { must_have: brief.skills.required, nice_to_have: brief.skills.preferred, bonus: [] },
  }
}
