import type { ChangeEvent } from 'react'
import { TagField } from './TagField'
import type { EmploymentType, SearchBrief } from '../models/searchBrief'
import type { LocationEntry } from '../screens/localJdExtraction'

type FieldChange = (path: string, updater: (current: SearchBrief) => SearchBrief) => void

// The editable part of the Search Brief. Everything the Search Boundary owns (where, work mode, hiring company) is
// deliberately NOT here: the boundary is the single authoritative source for those. The Living Brief
// (LivingBrief.tsx) shows the reading and asks the questions; this is the "Adjust before searching" panel.
type SearchBriefReviewProps = {
  brief: SearchBrief
  onChange: FieldChange
}

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

export function SearchBriefReview({ brief, onChange }: SearchBriefReviewProps) {
  const scalarInput = (path: string, value: string, apply: (b: SearchBrief, v: string) => SearchBrief) => ({
    value,
    onChange: (event: ChangeEvent<HTMLInputElement>) => onChange(path, (current) => apply(current, event.target.value)),
  })

  const tagList = (path: string, values: string[], apply: (b: SearchBrief, v: string[]) => SearchBrief) => ({
    values,
    onChange: (next: string[]) => onChange(path, (current) => apply(current, next)),
  })

  const toggleEmploymentType = (type: EmploymentType) => {
    onChange('employmentTypes', (current) => ({
      ...current,
      employmentTypes: current.employmentTypes.includes(type)
        ? current.employmentTypes.filter((t) => t !== type)
        : [...current.employmentTypes, type],
    }))
  }

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
            label="Excluded Titles"
            placeholder="Add a title to exclude…"
            {...tagList('role.excludedTitles', brief.role.excludedTitles, (b, v) => ({ ...b, role: { ...b.role, excludedTitles: v } }))}
          />
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
          <h2 className="brief-section__title">Must-have capabilities</h2>
          <p className="brief-field__hint">
            These are the only capability terms matched as a <strong>hard filter</strong>. Everything
            else from the brief (the requirement sentences, seniority, preferred skills) guides ranking,
            not a yes/no filter — so keep this list short and precise, or it narrows the pool fast.
          </p>

          {(brief.mustHaveKeywordGroups?.[0]?.length ?? 0) > 0 && (
            <div className="brief-recommendation">
              <TagField
                label="Role-defining capability — recommended, required"
                placeholder="Add or remove a spelling…"
                {...tagList(
                  'mustHaveKeywordGroups.0',
                  brief.mustHaveKeywordGroups?.[0] ?? [],
                  (b, v) => ({ ...b, mustHaveKeywordGroups: v.length ? [v] : [] }),
                )}
              />
              <p className="brief-field__hint">
                This role is defined by this capability, so I&rsquo;ll require candidates to show
                evidence of <strong>any one</strong> of these terms — that keeps the shortlist on
                genuine matches instead of look-alikes who only share the base title. Clear all the
                tags to turn this off and widen the search.
              </p>
            </div>
          )}

          <TagField
            label="Must-have keywords (enforced)"
            placeholder="e.g. Java, .NET, RAG — matched precisely, not just ranked"
            {...tagList('mustHaveKeywords', brief.mustHaveKeywords ?? [], (b, v) => ({ ...b, mustHaveKeywords: v }))}
          />
        </div>

        <div className="brief-section">
          <h2 className="brief-section__title">Companies</h2>
          <div className="brief-field-grid brief-field-grid--two">
            <TagField label="Target Companies" placeholder="Add a company…" {...tagList('companies.include', brief.companies.include, (b, v) => ({ ...b, companies: { ...b.companies, include: v } }))} />
            <TagField label="Exclude Companies" placeholder="Add a company…" {...tagList('companies.exclude', brief.companies.exclude, (b, v) => ({ ...b, companies: { ...b.companies, exclude: v } }))} />
          </div>
          <p className="brief-field__hint">The two above match a candidate's <strong>current</strong> employer. Use the pair below to match anyone who has <strong>ever</strong> worked there.</p>
          <div className="brief-field-grid brief-field-grid--two">
            <TagField label="Target — ever worked there" placeholder="Add a company…" {...tagList('companies.includeEver', brief.companies.includeEver ?? [], (b, v) => ({ ...b, companies: { ...b.companies, includeEver: v } }))} />
            <TagField label="Exclude — ever worked there" placeholder="Add a company…" {...tagList('companies.excludeEver', brief.companies.excludeEver ?? [], (b, v) => ({ ...b, companies: { ...b.companies, excludeEver: v } }))} />
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

  return fields
}
