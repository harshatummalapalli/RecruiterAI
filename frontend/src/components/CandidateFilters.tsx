import { useMemo } from 'react'
import { RotateCcw } from 'lucide-react'
import type { DiscoveryCandidate } from '../models/discovery'
import {
  EMPTY_FILTERS,
  candidatePassesFilters,
  filtersActive,
  companyTypeOf,
  seniorityOf,
  recentlyStartedOf,
  openToWorkOf,
  nextFacet,
  sortValues,
  type FacetState,
  type CandidateFilterState,
} from './candidateFilterModel'

// Include/Exclude filters over the deterministic, CrustData-derived attributes every
// candidate already carries. Purely a local view filter — it never re-searches, spends
// credits, or changes what the backend admitted/ranked; it only narrows what's on screen.
// The pure model (state shape + predicates) lives in ./candidateFilterModel so it is
// unit-testable without React; re-exported here so existing importers are unchanged.
export { EMPTY_FILTERS, candidatePassesFilters, filtersActive }
export type { FacetState, CandidateFilterState }

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
  const anyOpenToWork = useMemo(() => candidates.some((c) => openToWorkOf(c) === true), [candidates])

  // Nothing deterministic to filter on (e.g. a legacy search with no attributes) — show nothing.
  if (companyValues.length === 0 && seniorityValues.length === 0 && !anyRecent && !anyOpenToWork) return null

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
  const toggleOpenToWork = () => {
    const order: Array<CandidateFilterState['openToWork']> = ['any', 'include', 'exclude']
    const n = order[(order.indexOf(state.openToWork) + 1) % order.length]
    onChange({ ...state, openToWork: n })
  }

  const active = filtersActive(state)

  return (
    <div className="candidate-filters" role="group" aria-label="Filter candidates">
      <div className="cf-row">
        <span className="cf-hint">Filters the profiles already found — click once to keep, twice to exclude.</span>
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
          <span className="cf-group__label">Company Type</span>
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

      {anyOpenToWork ? (
        <div className="cf-group">
          <span className="cf-group__label">Availability</span>
          <div className="cf-chips">
            <Chip
              label="Open to work"
              state={state.openToWork === 'any' ? undefined : state.openToWork}
              onClick={toggleOpenToWork}
              title="Self-reported on LinkedIn (soft signal) — many strong passive candidates never set it"
            />
          </div>
        </div>
      ) : null}
    </div>
  )
}
