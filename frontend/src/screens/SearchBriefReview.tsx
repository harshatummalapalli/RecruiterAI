import { ArrowLeft, Plus, X } from 'lucide-react'
import type { ChangeEvent } from 'react'
import { TagField } from './TagField'
import { createEmptyLocationEntry } from '../models/searchBrief'
import type { EmploymentType, SearchBrief, SearchGeography, WorkMode } from '../models/searchBrief'
import type { LocationEntry } from '../screens/localJdExtraction'

type FieldChange = (path: string, updater: (current: SearchBrief) => SearchBrief) => void

type SearchBriefReviewProps = {
  brief: SearchBrief
  onChange: FieldChange
  onFindCandidates?: () => void
  onBackToJd?: () => void
  isSearching?: boolean
  searchState?: 'idle' | 'searching' | 'done' | 'error'
  variant?: 'standalone' | 'embedded'
  submitLabel?: string
  submitBusyLabel?: string
  backLabel?: string
}

const SEARCH_GEOGRAPHIES: Array<{ value: SearchGeography; label: string }> = [
  { value: 'global', label: 'Global' },
  { value: 'country', label: 'Country' },
  { value: 'multiple', label: 'Multiple Locations' },
  { value: 'radius', label: 'Radius Search' },
]

const WORK_MODES: Array<{ value: WorkMode; label: string }> = [
  { value: 'remote', label: 'Remote' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'onsite', label: 'Onsite' },
]

const EMPLOYMENT_TYPES: EmploymentType[] = ['Full-time', 'Contract', 'Contract-to-hire', 'Internship', 'Part-time']

function locationLabel(entry: LocationEntry): string {
  const parts = [entry.city, entry.state, entry.zip, entry.country].filter((part) => part.trim())
  return parts.length ? parts.join(', ') : 'Not specified'
}

export function summarizeLocations(brief: SearchBrief): string {
  if (brief.location.searchGeography === 'global') {
    return 'Global'
  }
  if (brief.location.searchGeography === 'country') {
    return brief.location.country || 'Not specified'
  }
  if (!brief.location.locations.length) {
    return 'Not specified'
  }
  const base = brief.location.locations.map(locationLabel).join(' · ')
  if (brief.location.searchGeography === 'radius' && brief.location.radius) {
    return `${base} · ${brief.location.radius} mi radius`
  }
  return base
}

export function summarizeCompanies(include: string[], exclude: string[]): string {
  const parts: string[] = []
  if (include.length) parts.push(`${include.length} target${include.length === 1 ? '' : 's'}`)
  if (exclude.length) parts.push(`${exclude.length} excluded`)
  return parts.length ? parts.join(' · ') : 'Not specified'
}

export function summarizeSkills(required: string[], preferred: string[], excluded: string[]): string {
  const parts: string[] = []
  if (required.length) parts.push(`${required.length} required`)
  if (preferred.length) parts.push(`${preferred.length} preferred`)
  if (excluded.length) parts.push(`${excluded.length} excluded`)
  return parts.length ? parts.join(' · ') : 'Not specified'
}

export function summarizeExperience(brief: SearchBrief): string {
  const { minimumYears, maximumYears } = brief.experience
  if (minimumYears && maximumYears) return `${minimumYears}–${maximumYears} years`
  if (minimumYears) return `${minimumYears}+ years`
  if (maximumYears) return `Up to ${maximumYears} years`
  return 'Not specified'
}

export function SearchBriefReview({
  brief,
  onChange,
  onFindCandidates,
  onBackToJd,
  isSearching = false,
  searchState = 'idle',
  variant = 'standalone',
  submitLabel = 'Find Candidates',
  submitBusyLabel = 'Searching Crustdata…',
  backLabel = 'Back to JD',
}: SearchBriefReviewProps) {
  const scalarInput = (path: string, value: string, apply: (b: SearchBrief, v: string) => SearchBrief) => ({
    value,
    onChange: (event: ChangeEvent<HTMLInputElement>) => onChange(path, (current) => apply(current, event.target.value)),
  })

  const tagList = (path: string, values: string[], apply: (b: SearchBrief, v: string[]) => SearchBrief) => ({
    values,
    onChange: (next: string[]) => onChange(path, (current) => apply(current, next)),
  })

  const updateLocationEntry = (index: number, patch: Partial<LocationEntry>) => {
    onChange('location.locations', (current) => ({
      ...current,
      location: {
        ...current.location,
        locations: current.location.locations.map((entry, i) => (i === index ? { ...entry, ...patch } : entry)),
      },
    }))
  }

  const addLocationEntry = () => {
    onChange('location.locations', (current) => ({
      ...current,
      location: { ...current.location, locations: [...current.location.locations, createEmptyLocationEntry()] },
    }))
  }

  const removeLocationEntry = (index: number) => {
    onChange('location.locations', (current) => ({
      ...current,
      location: { ...current.location, locations: current.location.locations.filter((_, i) => i !== index) },
    }))
  }

  const setSearchGeography = (value: SearchGeography) => {
    onChange('location.searchGeography', (current) => {
      const needsLocations = value === 'multiple' || value === 'radius'
      const nextLocations = needsLocations && current.location.locations.length === 0 ? [createEmptyLocationEntry()] : current.location.locations
      const trimmedLocations = value === 'radius' ? nextLocations.slice(0, 1) : nextLocations
      return { ...current, location: { ...current.location, searchGeography: value, locations: trimmedLocations } }
    })
  }

  const toggleWorkMode = (mode: WorkMode) => {
    onChange('location.workModes', (current) => ({
      ...current,
      location: {
        ...current.location,
        workModes: current.location.workModes.includes(mode)
          ? current.location.workModes.filter((m) => m !== mode)
          : [...current.location.workModes, mode],
      },
    }))
  }

  const toggleEmploymentType = (type: EmploymentType) => {
    onChange('employmentTypes', (current) => ({
      ...current,
      employmentTypes: current.employmentTypes.includes(type)
        ? current.employmentTypes.filter((t) => t !== type)
        : [...current.employmentTypes, type],
    }))
  }

  const radiusLocation = brief.location.locations[0]
  // A radius search needs an anchor CrustData can geocode — either a ZIP or
  // a city/state pair both work (see buildRadiusPlace in models/searchBrief.
  // ts), so require whichever the recruiter has actually filled in rather
  // than ZIP specifically. The confirmed-intake path never has a ZIP (Task A
  // doesn't extract one) but always has city/state once a location exists.
  const showRadiusInput =
    brief.location.searchGeography === 'radius' &&
    Boolean(radiusLocation?.zip || (radiusLocation?.city && radiusLocation?.state))

  const fields = (
    <>
      <section className="brief-panel" aria-label="Search brief">
        <div className="brief-section">
          <h2 className="brief-section__title">Role</h2>
          <div className="brief-field-grid brief-field-grid--two">
            <div className="brief-field">
              <span className="brief-field__label">Primary Title</span>
              <input
                className="brief-input"
                type="text"
                placeholder="e.g. Senior Backend Engineer"
                {...scalarInput('role.primaryTitle', brief.role.primaryTitle, (b, v) => ({ ...b, role: { ...b.role, primaryTitle: v } }))}
              />
            </div>
            <div className="brief-field">
              <span className="brief-field__label">Seniority</span>
              <input
                className="brief-input"
                type="text"
                placeholder="e.g. Senior"
                {...scalarInput('role.seniority', brief.role.seniority, (b, v) => ({ ...b, role: { ...b.role, seniority: v } }))}
              />
            </div>
          </div>
          <TagField
            label="Equivalent Titles"
            placeholder="Add a title…"
            {...tagList('role.equivalentTitles', brief.role.equivalentTitles, (b, v) => ({ ...b, role: { ...b.role, equivalentTitles: v } }))}
          />
          <TagField
            label="Past Titles"
            placeholder="Add a past title…"
            {...tagList('role.pastTitles', brief.role.pastTitles, (b, v) => ({ ...b, role: { ...b.role, pastTitles: v } }))}
          />
          <TagField
            label="Excluded Titles"
            placeholder="Add a title to exclude…"
            {...tagList('role.excludedTitles', brief.role.excludedTitles, (b, v) => ({ ...b, role: { ...b.role, excludedTitles: v } }))}
          />
        </div>

        <div className="brief-section">
          <h2 className="brief-section__title">Location</h2>
          <div className="brief-segmented" role="group" aria-label="Search geography">
            {SEARCH_GEOGRAPHIES.map((geography) => (
              <button
                key={geography.value}
                type="button"
                className={`brief-segmented__option${brief.location.searchGeography === geography.value ? ' is-active' : ''}`}
                onClick={() => setSearchGeography(geography.value)}
              >
                {geography.label}
              </button>
            ))}
          </div>

          {brief.location.searchGeography === 'global' ? (
            <p className="brief-scope-detail">No location constraint — candidates anywhere are in scope.</p>
          ) : null}

          {brief.location.searchGeography === 'country' ? (
            <div className="brief-field">
              <span className="brief-field__label">Country</span>
              <input
                className="brief-input"
                type="text"
                placeholder="United States"
                {...scalarInput('location.country', brief.location.country, (b, v) => ({ ...b, location: { ...b.location, country: v } }))}
              />
            </div>
          ) : null}

          {brief.location.searchGeography === 'multiple' || brief.location.searchGeography === 'radius' ? (
            <div className="brief-location-list">
              {brief.location.locations.map((entry, index) => (
                <div key={index} className="brief-location-row">
                  <div className={brief.location.searchGeography === 'radius' ? 'brief-field-grid' : 'brief-field-grid brief-field-grid--three'}>
                    <div className="brief-field">
                      <span className="brief-field__label">Country</span>
                      <input
                        className="brief-input"
                        type="text"
                        placeholder="United States"
                        value={entry.country}
                        onChange={(event) => updateLocationEntry(index, { country: event.target.value })}
                      />
                    </div>
                    <div className="brief-field">
                      <span className="brief-field__label">State</span>
                      <input
                        className="brief-input"
                        type="text"
                        placeholder="TX"
                        value={entry.state}
                        onChange={(event) => updateLocationEntry(index, { state: event.target.value })}
                      />
                    </div>
                    <div className="brief-field">
                      <span className="brief-field__label">City</span>
                      <input
                        className="brief-input"
                        type="text"
                        placeholder="Austin"
                        value={entry.city}
                        onChange={(event) => updateLocationEntry(index, { city: event.target.value })}
                      />
                    </div>
                    {brief.location.searchGeography === 'radius' ? (
                      <div className="brief-field">
                        <span className="brief-field__label">Zip Code</span>
                        <input
                          className="brief-input"
                          type="text"
                          placeholder="Required for radius"
                          value={entry.zip}
                          onChange={(event) => updateLocationEntry(index, { zip: event.target.value })}
                        />
                      </div>
                    ) : null}
                  </div>

                  {brief.location.searchGeography === 'multiple' && brief.location.locations.length > 1 ? (
                    <button
                      type="button"
                      className="brief-location-remove"
                      onClick={() => removeLocationEntry(index)}
                      aria-label="Remove location"
                    >
                      <X size={14} />
                    </button>
                  ) : null}
                </div>
              ))}

              {brief.location.searchGeography === 'multiple' ? (
                <button type="button" className="brief-location-add" onClick={addLocationEntry}>
                  <Plus size={14} aria-hidden="true" />
                  Add location
                </button>
              ) : null}

              {showRadiusInput ? (
                <div className="brief-field">
                  <span className="brief-field__label">Radius (miles)</span>
                  <input
                    className="brief-input"
                    type="number"
                    min={0}
                    placeholder="e.g. 25"
                    {...scalarInput('location.radius', brief.location.radius, (b, v) => ({ ...b, location: { ...b.location, radius: v } }))}
                  />
                </div>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="brief-section">
          <h2 className="brief-section__title">Experience</h2>
          <div className="brief-field-grid brief-field-grid--two">
            <div className="brief-field">
              <span className="brief-field__label">Minimum Years</span>
              <input
                className="brief-input"
                type="number"
                min={0}
                placeholder="0"
                {...scalarInput('experience.minimumYears', brief.experience.minimumYears, (b, v) => ({ ...b, experience: { ...b.experience, minimumYears: v } }))}
              />
            </div>
            <div className="brief-field">
              <span className="brief-field__label">Maximum Years</span>
              <input
                className="brief-input"
                type="number"
                min={0}
                placeholder="Leave blank if open-ended"
                {...scalarInput('experience.maximumYears', brief.experience.maximumYears, (b, v) => ({ ...b, experience: { ...b.experience, maximumYears: v } }))}
              />
            </div>
          </div>
        </div>

        <div className="brief-section">
          <h2 className="brief-section__title">Skills</h2>

          <div className="brief-field-grid brief-field-grid--two">
            <TagField label="Required Skills" placeholder="Add a skill…" {...tagList('skills.required', brief.skills.required, (b, v) => ({ ...b, skills: { ...b.skills, required: v } }))} />
            <TagField label="Preferred Skills" placeholder="Add a skill…" {...tagList('skills.preferred', brief.skills.preferred, (b, v) => ({ ...b, skills: { ...b.skills, preferred: v } }))} />
          </div>
          <TagField label="Excluded Skills" placeholder="Add a skill to avoid…" {...tagList('skills.excluded', brief.skills.excluded, (b, v) => ({ ...b, skills: { ...b.skills, excluded: v } }))} />
        </div>

        <div className="brief-section">
          <h2 className="brief-section__title">Companies</h2>
          <div className="brief-field-grid brief-field-grid--two">
            <TagField label="Target Companies" placeholder="Add a company…" {...tagList('companies.include', brief.companies.include, (b, v) => ({ ...b, companies: { ...b.companies, include: v } }))} />
            <TagField label="Exclude Companies" placeholder="Add a company…" {...tagList('companies.exclude', brief.companies.exclude, (b, v) => ({ ...b, companies: { ...b.companies, exclude: v } }))} />
          </div>
        </div>

        <div className="brief-section">
          <h2 className="brief-section__title">Industries</h2>
          <TagField label="Industries" placeholder="Add an industry…" {...tagList('industries', brief.industries, (b, v) => ({ ...b, industries: v }))} />
        </div>

        <div className="brief-section">
          <h2 className="brief-section__title">Education</h2>
          <TagField label="Education" placeholder="e.g. Bachelor's in Computer Science" {...tagList('education', brief.education, (b, v) => ({ ...b, education: v }))} />
        </div>

        <div className="brief-section">
          <h2 className="brief-section__title">Work Mode</h2>
          <div className="brief-segmented" role="group" aria-label="Work mode">
            {WORK_MODES.map((mode) => (
              <button
                key={mode.value}
                type="button"
                className={`brief-segmented__option${brief.location.workModes.includes(mode.value) ? ' is-active' : ''}`}
                onClick={() => toggleWorkMode(mode.value)}
              >
                {mode.label}
              </button>
            ))}
          </div>
        </div>

        <div className="brief-section">
          <h2 className="brief-section__title">Employment Type</h2>
          <div className="brief-segmented" role="group" aria-label="Employment type">
            {EMPLOYMENT_TYPES.map((type) => (
              <button
                key={type}
                type="button"
                className={`brief-segmented__option${brief.employmentTypes.includes(type) ? ' is-active' : ''}`}
                onClick={() => toggleEmploymentType(type)}
              >
                {type}
              </button>
            ))}
          </div>
        </div>
      </section>
    </>
  )

  if (variant === 'embedded') {
    return fields
  }

  return (
    <div className="workspace__grid">
      {fields}

      <aside className="workspace__preview" aria-label="Search summary">
        <p className="workspace__preview-label">Search Summary</p>

        <dl className="workspace__preview-list">
          <div className="workspace__preview-row">
            <dt>Role</dt>
            <dd className={brief.role.primaryTitle ? '' : 'workspace__preview-value--empty'}>
              {brief.role.primaryTitle || 'Not specified'}
              {brief.role.seniority ? ` · ${brief.role.seniority}` : ''}
              {brief.employmentTypes.length ? ` · ${brief.employmentTypes.join(', ')}` : ''}
            </dd>
          </div>
          <div className="workspace__preview-row">
            <dt>Location</dt>
            <dd className={summarizeLocations(brief) === 'Not specified' ? 'workspace__preview-value--empty' : ''}>
              {summarizeLocations(brief)}
              {brief.location.workModes.length ? ` · ${brief.location.workModes.map((m) => WORK_MODES.find((w) => w.value === m)?.label).join(', ')}` : ''}
            </dd>
          </div>
          <div className="workspace__preview-row">
            <dt>Experience</dt>
            <dd className={summarizeExperience(brief) === 'Not specified' ? 'workspace__preview-value--empty' : ''}>
              {summarizeExperience(brief)}
            </dd>
          </div>
          <div className="workspace__preview-row">
            <dt>Skills</dt>
            <dd className={summarizeSkills(brief.skills.required, brief.skills.preferred, brief.skills.excluded) === 'Not specified' ? 'workspace__preview-value--empty' : ''}>
              {summarizeSkills(brief.skills.required, brief.skills.preferred, brief.skills.excluded)}
            </dd>
          </div>
          <div className="workspace__preview-row">
            <dt>Companies</dt>
            <dd className={summarizeCompanies(brief.companies.include, brief.companies.exclude) === 'Not specified' ? 'workspace__preview-value--empty' : ''}>
              {summarizeCompanies(brief.companies.include, brief.companies.exclude)}
            </dd>
          </div>
        </dl>
      </aside>

      <div className="brief-actions">
        <button type="button" className="brief-back" onClick={onBackToJd}>
          <ArrowLeft size={15} aria-hidden="true" />
          {backLabel}
        </button>

        <div className="brief-find-slot">
          {searchState === 'error' ? (
            <div className="workspace__status workspace__status--error" role="alert">
              <p>Unable to reach the search provider.</p>
              <button type="button" className="workspace__retry" onClick={onFindCandidates}>
                Retry
              </button>
            </div>
          ) : null}

          <button
            type="button"
            className={`workspace__parse${isSearching ? ' workspace__parse--busy' : ''}`}
            onClick={onFindCandidates}
            disabled={isSearching}
          >
            {isSearching ? (
              <>
                <span className="workspace__spinner" aria-hidden="true" />
                <span>{submitBusyLabel}</span>
              </>
            ) : (
              <span>{submitLabel}</span>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
