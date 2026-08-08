import type { Candidate, SearchIntent, SearchResponse } from '../types'
import type { LocationDetail } from '../models/searchBrief'

export type RecruiterAction = 'shortlist' | 'reject' | 'note' | 'export' | 'view'

export const API_BASE_URL = 'http://127.0.0.1:8000'

export type BusyState = 'parsing' | 'searching' | 'exporting' | null
export type NoticeType = 'error' | 'success' | 'info'

export type Notice = {
  type: NoticeType
  message: string
}

export type SearchSummary = {
  candidateCount: number
  averageMatch: string
  highestMatch: string
  topLocations: string[]
  topCompanies: string[]
  searchDuration: string
  searchConfidence: string
  lastUpdated: string
  demo: boolean
}

export const defaultIntent: SearchIntent = {
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

export const arrayField = (value: string) => value.split(',').map((item) => item.trim()).filter(Boolean)

export const buildParsedIntentSummary = (intent: SearchIntent) => {
  return [
    intent.role.title ? `Role: ${intent.role.title}` : 'Role: —',
    intent.skills.required_skills.length ? `Skills: ${intent.skills.required_skills.join(', ')}` : 'Skills: —',
    intent.location.countries.length ? `Countries: ${intent.location.countries.join(', ')}` : 'Countries: —',
  ].join(' • ')
}

export const validateIntent = (currentIntent: SearchIntent) => {
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

export const serializeIntentForSearch = (currentIntent: SearchIntent) => {
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

export const getCandidateKey = (candidate: Candidate) => {
  const parts = [candidate.name, candidate.title, candidate.company, candidate.location]
  return parts.filter(Boolean).join('|') || `${candidate.provider_score ?? ''}-${candidate.final_score ?? ''}`
}

export const getProviderAvailability = async () => {
  try {
    const response = await fetch(`${API_BASE_URL}/providers`)
    if (!response.ok) {
      return { available: false, message: 'Sourcing has not yet been configured.' }
    }

    const payload = await response.json() as { providers?: string[] }
    return { available: (payload.providers?.length ?? 0) > 0, message: (payload.providers?.length ?? 0) > 0 ? 'Sourcing is ready.' : 'Sourcing has not yet been configured.' }
  } catch {
    return { available: false, message: 'Sourcing has not yet been configured.' }
  }
}

const toPercent = (value: number) => {
  const normalized = value > 1 ? value : value * 100
  return `${Math.round(normalized)}%`
}

export const buildSearchSummary = (payload: SearchResponse): SearchSummary => {
  const candidates = payload.candidates ?? []
  const scores = candidates
    .map((candidate) => Number(candidate.final_score ?? candidate.provider_score ?? 0))
    .filter((score) => Number.isFinite(score))

  const averageMatch = scores.length ? toPercent(scores.reduce((sum, value) => sum + value, 0) / scores.length) : '0%'
  const highestMatch = scores.length ? toPercent(Math.max(...scores)) : '0%'
  const locationCounts = candidates.reduce<Record<string, number>>((accumulator, candidate) => {
    const location = candidate.location?.trim() || 'Unspecified'
    accumulator[location] = (accumulator[location] ?? 0) + 1
    return accumulator
  }, {})
  const companyCounts = candidates.reduce<Record<string, number>>((accumulator, candidate) => {
    const company = candidate.company?.trim() || 'Unspecified'
    accumulator[company] = (accumulator[company] ?? 0) + 1
    return accumulator
  }, {})

  return {
    candidateCount: payload.candidate_count ?? candidates.length,
    averageMatch,
    highestMatch,
    topLocations: Object.entries(locationCounts).sort((left, right) => right[1] - left[1]).slice(0, 3).map(([location]) => location),
    topCompanies: Object.entries(companyCounts).sort((left, right) => right[1] - left[1]).slice(0, 3).map(([company]) => company),
    searchDuration: '0.8s',
    searchConfidence: payload.demo ? 'Demo' : 'High',
    lastUpdated: new Date().toLocaleString(),
    demo: Boolean(payload.demo),
  }
}

export const parseJobDescription = async (jdText: string) => {
  const response = await fetch(`${API_BASE_URL}/parse-jd`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jd_text: jdText }),
  })

  if (!response.ok) {
    throw new Error('Failed to parse JD')
  }

  return response.json() as Promise<SearchIntent>
}

export const runCandidateSearch = async (
  _jdText: string,
  intent: SearchIntent,
  location?: LocationDetail,
  options?: { searchId?: string; debug?: boolean },
) => {
  const response = await fetch(`${API_BASE_URL}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      jd_text: serializeIntentForSearch(intent),
      provider: 'crustdata',
      page_size: 10,
      max_pages: 1,
      autocomplete: true,
      location,
      search_id: options?.searchId,
      debug: options?.debug ?? false,
    }),
  })

  if (!response.ok) {
    throw new Error('Search failed')
  }

  return response.json() as Promise<SearchResponse>
}

export const loadPersistedSearch = async (searchId: string): Promise<SearchResponse | null> => {
  const response = await fetch(`${API_BASE_URL}/search/${encodeURIComponent(searchId)}`)
  if (response.status === 404) {
    return null
  }
  if (!response.ok) {
    throw new Error('Failed to reload search')
  }
  return response.json() as Promise<SearchResponse>
}

export const updateCandidateRecord = async (
  searchId: string,
  candidateId: string,
  update: { decision?: string; note?: string },
): Promise<{ recruiter_decisions: Record<string, string>; notes: Record<string, Array<{ text: string; created_at: string }>> }> => {
  const response = await fetch(`${API_BASE_URL}/search/${encodeURIComponent(searchId)}/candidate`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidate_id: candidateId, ...update }),
  })
  if (!response.ok) {
    throw new Error('Failed to save candidate update')
  }
  return response.json()
}

export const exportCandidateResults = async (_jdText: string, intent: SearchIntent) => {
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
}

export const downloadCandidateExport = (candidate: Candidate) => {
  const payload = {
    candidate: {
      name: candidate.name,
      title: candidate.title,
      company: candidate.company,
      location: candidate.location,
      match: candidate.final_score ?? candidate.provider_score,
      summary: candidate.summary,
      uploadedAt: new Date().toISOString(),
    },
  }
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${(candidate.name ?? 'candidate').toLowerCase().replace(/\s+/g, '-')}-export.json`
  anchor.click()
  window.URL.revokeObjectURL(url)
}
