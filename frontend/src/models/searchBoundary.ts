// Mirrors backend/models/intake.py's SearchBoundary exactly — the
// recruiter's explicit, authoritative search boundary, submitted alongside
// raw_input at intake start. RECRUITER DEFINES: hiring company, country,
// work mode, geographic scope. Everything else stays AI-derived. See
// backend/services/intake_reasoning.py's apply_search_boundary for how this
// is applied server-side.
export type WorkMode = 'onsite' | 'hybrid' | 'remote'
export type RemoteScope = 'anywhere' | 'states' | 'cities'

export type SearchBoundary = {
  hiring_company: string
  country: string
  // Empty until the recruiter chooses: there is no default, so "mandatory" cannot be satisfied by accident.
  work_mode: WorkMode | ''
  state?: string | null
  city?: string | null
  radius_miles?: number | null
  // Onsite/hybrid multi-city: several named cities (city in [...]), used
  // INSTEAD of the single city + radius when non-empty. Optional so a boundary
  // restored from an older session still type-checks.
  cities?: string[]
  remote_scope?: RemoteScope | null
  remote_states: string[]
  remote_cities: string[]
  // Company targeting. include = candidates who EVER worked at any of these (OR);
  // exclude = not currently at these (the hiring company is always excluded too).
  // Optional so a boundary restored from an older session still type-checks.
  include_companies?: string[]
  exclude_companies?: string[]
  // Per-list scope: 'current' (current employer only) or 'ever' (anywhere in their
  // history). Optional + defaulted so an older restored session still type-checks.
  include_companies_scope?: 'current' | 'ever'
  exclude_companies_scope?: 'current' | 'ever'
  // Experience is a first-step recruiter input now (min required, max optional),
  // not only read from the JD — so a JD that omits it never blocks on a clarification.
  min_years?: number | null
  max_years?: number | null
}

export function createEmptySearchBoundary(): SearchBoundary {
  return {
    hiring_company: '',
    country: '',
    work_mode: '',
    state: '',
    city: '',
    radius_miles: null,
    cities: [],
    remote_scope: null,
    remote_states: [],
    remote_cities: [],
    include_companies: [],
    exclude_companies: [],
    include_companies_scope: 'ever',
    exclude_companies_scope: 'current',
    min_years: null,
    max_years: null,
  }
}

/** True once every field the current work_mode requires is filled — gates
 * the "Build Search Brief" submit button. Mirrors the backend's own
 * mandatory-field rules (see the Final Intake Form Pass spec): Hiring
 * Company, Country and Work Mode are always required; Onsite/Hybrid also
 * require State + City + Radius; Remote requires a resolved scope
 * (Anywhere, or at least one specific state/city). */
export function isSearchBoundaryComplete(boundary: SearchBoundary): boolean {
  if (!boundary.hiring_company.trim() || !boundary.country.trim() || !boundary.work_mode) {
    return false
  }
  // Minimum years is a required first-step input.
  if (boundary.min_years == null || boundary.min_years < 0) return false
  if (boundary.work_mode === 'onsite' || boundary.work_mode === 'hybrid') {
    // Multi-city mode (several named cities) is complete on its own; otherwise
    // the classic single city + radius is required.
    if ((boundary.cities?.length ?? 0) > 0) return true
    return Boolean(boundary.state?.trim() && boundary.city?.trim() && boundary.radius_miles && boundary.radius_miles > 0)
  }
  // Remote.
  if (boundary.remote_scope === 'anywhere') return true
  if (boundary.remote_scope === 'states') return boundary.remote_states.length > 0
  if (boundary.remote_scope === 'cities') return boundary.remote_cities.length > 0
  return false
}

/** The non-negotiables still missing, phrased for a recruiter — so a disabled
 * "Read & plan" button can say exactly what it is waiting for instead of nothing.
 * Mirrors isSearchBoundaryComplete field-for-field. */
export function missingBoundaryFields(boundary: SearchBoundary): string[] {
  const missing: string[] = []
  if (!boundary.hiring_company.trim()) missing.push('the hiring company')
  if (!boundary.country.trim()) missing.push('a country')
  if (boundary.min_years == null || boundary.min_years < 0) missing.push('minimum years')
  if (!boundary.work_mode) {
    missing.push('a work mode')
  } else if (boundary.work_mode === 'onsite' || boundary.work_mode === 'hybrid') {
    const hasCities = (boundary.cities?.length ?? 0) > 0
    const hasClassic = Boolean(boundary.state?.trim() && boundary.city?.trim() && boundary.radius_miles && boundary.radius_miles > 0)
    if (!hasCities && !hasClassic) missing.push('a location (cities, or state + city + radius)')
  } else {
    const ok =
      boundary.remote_scope === 'anywhere' ||
      (boundary.remote_scope === 'states' && boundary.remote_states.length > 0) ||
      (boundary.remote_scope === 'cities' && boundary.remote_cities.length > 0)
    if (!ok) missing.push('a remote scope (anywhere, or at least one state/city)')
  }
  return missing
}
