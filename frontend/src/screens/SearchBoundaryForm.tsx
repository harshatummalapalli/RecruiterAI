// The first-page SEARCH BOUNDARY inputs (Final Intake Form Pass): Hiring
// Company, Country, Work Mode, and the geographic scope that goes with it.
// These are the recruiter's own explicit, authoritative facts — never
// AI-derived, never re-asked about once submitted (see backend/services/
// intake_reasoning.py's apply_search_boundary). Everything else (role,
// seniority, requirements, technologies, title variants...) stays AI
// interpretation, shown afterward on the Search Brief.
import type { SearchBoundary, WorkMode, RemoteScope } from '../models/searchBoundary'
import { LocationTypeahead } from '../components/LocationTypeahead'
import { LocationMultiTypeahead } from '../components/LocationMultiTypeahead'
import { searchCountries, searchStatesForCountry, searchCitiesForState, searchCitiesForCountry } from '../intelligence/locationData'

type SearchBoundaryFormProps = {
  boundary: SearchBoundary
  onChange: (updater: (current: SearchBoundary) => SearchBoundary) => void
  disabled?: boolean
}

const WORK_MODE_OPTIONS: Array<{ value: WorkMode; label: string }> = [
  { value: 'onsite', label: 'Onsite' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'remote', label: 'Remote' },
]

const REMOTE_SCOPE_OPTIONS: Array<{ value: RemoteScope; label: string }> = [
  { value: 'anywhere', label: 'Anywhere in country' },
  { value: 'states', label: 'Specific states/regions' },
  { value: 'cities', label: 'Specific cities' },
]

export function SearchBoundaryForm({ boundary, onChange, disabled }: SearchBoundaryFormProps) {
  const isOnsiteOrHybrid = boundary.work_mode === 'onsite' || boundary.work_mode === 'hybrid'
  const isRemote = boundary.work_mode === 'remote'

  return (
    <section className="boundary-form" aria-label="Search boundary">
      <div className="brief-field-grid brief-field-grid--two">
        <div className="brief-field">
          <label className="brief-field__label" htmlFor="boundary-hiring-company">
            Hiring Company <span aria-hidden="true">*</span>
          </label>
          <input
            id="boundary-hiring-company"
            type="text"
            className="brief-input"
            value={boundary.hiring_company}
            disabled={disabled}
            placeholder="e.g. Epiq"
            onChange={(event) => {
              const value = event.target.value
              onChange((current) => ({ ...current, hiring_company: value }))
            }}
          />
          <span className="boundary-form__caption">Current employees will be excluded from this search by default.</span>
        </div>

        <LocationTypeahead
          label="Country"
          value={boundary.country}
          disabled={disabled}
          required
          placeholder="e.g. India"
          search={(query) => searchCountries(query).map((c) => c.name)}
          onChange={(country) => {
            onChange((current) => ({ ...current, country, state: '', city: '' }))
          }}
        />
      </div>

      <div className="brief-field">
        <span className="brief-field__label">
          Work Mode <span aria-hidden="true">*</span>
        </span>
        <div className="brief-segmented" role="radiogroup" aria-label="Work mode">
          {WORK_MODE_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`brief-segmented__option${boundary.work_mode === option.value ? ' is-active' : ''}`}
              disabled={disabled}
              onClick={() =>
                onChange((current) => ({
                  ...current,
                  work_mode: option.value,
                  // Switching work mode invalidates the fields that only make
                  // sense for the previous mode — never carry stale state
                  // across the boundary.
                  state: '',
                  city: '',
                  radius_miles: null,
                  remote_scope: null,
                  remote_states: [],
                  remote_cities: [],
                }))
              }
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {isOnsiteOrHybrid ? (
        <div className="brief-field-grid brief-field-grid--three">
          <LocationTypeahead
            label="State"
            value={boundary.state ?? ''}
            disabled={disabled || !boundary.country}
            required
            placeholder={boundary.country ? 'e.g. Telangana' : 'Select a country first'}
            search={(query) => searchStatesForCountry(boundary.country, query).map((s) => s.name)}
            onChange={(state) => onChange((current) => ({ ...current, state, city: '' }))}
          />
          <LocationTypeahead
            label="City"
            value={boundary.city ?? ''}
            disabled={disabled || !boundary.state}
            required
            placeholder={boundary.state ? 'e.g. Hyderabad' : 'Select a state first'}
            search={(query) => searchCitiesForState(boundary.country, boundary.state ?? '', query)}
            onChange={(city) => onChange((current) => ({ ...current, city }))}
          />
          <div className="brief-field">
            <label className="brief-field__label" htmlFor="boundary-radius">
              Radius (miles) <span aria-hidden="true">*</span>
            </label>
            <input
              id="boundary-radius"
              type="number"
              min={1}
              className="brief-input"
              value={boundary.radius_miles ?? ''}
              disabled={disabled || !boundary.city}
              placeholder="e.g. 25"
              onChange={(event) => {
                const value = event.target.value
                onChange((current) => ({ ...current, radius_miles: value ? Number(value) : null }))
              }}
            />
          </div>
        </div>
      ) : null}

      {isRemote ? (
        <div className="brief-field">
          <span className="brief-field__label">Where can the candidate be located?</span>
          <div className="brief-segmented" role="radiogroup" aria-label="Remote location scope">
            {REMOTE_SCOPE_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                className={`brief-segmented__option${boundary.remote_scope === option.value ? ' is-active' : ''}`}
                disabled={disabled}
                onClick={() =>
                  onChange((current) => ({ ...current, remote_scope: option.value, remote_states: [], remote_cities: [] }))
                }
              >
                {option.label}
              </button>
            ))}
          </div>

          {boundary.remote_scope === 'states' ? (
            <div className="boundary-form__remote-detail">
              <LocationMultiTypeahead
                label="States/regions"
                values={boundary.remote_states}
                placeholder={boundary.country ? 'Add a state…' : 'Select a country first'}
                search={(query) => searchStatesForCountry(boundary.country, query).map((s) => s.name)}
                onChange={(remote_states) => onChange((current) => ({ ...current, remote_states }))}
              />
            </div>
          ) : null}

          {boundary.remote_scope === 'cities' ? (
            <div className="boundary-form__remote-detail">
              <LocationMultiTypeahead
                label="Cities"
                values={boundary.remote_cities}
                placeholder={boundary.country ? 'Add a city…' : 'Select a country first'}
                search={(query) => searchCitiesForCountry(boundary.country, query)}
                onChange={(remote_cities) => onChange((current) => ({ ...current, remote_cities }))}
              />
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
