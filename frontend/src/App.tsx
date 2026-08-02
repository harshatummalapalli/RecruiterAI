import { useMemo, useState } from 'react'
import type { Candidate, SearchIntent, SearchResponse } from './types'
import './App.css'

const API_BASE_URL = 'http://127.0.0.1:8000'

type BusyState = 'parsing' | 'searching' | 'exporting' | null

type Notice = {
  type: 'error' | 'success' | 'info'
  message: string
}

const defaultIntent: SearchIntent = {
  role: { title: 'Software Engineer', seniority: 'Senior', employment_type: 'Full-time' },
  location: { countries: ['US'], cities: ['New York'], work_mode: 'hybrid' },
  experience: { minimum_years: 5, maximum_years: 10 },
  titles: { include_titles: ['Backend Engineer'], exclude_titles: ['Manager'] },
  skills: { required_skills: ['Python', 'FastAPI'], preferred_skills: ['AWS', 'Postgres'] },
  previous_background: { preferred_technologies: ['Python'], preferred_companies: ['OpenAI'] },
  ai_focus: { llm: true, rag: true },
  company_preferences: { exclude_current_companies: ['Google'], preferred_company_types: ['startup'] },
  ranking: { must_have: ['Python'], nice_to_have: ['FastAPI'], bonus: ['Cloud'] },
}

const arrayField = (value: string) => value.split(',').map((item) => item.trim()).filter(Boolean)

function App() {
  const [jdText, setJdText] = useState('We are hiring a Senior Software Engineer with Python, FastAPI, AWS, and cloud-native experience for a hybrid role in New York.')
  const [intent, setIntent] = useState<SearchIntent>(defaultIntent)
  const [busyState, setBusyState] = useState<BusyState>(null)
  const [notice, setNotice] = useState<Notice | null>(null)
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null)
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null)
  const [hasParsed, setHasParsed] = useState(false)
  const [lastParsedJd, setLastParsedJd] = useState('')
  const [validationErrors, setValidationErrors] = useState<string[]>([])

  const parsedIntentSummary = useMemo(() => {
    return [
      intent.role.title ? `Role: ${intent.role.title}` : 'Role: —',
      intent.skills.required_skills.length ? `Skills: ${intent.skills.required_skills.join(', ')}` : 'Skills: —',
      intent.location.countries.length ? `Countries: ${intent.location.countries.join(', ')}` : 'Countries: —',
    ].join(' • ')
  }, [intent])

  const hasPendingParse = hasParsed && jdText.trim() !== lastParsedJd.trim()

  const validateIntent = (currentIntent: SearchIntent) => {
    const issues: string[] = []

    if (!currentIntent.role.title?.trim()) {
      issues.push('Add a role title before searching.')
    }

    if (!currentIntent.skills.required_skills.length && !currentIntent.skills.preferred_skills.length) {
      issues.push('Add at least one skill.')
    }

    if (!currentIntent.location.countries.length && !currentIntent.location.cities.length) {
      issues.push('Add at least one location or city.')
    }

    return issues
  }

  const updateIntent = (updater: (current: SearchIntent) => SearchIntent) => {
    setIntent((current) => {
      const next = updater(current)
      setValidationErrors(validateIntent(next))
      return next
    })
  }

  const serializeIntentForSearch = (currentIntent: SearchIntent) => {
    const sections = [] as string[]

    sections.push(`Role: ${currentIntent.role.title ?? '—'}`)
    if (currentIntent.role.seniority) sections.push(`Seniority: ${currentIntent.role.seniority}`)
    if (currentIntent.role.employment_type) sections.push(`Employment type: ${currentIntent.role.employment_type}`)

    if (currentIntent.titles.include_titles.length || currentIntent.titles.exclude_titles.length) {
      sections.push(`Titles: include ${currentIntent.titles.include_titles.join(', ') || '—'}; exclude ${currentIntent.titles.exclude_titles.join(', ') || '—'}`)
    }

    if (currentIntent.skills.required_skills.length || currentIntent.skills.preferred_skills.length) {
      sections.push(`Skills: required ${currentIntent.skills.required_skills.join(', ') || '—'}; preferred ${currentIntent.skills.preferred_skills.join(', ') || '—'}`)
    }

    if (currentIntent.location.countries.length || currentIntent.location.cities.length || currentIntent.location.work_mode) {
      sections.push(`Location: countries ${currentIntent.location.countries.join(', ') || '—'}; cities ${currentIntent.location.cities.join(', ') || '—'}; work mode ${currentIntent.location.work_mode || '—'}`)
    }

    if (currentIntent.experience.minimum_years != null || currentIntent.experience.maximum_years != null) {
      sections.push(`Experience: ${currentIntent.experience.minimum_years ?? '—'} to ${currentIntent.experience.maximum_years ?? '—'} years`)
    }

    const aiFocus = [
      currentIntent.ai_focus.llm ? 'llm' : null,
      currentIntent.ai_focus.rag ? 'rag' : null,
      currentIntent.ai_focus.agentic_ai ? 'agentic_ai' : null,
      currentIntent.ai_focus.mcp ? 'mcp' : null,
      currentIntent.ai_focus.semantic_kernel ? 'semantic_kernel' : null,
    ].filter(Boolean)
    if (aiFocus.length) {
      sections.push(`AI focus: ${aiFocus.join(', ')}`)
    }

    if (currentIntent.company_preferences.exclude_current_companies.length || currentIntent.company_preferences.preferred_company_types.length) {
      sections.push(`Company preferences: exclude ${currentIntent.company_preferences.exclude_current_companies.join(', ') || '—'}; prefer ${currentIntent.company_preferences.preferred_company_types.join(', ') || '—'}`)
    }

    if (currentIntent.ranking.must_have.length || currentIntent.ranking.nice_to_have.length || currentIntent.ranking.bonus.length) {
      sections.push(`Ranking hints: must have ${currentIntent.ranking.must_have.join(', ') || '—'}; nice to have ${currentIntent.ranking.nice_to_have.join(', ') || '—'}; bonus ${currentIntent.ranking.bonus.join(', ') || '—'}`)
    }

    return sections.join('\n')
  }

  const parseIntent = async () => {
    if (!jdText.trim()) {
      setNotice({ type: 'error', message: 'Paste a job description before parsing.' })
      setValidationErrors(['Paste a job description before parsing.'])
      return
    }

    setBusyState('parsing')
    setNotice(null)

    try {
      const response = await fetch(`${API_BASE_URL}/parse-jd`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jd_text: jdText }),
      })

      if (!response.ok) {
        throw new Error('Failed to parse JD')
      }

      const parsed = await response.json()
      setIntent(parsed)
      setHasParsed(true)
      setLastParsedJd(jdText)
      setValidationErrors(validateIntent(parsed))
      setNotice({ type: 'success', message: 'Search brief refreshed from the job description.' })
    } catch (err) {
      setNotice({ type: 'error', message: err instanceof Error ? err.message : 'Unable to parse JD' })
    } finally {
      setBusyState(null)
    }
  }

  const runSearch = async () => {
    const nextValidation = validateIntent(intent)
    setValidationErrors(nextValidation)

    if (!jdText.trim()) {
      setNotice({ type: 'error', message: 'Paste a job description before searching.' })
      return
    }

    if (nextValidation.length) {
      setNotice({ type: 'error', message: 'Complete the required sections before searching.' })
      return
    }

    setBusyState('searching')
    setNotice(null)
    setSearchResponse(null)
    setSelectedCandidate(null)

    try {
      if (!hasParsed || jdText.trim() !== lastParsedJd.trim()) {
        await parseIntent()
      }

      const response = await fetch(`${API_BASE_URL}/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          jd_text: serializeIntentForSearch(intent),
          provider: 'crustdata',
          page_size: 10,
          max_pages: 1,
          autocomplete: true,
        }),
      })

      if (!response.ok) {
        throw new Error('Search failed')
      }

      const payload = await response.json()
      setSearchResponse(payload)
      setSelectedCandidate(payload.candidates[0] ?? null)
      setNotice({ type: 'success', message: `Found ${payload.candidate_count ?? 0} candidates.` })
    } catch (err) {
      setNotice({ type: 'error', message: err instanceof Error ? err.message : 'Unable to run search' })
    } finally {
      setBusyState(null)
    }
  }

  const exportResults = async () => {
    const nextValidation = validateIntent(intent)
    setValidationErrors(nextValidation)

    if (!jdText.trim()) {
      setNotice({ type: 'error', message: 'Paste a job description before exporting.' })
      return
    }

    if (nextValidation.length) {
      setNotice({ type: 'error', message: 'Complete the required sections before exporting.' })
      return
    }

    setBusyState('exporting')
    setNotice(null)

    try {
      if (!hasParsed || jdText.trim() !== lastParsedJd.trim()) {
        await parseIntent()
      }

      const response = await fetch(`${API_BASE_URL}/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jd_text: serializeIntentForSearch(intent), provider: 'crustdata' }),
      })

      if (!response.ok) {
        throw new Error('Export failed')
      }

      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = 'recruiterai-results.xlsx'
      anchor.click()
      window.URL.revokeObjectURL(url)
      setNotice({ type: 'success', message: 'Export started successfully.' })
    } catch (err) {
      setNotice({ type: 'error', message: err instanceof Error ? err.message : 'Unable to export results' })
    } finally {
      setBusyState(null)
    }
  }

  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">RecruiterAI</p>
          <h1>Refine the search brief before you source candidates.</h1>
          <p className="hero-copy">Paste a job description, review and edit the parsed SearchIntent, then run a CrustData search from the refined brief.</p>
        </div>
      </header>

      <main className="grid">
        <section className="panel">
          <h2>1. Paste job description</h2>
          <textarea value={jdText} onChange={(event) => { setJdText(event.target.value); setNotice(null); }} rows={8} placeholder="Paste the job description here…" />
          <div className="actions">
            <button onClick={parseIntent} disabled={busyState === 'parsing'}>{busyState === 'parsing' ? 'Parsing…' : 'Parse JD'}</button>
            <button className="secondary" onClick={runSearch} disabled={busyState === 'searching'}>{busyState === 'searching' ? 'Searching…' : 'Search Candidates'}</button>
            <button className="secondary" onClick={exportResults} disabled={busyState === 'exporting'}>{busyState === 'exporting' ? 'Exporting…' : 'Export'}</button>
          </div>
          {notice ? <p className={`status ${notice.type}`}>{notice.message}</p> : null}
          {busyState ? <p className="muted">Working on your request…</p> : null}
        </section>

        <section className="panel wide">
          <h2>2. Edit search intent</h2>
          <div className="section-header">
            <p className="muted">{parsedIntentSummary}</p>
            {hasPendingParse ? <span className="pill">Needs refresh</span> : null}
          </div>
          {validationErrors.length ? (
            <div className="validation-card">
              <strong>Complete these before continuing:</strong>
              <ul>
                {validationErrors.map((message) => (
                  <li key={message}>{message}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className="intent-sections">
            <div className="intent-card">
              <h3>Role</h3>
              <div className="intent-grid">
                <label>
                  <span>Role title</span>
                  <input value={intent.role.title ?? ''} onChange={(event) => updateIntent((current) => ({ ...current, role: { ...current.role, title: event.target.value } }))} placeholder="e.g. Software Engineer" />
                </label>
                <label>
                  <span>Seniority</span>
                  <input value={intent.role.seniority ?? ''} onChange={(event) => updateIntent((current) => ({ ...current, role: { ...current.role, seniority: event.target.value } }))} placeholder="e.g. Senior" />
                </label>
                <label>
                  <span>Employment type</span>
                  <input value={intent.role.employment_type ?? ''} onChange={(event) => updateIntent((current) => ({ ...current, role: { ...current.role, employment_type: event.target.value } }))} placeholder="e.g. Full-time" />
                </label>
              </div>
            </div>

            <div className="intent-card">
              <h3>Titles</h3>
              <div className="intent-grid">
                <label>
                  <span>Include titles</span>
                  <textarea rows={3} value={intent.titles.include_titles.join(', ')} onChange={(event) => updateIntent((current) => ({ ...current, titles: { ...current.titles, include_titles: arrayField(event.target.value) } }))} placeholder="Backend Engineer, Staff Engineer" />
                </label>
                <label>
                  <span>Exclude titles</span>
                  <textarea rows={3} value={intent.titles.exclude_titles.join(', ')} onChange={(event) => updateIntent((current) => ({ ...current, titles: { ...current.titles, exclude_titles: arrayField(event.target.value) } }))} placeholder="Manager, Director" />
                </label>
              </div>
            </div>

            <div className="intent-card">
              <h3>Skills</h3>
              <div className="intent-grid">
                <label>
                  <span>Required skills</span>
                  <textarea rows={3} value={intent.skills.required_skills.join(', ')} onChange={(event) => updateIntent((current) => ({ ...current, skills: { ...current.skills, required_skills: arrayField(event.target.value) } }))} placeholder="Python, FastAPI" />
                </label>
                <label>
                  <span>Preferred skills</span>
                  <textarea rows={3} value={intent.skills.preferred_skills.join(', ')} onChange={(event) => updateIntent((current) => ({ ...current, skills: { ...current.skills, preferred_skills: arrayField(event.target.value) } }))} placeholder="AWS, Postgres" />
                </label>
              </div>
            </div>

            <div className="intent-card">
              <h3>Location</h3>
              <div className="intent-grid">
                <label>
                  <span>Countries</span>
                  <textarea rows={3} value={intent.location.countries.join(', ')} onChange={(event) => updateIntent((current) => ({ ...current, location: { ...current.location, countries: arrayField(event.target.value) } }))} placeholder="US, Canada" />
                </label>
                <label>
                  <span>Cities</span>
                  <textarea rows={3} value={intent.location.cities.join(', ')} onChange={(event) => updateIntent((current) => ({ ...current, location: { ...current.location, cities: arrayField(event.target.value) } }))} placeholder="New York, Seattle" />
                </label>
                <label>
                  <span>Work mode</span>
                  <input value={intent.location.work_mode ?? ''} onChange={(event) => updateIntent((current) => ({ ...current, location: { ...current.location, work_mode: event.target.value } }))} placeholder="hybrid" />
                </label>
              </div>
            </div>

            <div className="intent-card">
              <h3>Experience</h3>
              <div className="intent-grid">
                <label>
                  <span>Minimum years</span>
                  <input type="number" value={intent.experience.minimum_years ?? ''} onChange={(event) => updateIntent((current) => ({ ...current, experience: { ...current.experience, minimum_years: event.target.value === '' ? null : Number(event.target.value) } }))} placeholder="5" />
                </label>
                <label>
                  <span>Maximum years</span>
                  <input type="number" value={intent.experience.maximum_years ?? ''} onChange={(event) => updateIntent((current) => ({ ...current, experience: { ...current.experience, maximum_years: event.target.value === '' ? null : Number(event.target.value) } }))} placeholder="10" />
                </label>
              </div>
            </div>

            <div className="intent-card">
              <h3>AI focus</h3>
              <div className="check-grid">
                <label className="checkbox-row">
                  <input type="checkbox" checked={intent.ai_focus.llm ?? false} onChange={(event) => updateIntent((current) => ({ ...current, ai_focus: { ...current.ai_focus, llm: event.target.checked } }))} />
                  <span>LLM</span>
                </label>
                <label className="checkbox-row">
                  <input type="checkbox" checked={intent.ai_focus.rag ?? false} onChange={(event) => updateIntent((current) => ({ ...current, ai_focus: { ...current.ai_focus, rag: event.target.checked } }))} />
                  <span>RAG</span>
                </label>
                <label className="checkbox-row">
                  <input type="checkbox" checked={intent.ai_focus.agentic_ai ?? false} onChange={(event) => updateIntent((current) => ({ ...current, ai_focus: { ...current.ai_focus, agentic_ai: event.target.checked } }))} />
                  <span>Agentic AI</span>
                </label>
                <label className="checkbox-row">
                  <input type="checkbox" checked={intent.ai_focus.mcp ?? false} onChange={(event) => updateIntent((current) => ({ ...current, ai_focus: { ...current.ai_focus, mcp: event.target.checked } }))} />
                  <span>MCP</span>
                </label>
                <label className="checkbox-row">
                  <input type="checkbox" checked={intent.ai_focus.semantic_kernel ?? false} onChange={(event) => updateIntent((current) => ({ ...current, ai_focus: { ...current.ai_focus, semantic_kernel: event.target.checked } }))} />
                  <span>Semantic Kernel</span>
                </label>
              </div>
            </div>

            <div className="intent-card">
              <h3>Company preferences</h3>
              <div className="intent-grid">
                <label>
                  <span>Exclude current companies</span>
                  <textarea rows={3} value={intent.company_preferences.exclude_current_companies.join(', ')} onChange={(event) => updateIntent((current) => ({ ...current, company_preferences: { ...current.company_preferences, exclude_current_companies: arrayField(event.target.value) } }))} placeholder="Google, Meta" />
                </label>
                <label>
                  <span>Preferred company types</span>
                  <textarea rows={3} value={intent.company_preferences.preferred_company_types.join(', ')} onChange={(event) => updateIntent((current) => ({ ...current, company_preferences: { ...current.company_preferences, preferred_company_types: arrayField(event.target.value) } }))} placeholder="startup, series-a" />
                </label>
              </div>
            </div>

            <div className="intent-card">
              <h3>Ranking hints</h3>
              <div className="intent-grid">
                <label>
                  <span>Must have</span>
                  <textarea rows={3} value={intent.ranking.must_have.join(', ')} onChange={(event) => updateIntent((current) => ({ ...current, ranking: { ...current.ranking, must_have: arrayField(event.target.value) } }))} placeholder="Python, distributed systems" />
                </label>
                <label>
                  <span>Nice to have</span>
                  <textarea rows={3} value={intent.ranking.nice_to_have.join(', ')} onChange={(event) => updateIntent((current) => ({ ...current, ranking: { ...current.ranking, nice_to_have: arrayField(event.target.value) } }))} placeholder="AWS, Kubernetes" />
                </label>
                <label>
                  <span>Bonus</span>
                  <textarea rows={3} value={intent.ranking.bonus.join(', ')} onChange={(event) => updateIntent((current) => ({ ...current, ranking: { ...current.ranking, bonus: arrayField(event.target.value) } }))} placeholder="Cloud-native, mentoring" />
                </label>
              </div>
            </div>
          </div>
        </section>

        <section className="panel wide">
          <h2>3. Ranked candidates</h2>
          {searchResponse ? (
            <>
              {searchResponse.candidates.length ? (
                <div className="candidate-list">
                  {searchResponse.candidates.map((candidate, index) => (
                    <button key={index} className="candidate-card" onClick={() => setSelectedCandidate(candidate)}>
                      <strong>{String(candidate.name ?? 'Candidate')}</strong>
                      <span>{String(candidate.title ?? '—')}</span>
                      <small>{String(candidate.company ?? '—')}</small>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="empty-state">
                  <h3>No candidates matched this brief.</h3>
                  <p className="muted">Try widening the location, skills, or ranking hints and search again.</p>
                </div>
              )}
              <div className="candidate-details">
                {selectedCandidate ? (
                  <>
                    <h3>{String(selectedCandidate.name ?? 'Candidate')}</h3>
                    <p>{String(selectedCandidate.title ?? '—')}</p>
                    <p>{String(selectedCandidate.company ?? '—')}</p>
                    <p>{String(selectedCandidate.location ?? '—')}</p>
                    <div className="meta-row">
                      <span>Provider score: {selectedCandidate.provider_score ?? '—'}</span>
                      <span>Final score: {selectedCandidate.final_score ?? '—'}</span>
                    </div>
                    <pre>{JSON.stringify(selectedCandidate.raw_data ?? {}, null, 2)}</pre>
                  </>
                ) : searchResponse.candidates.length ? (
                  <p className="muted">Select a candidate to review the profile details.</p>
                ) : null}
              </div>
            </>
          ) : (
            <div className="empty-state">
              <h3>Ready to source.</h3>
              <p className="muted">Search candidates once your brief is complete to see ranked results here.</p>
            </div>
          )}
        </section>
      </main>
    </div>
  )
}

export default App
