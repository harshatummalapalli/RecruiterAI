import type { SearchIntent } from '../types'
import { arrayField } from '../services/recruiterWorkflow'
import { SectionCard } from './SectionCard'
import { TextAreaField, TextField } from './TextField'

type SearchBriefEditorProps = {
  intent: SearchIntent
  onChange: (updater: (current: SearchIntent) => SearchIntent) => void
  validationErrors: string[]
}

export function SearchBriefEditor({ intent, onChange, validationErrors }: SearchBriefEditorProps) {
  return (
    <div className="brief-editor">
      {validationErrors.length ? (
        <div className="validation-card" role="alert">
          <strong>Complete these before continuing:</strong>
          <ul>
            {validationErrors.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <SectionCard title="Role" description="Set the hiring target and employment context.">
        <div className="field-grid">
          <TextField label="Role title" value={intent.role.title ?? ''} onChange={(event) => onChange((current) => ({ ...current, role: { ...current.role, title: event.target.value } }))} placeholder="e.g. Software Engineer" />
          <TextField label="Seniority" value={intent.role.seniority ?? ''} onChange={(event) => onChange((current) => ({ ...current, role: { ...current.role, seniority: event.target.value } }))} placeholder="e.g. Senior" />
          <TextField label="Employment type" value={intent.role.employment_type ?? ''} onChange={(event) => onChange((current) => ({ ...current, role: { ...current.role, employment_type: event.target.value } }))} placeholder="e.g. Full-time" />
        </div>
      </SectionCard>

      <SectionCard title="Titles" description="Include or exclude job titles to shape the search.">
        <div className="field-grid">
          <TextAreaField label="Include titles" value={intent.titles.include_titles.join(', ')} onChange={(event) => onChange((current) => ({ ...current, titles: { ...current.titles, include_titles: arrayField(event.target.value) } }))} placeholder="Backend Engineer, Staff Engineer" rows={3} />
          <TextAreaField label="Exclude titles" value={intent.titles.exclude_titles.join(', ')} onChange={(event) => onChange((current) => ({ ...current, titles: { ...current.titles, exclude_titles: arrayField(event.target.value) } }))} placeholder="Manager, Director" rows={3} />
        </div>
      </SectionCard>

      <SectionCard title="Skills" description="Capture the required and preferred capabilities.">
        <div className="field-grid">
          <TextAreaField label="Required skills" value={intent.skills.required_skills.join(', ')} onChange={(event) => onChange((current) => ({ ...current, skills: { ...current.skills, required_skills: arrayField(event.target.value) } }))} placeholder="Python, FastAPI" rows={3} />
          <TextAreaField label="Preferred skills" value={intent.skills.preferred_skills.join(', ')} onChange={(event) => onChange((current) => ({ ...current, skills: { ...current.skills, preferred_skills: arrayField(event.target.value) } }))} placeholder="AWS, Postgres" rows={3} />
        </div>
      </SectionCard>

      <SectionCard title="Location" description="Tune the geography, work mode, and office expectations.">
        <div className="field-grid">
          <TextAreaField label="Countries" value={intent.location.countries.join(', ')} onChange={(event) => onChange((current) => ({ ...current, location: { ...current.location, countries: arrayField(event.target.value) } }))} placeholder="US, Canada" rows={3} />
          <TextAreaField label="Cities" value={intent.location.cities.join(', ')} onChange={(event) => onChange((current) => ({ ...current, location: { ...current.location, cities: arrayField(event.target.value) } }))} placeholder="New York, Seattle" rows={3} />
          <TextField label="Work mode" value={intent.location.work_mode ?? ''} onChange={(event) => onChange((current) => ({ ...current, location: { ...current.location, work_mode: event.target.value } }))} placeholder="hybrid" />
        </div>
      </SectionCard>

      <SectionCard title="Experience" description="Set minimum and maximum experience bands.">
        <div className="field-grid">
          <TextField label="Minimum years" type="number" value={intent.experience.minimum_years ?? ''} onChange={(event) => onChange((current) => ({ ...current, experience: { ...current.experience, minimum_years: event.target.value === '' ? null : Number(event.target.value) } }))} placeholder="5" />
          <TextField label="Maximum years" type="number" value={intent.experience.maximum_years ?? ''} onChange={(event) => onChange((current) => ({ ...current, experience: { ...current.experience, maximum_years: event.target.value === '' ? null : Number(event.target.value) } }))} placeholder="10" />
        </div>
      </SectionCard>

      <SectionCard title="AI focus" description="Signal which AI capabilities matter to the role.">
        <div className="check-grid">
          <label className="checkbox-row"><input type="checkbox" checked={intent.ai_focus.llm ?? false} onChange={(event) => onChange((current) => ({ ...current, ai_focus: { ...current.ai_focus, llm: event.target.checked } }))} /><span>LLM</span></label>
          <label className="checkbox-row"><input type="checkbox" checked={intent.ai_focus.rag ?? false} onChange={(event) => onChange((current) => ({ ...current, ai_focus: { ...current.ai_focus, rag: event.target.checked } }))} /><span>RAG</span></label>
          <label className="checkbox-row"><input type="checkbox" checked={intent.ai_focus.agentic_ai ?? false} onChange={(event) => onChange((current) => ({ ...current, ai_focus: { ...current.ai_focus, agentic_ai: event.target.checked } }))} /><span>Agentic AI</span></label>
          <label className="checkbox-row"><input type="checkbox" checked={intent.ai_focus.mcp ?? false} onChange={(event) => onChange((current) => ({ ...current, ai_focus: { ...current.ai_focus, mcp: event.target.checked } }))} /><span>MCP</span></label>
          <label className="checkbox-row"><input type="checkbox" checked={intent.ai_focus.semantic_kernel ?? false} onChange={(event) => onChange((current) => ({ ...current, ai_focus: { ...current.ai_focus, semantic_kernel: event.target.checked } }))} /><span>Semantic Kernel</span></label>
        </div>
      </SectionCard>

      <SectionCard title="Company preferences" description="Add exclusion and preference signals.">
        <div className="field-grid">
          <TextAreaField label="Exclude current companies" value={intent.company_preferences.exclude_current_companies.join(', ')} onChange={(event) => onChange((current) => ({ ...current, company_preferences: { ...current.company_preferences, exclude_current_companies: arrayField(event.target.value) } }))} placeholder="Google, Meta" rows={3} />
          <TextAreaField label="Preferred company types" value={intent.company_preferences.preferred_company_types.join(', ')} onChange={(event) => onChange((current) => ({ ...current, company_preferences: { ...current.company_preferences, preferred_company_types: arrayField(event.target.value) } }))} placeholder="startup, series-a" rows={3} />
        </div>
      </SectionCard>

      <SectionCard title="Ranking hints" description="Prioritize the strongest must-have and nice-to-have signals.">
        <div className="field-grid">
          <TextAreaField label="Must have" value={intent.ranking.must_have.join(', ')} onChange={(event) => onChange((current) => ({ ...current, ranking: { ...current.ranking, must_have: arrayField(event.target.value) } }))} placeholder="Python, distributed systems" rows={3} />
          <TextAreaField label="Nice to have" value={intent.ranking.nice_to_have.join(', ')} onChange={(event) => onChange((current) => ({ ...current, ranking: { ...current.ranking, nice_to_have: arrayField(event.target.value) } }))} placeholder="AWS, Kubernetes" rows={3} />
          <TextAreaField label="Bonus" value={intent.ranking.bonus.join(', ')} onChange={(event) => onChange((current) => ({ ...current, ranking: { ...current.ranking, bonus: arrayField(event.target.value) } }))} placeholder="Cloud-native, mentoring" rows={3} />
        </div>
      </SectionCard>
    </div>
  )
}
