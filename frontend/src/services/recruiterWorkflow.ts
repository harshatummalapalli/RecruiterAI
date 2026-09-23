import type { SearchIntent, SearchResponse } from '../types'
import type { LocationDetail } from '../models/searchBrief'
import type { IntakeStartResponse } from '../models/intake'
import type { SearchBoundary } from '../models/searchBoundary'

// Empty string means "same origin as the page" — used in production where
// nginx serves the frontend and proxies the API from one origin. Local dev
// keeps talking to the backend directly on :8000 unless overridden.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

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

export const checkSession = async (): Promise<boolean> => {
  try {
    const response = await fetch(`${API_BASE_URL}/auth/me`, { credentials: 'include' })
    return response.ok
  } catch {
    return false
  }
}

export const logout = async (): Promise<void> => {
  await fetch(`${API_BASE_URL}/auth/logout`, { method: 'POST', credentials: 'include' })
}

export const parseJobDescription = async (jdText: string) => {
  const response = await fetch(`${API_BASE_URL}/parse-jd`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jd_text: jdText }),
  })

  if (!response.ok) {
    throw new Error('Failed to parse JD')
  }

  return response.json() as Promise<SearchIntent>
}

export const runCandidateSearch = async (
  jdText: string,
  intent: SearchIntent,
  location?: LocationDetail,
  options?: { searchId?: string; debug?: boolean },
) => {
  const response = await fetch(`${API_BASE_URL}/search`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      // jd_text is kept only as a human-readable record for display/storage.
      // `intent` is the recruiter-edited Search Brief and is authoritative —
      // the backend uses it directly and does not re-parse jd_text through
      // the LLM when it's present.
      jd_text: jdText.trim() ? jdText : serializeIntentForSearch(intent),
      intent,
      provider: 'crustdata',
      // Retrieval sizing (page_size/max_pages) is backend-owned (Phase 3,
      // DISCOVERY_PAGE_SIZE/DISCOVERY_MAX_PAGES in backend/config.py) — the
      // recruiter just requests a search; the frontend deliberately never
      // sends these.
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

export const startIntake = async (rawInput: string, boundary?: SearchBoundary): Promise<IntakeStartResponse> => {
  const response = await fetch(`${API_BASE_URL}/intake/start`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ raw_input: rawInput, boundary: boundary ?? null }),
  })
  if (!response.ok) {
    throw new Error('Failed to understand this role')
  }
  return response.json() as Promise<IntakeStartResponse>
}

export const answerIntake = async (
  sessionId: string,
  issueId: string,
  value: string,
  label: string,
): Promise<IntakeStartResponse> => {
  const response = await fetch(`${API_BASE_URL}/intake/${encodeURIComponent(sessionId)}/answer`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ issue_id: issueId, value, label }),
  })
  if (!response.ok) {
    throw new Error('Failed to update the brief')
  }
  return response.json() as Promise<IntakeStartResponse>
}

export const confirmIntake = async (sessionId: string): Promise<SearchIntent> => {
  const response = await fetch(`${API_BASE_URL}/intake/${encodeURIComponent(sessionId)}/confirm`, {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error('This role still has an unresolved decision.')
  }
  return response.json() as Promise<SearchIntent>
}

export const loadPersistedSearch = async (searchId: string): Promise<SearchResponse | null> => {
  const response = await fetch(`${API_BASE_URL}/search/${encodeURIComponent(searchId)}`, { credentials: 'include' })
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
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidate_id: candidateId, ...update }),
  })
  if (!response.ok) {
    throw new Error('Failed to save candidate update')
  }
  return response.json()
}

