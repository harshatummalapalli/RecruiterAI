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
