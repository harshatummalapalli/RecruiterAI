// The single canonical model for a recruiter's search brief.
//
// Every screen reads from and writes to this same shape. It is populated in
// two non-destructive stages — AI parse, recruiter edit — each of which
// enriches the object rather than replacing it. A field, once manually
// edited by the recruiter, is "locked" and future AI merges leave it alone.

import type { SearchIntent } from '../types'
import type { LocationEntry } from '../screens/localJdExtraction'
import { normalizeSkillList, rootTechLabelForSkill } from '../screens/localJdExtraction'
import { expandTitle } from '../intelligence/titleIntelligence'
import { createEmptyAiConceptFlags, type AiConceptFlags } from '../intelligence/technologyGraph'
import { DEFAULT_EXCLUDED_TITLES } from '../intelligence/types'

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
  /** Internal-only, Intelligence-Layer-derived signal — never rendered in
   * the UI. Populated straight from explicit JD text mentions, never
   * inferred beyond that evidence. */
  aiFocus: AiConceptFlags
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
      mode: 'single' | 'multiple' | 'acceptable' | null
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

export { DEFAULT_EXCLUDED_TITLES }

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
    aiFocus: createEmptyAiConceptFlags(),
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

  // Title Intelligence: the backend parser only ever returns "equivalent"
  // titles (as include_titles), never past titles. When it comes back empty,
  // or to seed past titles at all, reason from the resolved title/seniority
  // instead of leaving the recruiter to type every variant by hand.
  const resolvedTitle = pick('role.primaryTitle', intent.role.title, brief.role.primaryTitle)
  const resolvedSeniority = pick('role.seniority', intent.role.seniority, brief.role.seniority)
  const titleExpansion = expandTitle(resolvedTitle, resolvedSeniority)

  let next: SearchBrief = {
    ...brief,
    role: {
      ...brief.role,
      primaryTitle: resolvedTitle,
      equivalentTitles: pickList(
        'role.equivalentTitles',
        intent.titles.include_titles?.length ? intent.titles.include_titles : titleExpansion.equivalentTitles,
        brief.role.equivalentTitles,
      ),
      pastTitles: locked.has('role.pastTitles')
        ? brief.role.pastTitles
        : (brief.role.pastTitles.length ? brief.role.pastTitles : titleExpansion.pastTitles),
      seniority: resolvedSeniority,
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

  // The Intelligence Layer may have already confidently resolved the
  // primary-technology question during local extraction (stage 1), before
  // this AI parse ever ran. That resolution isn't locked — it wasn't a
  // recruiter decision — so the AI's own required/preferred arrays above
  // would otherwise silently drop it. Re-apply it on top, the same way an
  // explicit recruiter clarification answer is applied after AI parse.
  if (!locked.has('skills.primaryTechnology')) {
    switch (brief.skills.primaryTechnology.mode) {
      case 'multiple':
        next = resolveMultiplePrimaryTechnologies(next)
        break
      case 'acceptable':
        next = resolveAcceptableBackgrounds(next)
        break
      case 'single':
        if (brief.skills.primaryTechnology.selected) {
          next = resolveSinglePrimaryTechnology(next, brief.skills.primaryTechnology.selected)
        }
        break
    }
  }

  return next
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

/** Multiple acceptable backgrounds — any one of the candidates is fine, so
 * none of them are individually required. All move to Preferred instead,
 * where matching any of them still lifts a candidate's score. */
export function resolveAcceptableBackgrounds(brief: SearchBrief): SearchBrief {
  const allSkills = normalizeSkillList(brief.skills.primaryTechnology.candidates)

  return {
    ...brief,
    skills: {
      ...brief.skills,
      preferred: Array.from(new Set([...brief.skills.preferred, ...allSkills])),
      primaryTechnology: { ...brief.skills.primaryTechnology, mode: 'acceptable', selected: null },
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

    case 'overConstrainedSkills':
      if (value === '__loosen__') {
        return {
          ...brief,
          skills: {
            ...brief.skills,
            required: [],
            preferred: Array.from(new Set([...brief.skills.preferred, ...brief.skills.required])),
          },
        }
      }
      return brief

    case 'titleExperienceMismatch':
      return value === '__keep__' ? brief : { ...brief, experience: { ...brief.experience, minimumYears: value } }

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
  overConstrainedSkills: ['skills.required', 'skills.preferred'],
  titleExperienceMismatch: ['experience.minimumYears'],
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
      states: Array.from(new Set(locations.map((entry) => entry.state).filter(Boolean))),
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
      preferred_technologies: brief.skills.primaryTechnology.candidates,
      preferred_companies: brief.companies.include,
    },
    ai_focus: {
      llm: brief.aiFocus.llm,
      rag: brief.aiFocus.rag,
      agentic_ai: brief.aiFocus.agentic,
      mcp: brief.aiFocus.mcp,
    },
    company_preferences: {
      exclude_current_companies: brief.companies.exclude,
      preferred_company_types: [],
    },
    ranking: { must_have: brief.skills.required, nice_to_have: brief.skills.preferred, bonus: [] },
  }
}

export type LocationDetail = {
  search_geography: SearchGeography
  countries: string[]
  states: string[]
  cities: string[]
  zip_codes: string[]
  radius_miles: number | null
  // Free-form place name (or ZIP text) CrustData's geo_distance geocodes
  // server-side — the backend never sends a zip_code filter field, since
  // CrustData's person_search has none.
  radius_place: string | null
  radius_unit: string
  work_mode: string | null
  employment_type: string | null
}

/** Builds the geo_distance anchor text from the first location entry: a
 * city/state pair when available, falling back to the ZIP the recruiter
 * entered. Never a coordinate — CrustData geocodes free-form place text
 * server-side. */
function buildRadiusPlace(entry: LocationEntry | undefined): string | null {
  if (!entry) return null
  const cityState = [entry.city, entry.state].filter((part) => part.trim()).join(', ')
  if (cityState) return cityState
  if (entry.zip.trim()) return entry.zip.trim()
  return null
}

/** The recruiter's exact, already-resolved location — sent to the backend
 * alongside the prose JD so it never has to re-derive location from a
 * second, lossy OpenAI pass. Unlike `briefToSearchIntent`'s `cities` field
 * (which munges city+state+zip into one string for the legacy prose-based
 * pipeline), every field here stays a clean, independently filterable list —
 * this is what actually reaches the provider's structured filters. */
export function briefToLocationDetail(brief: SearchBrief): LocationDetail {
  const geography = brief.location.searchGeography
  const locations = geography === 'multiple' || geography === 'radius' ? brief.location.locations : []

  const countries =
    geography === 'country' && brief.location.country
      ? [brief.location.country]
      : Array.from(new Set(locations.map((entry) => entry.country).filter((value) => value.trim())))

  const states = Array.from(new Set(locations.map((entry) => entry.state).filter((value) => value.trim())))
  const cities = Array.from(new Set(locations.map((entry) => entry.city).filter((value) => value.trim())))
  const zipCodes = Array.from(new Set(locations.map((entry) => entry.zip).filter((value) => value.trim())))
  const parsedRadius = geography === 'radius' && brief.location.radius ? Number(brief.location.radius) : NaN
  const radiusMiles = Number.isFinite(parsedRadius) ? parsedRadius : null

  return {
    search_geography: geography,
    countries,
    states,
    cities,
    zip_codes: zipCodes,
    radius_miles: radiusMiles,
    radius_place: geography === 'radius' && radiusMiles !== null ? buildRadiusPlace(locations[0]) : null,
    radius_unit: 'mi',
    work_mode: brief.location.workModes[0] ?? null,
    employment_type: brief.employmentTypes[0] ?? null,
  }
}

/** The ONLY function that should ever turn a backend-confirmed SearchIntent
 * (from POST /intake/{id}/confirm) into a SearchBrief. A direct, lossless
 * field copy — no expandTitle()/title-expansion heuristic, no re-parsing of
 * anything. Title expansion for the confirmed-intake path happens exactly
 * once, in the backend Search Translator (backend/services/
 * search_translator.py); this function must never independently guess
 * equivalent titles the way applyAiParse's fallback does for the legacy
 * /parse-jd flow. See the forensic investigation into why a second,
 * disconnected title-expansion step was the actual cause of "Equivalent
 * Titles" not matching what the Living Brief and the executed search agreed
 * on. */
export function searchIntentToBrief(intent: SearchIntent): SearchBrief {
  const cities = intent.location.cities ?? []
  const states = intent.location.states ?? []
  const country = intent.location.countries?.[0] ?? ''

  const locations: LocationEntry[] =
    cities.length > 0
      ? cities.map((city, index) => ({ city, state: states[index] ?? '', country, zip: '' }))
      : states.map((state) => ({ city: '', state, country, zip: '' }))

  // A country-only confirmed intent (e.g. a Remote/"Anywhere in country"
  // search boundary — see backend/services/search_translator.py's
  // _structured_locations_from_boundary) has no city/state entries at all,
  // so `locations` above comes back empty. Without the 'country' branch
  // here, this fell through to 'global', silently dropping the country and
  // searching with no location constraint at all instead of the country the
  // recruiter actually chose. A single anchored city WITH a radius (e.g. an
  // Onsite/Hybrid search boundary) must map to 'radius' specifically —
  // briefToLocationDetail only reads brief.location.radius when geography is
  // exactly 'radius', not 'multiple'.
  const searchGeography: SearchGeography =
    locations.length === 1 && intent.location.radius_miles != null
      ? 'radius'
      : locations.length > 0
        ? 'multiple'
        : country
          ? 'country'
          : 'global'

  return {
    role: {
      primaryTitle: intent.role.title ?? '',
      // Verbatim from the backend Search Translator — the resulting
      // SearchIntent/SearchPlan-derived title family, not an independently
      // invented one.
      equivalentTitles: intent.titles.include_titles ?? [],
      pastTitles: [],
      excludedTitles: intent.titles.exclude_titles ?? [],
      seniority: intent.role.seniority ?? '',
    },
    aiFocus: createEmptyAiConceptFlags(),
    location: {
      // Exact city/state/country match stays the default search — radius is
      // an opt-in the recruiter chooses explicitly via "Edit brief" ->
      // Radius Search, pre-filled below so it's immediately usable rather
      // than blank when they do.
      searchGeography,
      country,
      locations,
      // The recruiter's actual chosen radius (e.g. from an Onsite/Hybrid
      // search boundary) — previously hardcoded to '25' regardless of what
      // was actually confirmed, which was only ever right by coincidence.
      radius: intent.location.radius_miles != null ? String(intent.location.radius_miles) : '',
      workModes: normalizeWorkMode(intent.location.work_mode) ? [normalizeWorkMode(intent.location.work_mode) as WorkMode] : [],
    },
    experience: {
      minimumYears: intent.experience.minimum_years != null ? String(intent.experience.minimum_years) : '',
      maximumYears: intent.experience.maximum_years != null ? String(intent.experience.maximum_years) : '',
    },
    skills: {
      // Deliberately empty: the Search Translator does not populate a
      // fabricated skill filter (CrustData does not reliably support one on
      // this integration) — Core/Supporting/Differentiator signals reach
      // the search only through the natural-language query. See
      // CandidateReviewScreen.tsx for how this is surfaced honestly rather
      // than as "Skills: Not specified".
      required: intent.skills.required_skills ?? [],
      preferred: intent.skills.preferred_skills ?? [],
      excluded: [],
      primaryTechnology: { candidates: [], mode: null, selected: null },
    },
    companies: {
      include: intent.previous_background.preferred_companies ?? [],
      exclude: intent.company_preferences.exclude_current_companies ?? [],
    },
    industries: [],
    education: [],
    employmentTypes: intent.role.employment_type ? [intent.role.employment_type as EmploymentType] : [],
  }
}
