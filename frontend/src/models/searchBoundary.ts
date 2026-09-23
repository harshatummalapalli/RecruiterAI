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
  work_mode: WorkMode
  state?: string | null
  city?: string | null
  radius_miles?: number | null
  remote_scope?: RemoteScope | null
  remote_states: string[]
  remote_cities: string[]
}

export function createEmptySearchBoundary(): SearchBoundary {
  return {
    hiring_company: '',
    country: '',
    work_mode: 'onsite',
    state: '',
    city: '',
    radius_miles: null,
    remote_scope: null,
    remote_states: [],
    remote_cities: [],
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
  if (boundary.work_mode === 'onsite' || boundary.work_mode === 'hybrid') {
    return Boolean(boundary.state?.trim() && boundary.city?.trim() && boundary.radius_miles && boundary.radius_miles > 0)
  }
  // Remote.
  if (boundary.remote_scope === 'anywhere') return true
  if (boundary.remote_scope === 'states') return boundary.remote_states.length > 0
  if (boundary.remote_scope === 'cities') return boundary.remote_cities.length > 0
  return false
}
