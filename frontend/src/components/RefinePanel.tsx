import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { X } from 'lucide-react'
import type { IntakeResult } from '../models/intake'
import type { SearchBoundary, WorkMode } from '../models/searchBoundary'
import type { RefineDeltas } from '../services/recruiterWorkflow'
import type { SearchResponse } from '../types'
import './RefinePanel.css'

type Tier = 'core' | 'supporting' | 'differentiator'

const TIERS: Array<{ value: Tier; label: string }> = [
  { value: 'core', label: 'Core' },
  { value: 'supporting', label: 'Supporting' },
  { value: 'differentiator', label: 'Differentiator' },
]

const WORK_MODES: Array<{ value: WorkMode; label: string }> = [
  { value: 'onsite', label: 'Onsite' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'remote', label: 'Remote' },
]

type RequirementSeed = { text: string; tier: Tier }

// The requirements the recruiter can re-tier, read from the confirmed role
// understanding. Keyed by text — the same key the backend refine_model matches
// on — so a re-tier here lands on the right requirement.
function seedRequirements(intake: IntakeResult | null): RequirementSeed[] {
  if (!intake) return []
  const ru = intake.role_understanding
  const seen = new Set<string>()
  const out: RequirementSeed[] = []
  const take = (items: { value: string }[], tier: Tier) => {
    for (const item of items) {
      const text = item.value?.trim()
      if (!text || seen.has(text.toLowerCase())) continue
      seen.add(text.toLowerCase())
      out.push({ text, tier })
    }
  }
  take(ru.core_capabilities ?? [], 'core')
  take(ru.supporting_capabilities ?? [], 'supporting')
  take(ru.differentiators ?? [], 'differentiator')
  return out
}

// Capabilities the agent noticed but did not make requirements — the only
// source for "add a must-have". Suggestions only; there is no free-text box.
function seedSuggestions(intake: IntakeResult | null, existing: RequirementSeed[]): string[] {
  if (!intake) return []
  const known = new Set(existing.map((r) => r.text.toLowerCase()))
  const out: string[] = []
  for (const group of intake.role_understanding.technologies_mentioned ?? []) {
    for (const item of group.items ?? []) {
      const text = item?.trim()
      if (!text || known.has(text.toLowerCase())) continue
      known.add(text.toLowerCase())
      out.push(text)
    }
  }
  return out
}

/** A typed, structured tag field — chips the recruiter adds by typing a value
 * and pressing Enter. Not a free-text box: each entry is one structured value
 * (a company, a title, an industry), kept as its own removable chip. */
function TagField({
  id,
  label,
  hint,
  placeholder,
  values,
  onChange,
}: {
  id: string
  label: string
  hint?: string
  placeholder: string
  values: string[]
  onChange: (next: string[]) => void
}) {
  const [draft, setDraft] = useState('')
  const commit = () => {
    const value = draft.trim()
    if (!value) return
    if (!values.some((existing) => existing.toLowerCase() === value.toLowerCase())) {
      onChange([...values, value])
    }
    setDraft('')
  }
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault()
      commit()
    } else if (event.key === 'Backspace' && !draft && values.length) {
      onChange(values.slice(0, -1))
    }
  }
  return (
    <div className="refine-field">
      <label className="refine-field__label" htmlFor={id}>
        {label}
      </label>
      {hint ? <p className="refine-field__hint">{hint}</p> : null}
      <div className="refine-tags">
        {values.map((value) => (
          <span key={value} className="refine-tag">
            {value}
            <button type="button" className="refine-tag__remove" aria-label={`Remove ${value}`} onClick={() => onChange(values.filter((entry) => entry !== value))}>
              <X size={12} aria-hidden="true" />
            </button>
          </span>
        ))}
        <input
          id={id}
          type="text"
          className="refine-tags__input"
          placeholder={values.length ? '' : placeholder}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          onBlur={commit}
        />
      </div>
    </div>
  )
}

type Props = {
  onClose: () => void
  intakeResult: IntakeResult | null
  boundary: SearchBoundary | null
  // The result of the last pool-first refine, so the panel can show what changed
  // and, when the read profiles are exhausted, honestly name reaching wider.
  outcome: NonNullable<SearchResponse['refine_outcome']> | null
  busy: boolean
  onApply: (deltas: RefineDeltas) => void
}

export function RefinePanel({ onClose, intakeResult, boundary, outcome, busy, onApply }: Props) {
  const requirements = useMemo(() => seedRequirements(intakeResult), [intakeResult])
  const suggestions = useMemo(() => seedSuggestions(intakeResult, requirements), [intakeResult, requirements])

  // Everything starts at the confirmed value; a delta is only what the recruiter changes.
  const initialTiers = useMemo(() => {
    const map: Record<string, Tier> = {}
    for (const requirement of requirements) map[requirement.text] = requirement.tier
    return map
  }, [requirements])

  const [minYears, setMinYears] = useState<string>(boundary?.min_years != null ? String(boundary.min_years) : '')
  const [maxYears, setMaxYears] = useState<string>(boundary?.max_years != null ? String(boundary.max_years) : '')
  const [workMode, setWorkMode] = useState<WorkMode | ''>(boundary?.work_mode ?? '')
  const [cities, setCities] = useState<string[]>(() => boundary?.cities?.length ? boundary.cities : boundary?.city ? [boundary.city] : [])
  const [onlyCompanies, setOnlyCompanies] = useState<string[]>([])
  const [excludeCurrent, setExcludeCurrent] = useState<string[]>([])
  const [excludeEver, setExcludeEver] = useState<string[]>([])
  const [excludeTitles, setExcludeTitles] = useState<string[]>([])
  const [industries, setIndustries] = useState<string[]>([])
  const [tiers, setTiers] = useState<Record<string, Tier>>(initialTiers)
  const [added, setAdded] = useState<string[]>([])
  // The delta set the recruiter last pressed Apply on. Lets Apply re-disable once
  // applied, and re-enable only when something changes again.
  const [lastApplied, setLastApplied] = useState<string | null>(null)

  const dialogRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    dialogRef.current?.focus()
  }, [])
  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const country = boundary?.country?.trim() ?? ''

  const deltas = useMemo<RefineDeltas>(() => {
    const next: RefineDeltas = {}
    const min = minYears.trim() === '' ? null : Number(minYears)
    const max = maxYears.trim() === '' ? null : Number(maxYears)
    if (min != null && !Number.isNaN(min) && min !== (boundary?.min_years ?? null)) next.min_years = min
    if (max != null && !Number.isNaN(max) && max !== (boundary?.max_years ?? null)) next.max_years = max
    if (workMode && workMode !== (boundary?.work_mode ?? '')) next.work_mode = workMode
    const initialCities = boundary?.cities?.length ? boundary.cities : boundary?.city ? [boundary.city] : []
    if (cities.length && cities.join('|') !== initialCities.join('|')) next.location = { cities }
    if (onlyCompanies.length) next.only_companies = onlyCompanies
    if (excludeCurrent.length) next.exclude_companies_current = excludeCurrent
    if (excludeEver.length) next.exclude_companies_ever = excludeEver
    if (excludeTitles.length) next.exclude_titles = excludeTitles
    if (industries.length) next.industries = industries
    const retier: Record<string, string> = {}
    for (const [text, tier] of Object.entries(tiers)) {
      if (initialTiers[text] && initialTiers[text] !== tier) retier[text] = tier
    }
    if (Object.keys(retier).length) next.retier = retier
    if (added.length) next.add_requirements = added.map((text) => ({ text, tier: 'core', hard: true }))
    return next
  }, [minYears, maxYears, workMode, cities, onlyCompanies, excludeCurrent, excludeEver, excludeTitles, industries, tiers, added, initialTiers, boundary])

  const signature = useMemo(() => JSON.stringify(deltas), [deltas])
  // "Dirty" = there is a change not yet applied. After a successful Apply the
  // signature equals lastApplied, so Apply disables and the outcome banner is the
  // current truth; the moment the recruiter changes anything, it goes pending again.
  const dirty = Object.keys(deltas).length > 0 && signature !== lastApplied

  const apply = () => {
    setLastApplied(signature)
    onApply(deltas)
  }

  return (
    <div className="refine-overlay" role="presentation" onClick={onClose}>
      <div
        ref={dialogRef}
        className="refine-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Refine this search"
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="refine-dialog__head">
          <div>
            <h2 className="refine-dialog__title">Refine this search</h2>
            <p className="refine-dialog__lede">
              Tighten the brief and re-check the profiles already read. This is free — no new search, no credits.
            </p>
          </div>
          <button type="button" className="refine-dialog__close" aria-label="Close" onClick={onClose}>
            <X size={18} aria-hidden="true" />
          </button>
        </header>

        <div className="refine-dialog__body">
          <section className="refine-section">
            <h3 className="refine-section__title">Non-negotiables</h3>
            <div className="refine-grid">
              <div className="refine-field">
                <label className="refine-field__label" htmlFor="refine-min-years">Minimum years</label>
                <input
                  id="refine-min-years"
                  type="number"
                  min={0}
                  className="refine-number"
                  value={minYears}
                  onChange={(event) => setMinYears(event.target.value)}
                />
              </div>
              <div className="refine-field">
                <label className="refine-field__label" htmlFor="refine-max-years">Maximum years <span className="refine-field__opt">(optional)</span></label>
                <input
                  id="refine-max-years"
                  type="number"
                  min={0}
                  className="refine-number"
                  value={maxYears}
                  onChange={(event) => setMaxYears(event.target.value)}
                />
              </div>
            </div>
            <div className="refine-field">
              <span className="refine-field__label">Work mode</span>
              <div className="refine-segmented" role="group" aria-label="Work mode">
                {WORK_MODES.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    className={`refine-segment${workMode === option.value ? ' is-active' : ''}`}
                    aria-pressed={workMode === option.value}
                    onClick={() => setWorkMode((current) => (current === option.value ? '' : option.value))}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
            <TagField
              id="refine-cities"
              label="Cities"
              hint={country ? `Within ${country}. Type a city and press Enter.` : 'Type a city and press Enter.'}
              placeholder="Add a city…"
              values={cities}
              onChange={setCities}
            />
          </section>

          <section className="refine-section">
            <h3 className="refine-section__title">Companies</h3>
            <TagField
              id="refine-only-companies"
              label="Only from these companies"
              hint="Prefer candidates who have worked at any of these."
              placeholder="Add a company…"
              values={onlyCompanies}
              onChange={setOnlyCompanies}
            />
            <TagField
              id="refine-exclude-current"
              label="Exclude — currently there"
              placeholder="Add a company…"
              values={excludeCurrent}
              onChange={setExcludeCurrent}
            />
            <TagField
              id="refine-exclude-ever"
              label="Exclude — ever worked there"
              placeholder="Add a company…"
              values={excludeEver}
              onChange={setExcludeEver}
            />
          </section>

          <section className="refine-section">
            <h3 className="refine-section__title">Titles</h3>
            <TagField
              id="refine-exclude-titles"
              label="Exclude titles"
              hint="Drop profiles whose title contains any of these words."
              placeholder="Add a title…"
              values={excludeTitles}
              onChange={setExcludeTitles}
            />
          </section>

          <section className="refine-section">
            <h3 className="refine-section__title">More filters</h3>
            <TagField
              id="refine-industries"
              label="Industries"
              placeholder="Add an industry…"
              values={industries}
              onChange={setIndustries}
            />
          </section>

          {requirements.length ? (
            <section className="refine-section">
              <h3 className="refine-section__title">Qualifications</h3>
              <p className="refine-field__hint">Move a requirement between tiers to change how much it counts.</p>
              <ul className="refine-retier">
                {requirements.map((requirement) => (
                  <li key={requirement.text} className="refine-retier__row">
                    <span className="refine-retier__text">{requirement.text}</span>
                    <div className="refine-segmented refine-segmented--sm" role="group" aria-label={`Tier for ${requirement.text}`}>
                      {TIERS.map((tier) => (
                        <button
                          key={tier.value}
                          type="button"
                          className={`refine-segment${(tiers[requirement.text] ?? requirement.tier) === tier.value ? ' is-active' : ''}`}
                          aria-pressed={(tiers[requirement.text] ?? requirement.tier) === tier.value}
                          onClick={() => setTiers((current) => ({ ...current, [requirement.text]: tier.value }))}
                        >
                          {tier.label}
                        </button>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {suggestions.length ? (
            <section className="refine-section">
              <h3 className="refine-section__title">Add a must-have</h3>
              <p className="refine-field__hint">Promote something the role mentioned to a core requirement.</p>
              <div className="refine-suggestions">
                {suggestions.map((suggestion) => {
                  const chosen = added.includes(suggestion)
                  return (
                    <button
                      key={suggestion}
                      type="button"
                      className={`refine-suggestion${chosen ? ' is-chosen' : ''}`}
                      aria-pressed={chosen}
                      onClick={() =>
                        setAdded((current) => (chosen ? current.filter((entry) => entry !== suggestion) : [...current, suggestion]))
                      }
                    >
                      {chosen ? '✓ ' : '+ '}
                      {suggestion}
                    </button>
                  )
                })}
              </div>
            </section>
          ) : null}
        </div>

        <footer className="refine-dialog__foot">
          {!dirty && outcome ? (
            outcome.exhausted ? (
              <p className="refine-outcome refine-outcome--exhausted" role="status">
                None of the profiles already read match these tighter criteria. Finding new profiles would need a fresh
                search, which uses credits — that step is coming next.
              </p>
            ) : (
              <p className="refine-outcome" role="status">
                Re-checked the profiles already read: {outcome.shown} now shown
                {outcome.dropped ? `, ${outcome.dropped} no longer match` : ''}.
              </p>
            )
          ) : (
            <p className="refine-outcome refine-outcome--quiet">
              Changes re-check the profiles already read — free, no new search.
            </p>
          )}
          <div className="refine-foot__actions">
            <button type="button" className="refine-btn refine-btn--ghost" onClick={onClose}>
              Close
            </button>
            <button
              type="button"
              className="refine-btn refine-btn--primary"
              disabled={!dirty || busy}
              onClick={apply}
            >
              {busy ? 'Applying…' : 'Apply to profiles already read'}
            </button>
          </div>
        </footer>
      </div>
    </div>
  )
}
