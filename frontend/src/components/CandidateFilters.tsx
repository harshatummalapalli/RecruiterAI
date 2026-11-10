import { useMemo } from 'react'
import { RotateCcw } from 'lucide-react'
import type { DiscoveryCandidate } from '../models/discovery'

// Include/Exclude filters over the deterministic, CrustData-derived attributes
// every candidate already carries (company kind, seniority, recency). Purely a
// local view filter — it never re-searches, never spends credits, and never
// changes what the backend admitted or ranked. It only narrows what's on screen.

export type FacetState = 'include' | 'exclude'

export type CandidateFilterState = {
  // value -> include|exclude. Absent = neutral (no constraint).
  companyType: Record<string, FacetState>
  seniority: Record<string, FacetState>
  // recently_started is a single boolean signal, so it's a tri-state of its own.
  recency: 'any' | 'include' | 'exclude'
}

export const EMPTY_FILTERS: CandidateFilterState = { companyType: {}, seniority: {}, recency: 'any' }

export function filtersActive(state: CandidateFilterState): boolean {
  return (
    Object.keys(state.companyType).length > 0 ||
    Object.keys(state.seniority).length > 0 ||
    state.recency !== 'any'
  )
}

// A candidate's facet values, read the same way the record card's AttributeTags reads them.
function companyTypeOf(c: DiscoveryCandidate): string | null {
  const t = c.attributes?.company_type
  return t && t !== 'Unknown' ? t : null
}
function seniorityOf(c: DiscoveryCandidate): string | null {
  return c.attributes?.ic_level || c.attributes?.seniority_band || null
}
function recentlyStartedOf(c: DiscoveryCandidate): boolean {
  return Boolean(c.attributes?.recently_started)
}

// Does a value pass a value-keyed facet map? If any value is set to "include",
// the candidate must match one of them; a value set to "exclude" rejects a
// match. Neutral values impose nothing.
function passesFacet(value: string | null, map: Record<string, FacetState>): boolean {
  const includes = Object.entries(map).filter(([, s]) => s === 'include').map(([v]) => v)
  const excludes = Object.entries(map).filter(([, s]) => s === 'exclude').map(([v]) => v)
  if (value && excludes.includes(value)) return false
  if (includes.length > 0) return value != null && includes.includes(value)
  return true
}

export function candidatePassesFilters(c: DiscoveryCandidate, state: CandidateFilterState): boolean {
  if (!passesFacet(companyTypeOf(c), state.companyType)) return false
  if (!passesFacet(seniorityOf(c), state.seniority)) return false
  if (state.recency === 'include' && !recentlyStartedOf(c)) return false
  if (state.recency === 'exclude' && recentlyStartedOf(c)) return false
  return true
}

// neutral -> include -> exclude -> neutral
function nextFacet(current: FacetState | undefined): FacetState | undefined {
  if (current === undefined) return 'include'
  if (current === 'include') return 'exclude'
  return undefined
}

const SENIORITY_RANK = ['Distinguished', 'Fellow', 'Principal', 'Staff', 'Architect', 'Lead', 'Senior', 'Mid', 'Junior']

function sortValues(dimension: 'companyType' | 'seniority', values: string[]): string[] {
  if (dimension === 'seniority') {
    return [...values].sort((a, b) => {
      const ia = SENIORITY_RANK.indexOf(a)
      const ib = SENIORITY_RANK.indexOf(b)
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib) || a.localeCompare(b)
    })
  }
  return [...values].sort((a, b) => a.localeCompare(b))
}

function Chip({ label, state, onClick, title }: { label: string; state: FacetState | undefined; onClick: () => void; title?: string }) {
  const cls = state === 'include' ? ' is-include' : state === 'exclude' ? ' is-exclude' : ''
  return (
    <button
      type="button"
      className={`cf-chip${cls}`}
      aria-pressed={state !== undefined}
      onClick={onClick}
      title={title}
    >
      {state === 'exclude' ? <span aria-hidden="true" className="cf-chip__mark">−</span> : state === 'include' ? <span aria-hidden="true" className="cf-chip__mark">+</span> : null}
      {label}
    </button>
  )
}

type Props = {
  candidates: DiscoveryCandidate[]
  state: CandidateFilterState
  onChange: (next: CandidateFilterState) => void
  /** How many pass right now / how many there are in total, for the live count. */
  shown: number
  total: number
}

export function CandidateFilters({ candidates, state, onChange, shown, total }: Props) {
  // Facet options come from the whole presented set, so a chip never vanishes
  // just because the current filter hid every candidate that carried it.
  const companyValues = useMemo(() => {
    const set = new Set<string>()
    candidates.forEach((c) => { const v = companyTypeOf(c); if (v) set.add(v) })
    return sortValues('companyType', [...set])
  }, [candidates])
  const seniorityValues = useMemo(() => {
    const set = new Set<string>()
    candidates.forEach((c) => { const v = seniorityOf(c); if (v) set.add(v) })
    return sortValues('seniority', [...set])
  }, [candidates])
  const anyRecent = useMemo(() => candidates.some(recentlyStartedOf), [candidates])

  // Nothing deterministic to filter on (e.g. a legacy search with no attributes) — show nothing.
  if (companyValues.length === 0 && seniorityValues.length === 0 && !anyRecent) return null

  const toggleCompany = (value: string) => {
    const next = { ...state.companyType }
    const n = nextFacet(next[value])
    if (n === undefined) delete next[value]
    else next[value] = n
    onChange({ ...state, companyType: next })
  }
  const toggleSeniority = (value: string) => {
    const next = { ...state.seniority }
    const n = nextFacet(next[value])
    if (n === undefined) delete next[value]
    else next[value] = n
    onChange({ ...state, seniority: next })
  }
  const toggleRecency = () => {
    const order: Array<CandidateFilterState['recency']> = ['any', 'include', 'exclude']
    const n = order[(order.indexOf(state.recency) + 1) % order.length]
    onChange({ ...state, recency: n })
  }

  const active = filtersActive(state)

  return (
    <div className="candidate-filters" role="group" aria-label="Filter candidates">
      <div className="cf-row">
        <span className="cf-hint">Click once to keep, twice to exclude.</span>
        {active ? (
          <span className="cf-count">Showing {shown} of {total}</span>
        ) : null}
        {active ? (
          <button type="button" className="cf-clear" onClick={() => onChange(EMPTY_FILTERS)}>
            <RotateCcw size={12} aria-hidden="true" /> Clear filters
          </button>
        ) : null}
      </div>

      {companyValues.length > 0 ? (
        <div className="cf-group">
          <span className="cf-group__label">Company</span>
          <div className="cf-chips">
            {companyValues.map((value) => (
              <Chip key={value} label={value} state={state.companyType[value]} onClick={() => toggleCompany(value)} />
            ))}
          </div>
        </div>
      ) : null}

      {seniorityValues.length > 0 ? (
        <div className="cf-group">
          <span className="cf-group__label">Seniority</span>
          <div className="cf-chips">
            {seniorityValues.map((value) => (
              <Chip key={value} label={value} state={state.seniority[value]} onClick={() => toggleSeniority(value)} />
            ))}
          </div>
        </div>
      ) : null}

      {anyRecent ? (
        <div className="cf-group">
          <span className="cf-group__label">Tenure</span>
          <div className="cf-chips">
            <Chip
              label="Recently started"
              state={state.recency === 'any' ? undefined : state.recency}
              onClick={toggleRecency}
              title="Started the current role within the last few months"
            />
          </div>
        </div>
      ) : null}
    </div>
  )
}
