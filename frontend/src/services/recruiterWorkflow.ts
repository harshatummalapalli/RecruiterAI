import type { SearchIntent, SearchResponse } from '../types'
import type { ConfirmationEdits, ConfirmationResponse, IntakeSessionResponse, IntakeStartResponse } from '../models/intake'
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

/** Starts a search from a CONFIRMED brief. The server builds the executable search from the confirmation it stored;
 * the browser sends no intent, no location and no requirements of its own. */
export const runCandidateSearch = async (
  confirmationId: string,
  options?: { searchId?: string; debug?: boolean },
) => {
  const response = await fetch(`${API_BASE_URL}/search`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      // Required by the request schema; the server runs the confirmed brief and ignores this.
      jd_text: '',
      confirmation_id: confirmationId,
      provider: 'crustdata',
      // Retrieval sizing is backend-owned; the recruiter just requests a search.
      autocomplete: true,
      search_id: options?.searchId,
      debug: options?.debug ?? false,
    }),
  })

  if (!response.ok) {
    throw new Error('Search failed')
  }

  return response.json() as Promise<SearchResponse>
}

/** A request the server refused for reasons the recruiter can act on (an incomplete boundary, a brief that still has
 * open questions). `messages` are plain sentences, safe to show as they are. */
export class IntakeRequestError extends Error {
  messages: string[]

  constructor(fallback: string, messages: string[] = []) {
    super(messages[0] ?? fallback)
    this.messages = messages.length ? messages : [fallback]
  }
}

async function readRefusal(response: Response, fallback: string): Promise<IntakeRequestError> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    const detail = body.detail as { errors?: string[]; reasons?: string[] } | string | undefined
    if (detail && typeof detail === 'object') {
      const messages = detail.errors ?? detail.reasons ?? []
      if (messages.length) return new IntakeRequestError(fallback, messages)
    }
    if (typeof detail === 'string' && detail) return new IntakeRequestError(fallback, [detail])
  } catch {
    // fall through to the generic message
  }
  return new IntakeRequestError(fallback)
}

export const startIntake = async (rawInput: string, boundary: SearchBoundary, postedTitle?: string): Promise<IntakeStartResponse> => {
  const response = await fetch(`${API_BASE_URL}/intake/start`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ raw_input: rawInput, boundary, posted_title: postedTitle?.trim() ? postedTitle.trim() : null }),
  })
  if (!response.ok) {
    throw await readRefusal(response, 'Failed to understand this role')
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

/** Resume a brief after a reload. Read only; no model call. */
export const loadIntakeSession = async (sessionId: string): Promise<IntakeSessionResponse | null> => {
  const response = await fetch(`${API_BASE_URL}/intake/${encodeURIComponent(sessionId)}`, { credentials: 'include' })
  if (response.status === 404) return null
  if (!response.ok) throw new Error('Failed to reload the brief')
  return response.json() as Promise<IntakeSessionResponse>
}

/** Editing the Search Boundary is deterministic: validated and re-applied on the server with no model call. */
export const updateIntakeBoundary = async (sessionId: string, boundary: SearchBoundary): Promise<IntakeStartResponse> => {
  const response = await fetch(`${API_BASE_URL}/intake/${encodeURIComponent(sessionId)}/boundary`, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(boundary),
  })
  if (!response.ok) {
    throw await readRefusal(response, 'The search boundary could not be updated.')
  }
  return response.json() as Promise<IntakeStartResponse>
}

/** The recruiter presses Search: the server checks the gate, builds the executable intent, applies the edits and
 * stores an immutable snapshot. The returned id is the ONLY thing /search accepts. */
export const createConfirmation = async (sessionId: string, edits: ConfirmationEdits): Promise<ConfirmationResponse> => {
  const response = await fetch(`${API_BASE_URL}/intake/${encodeURIComponent(sessionId)}/confirmations`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ edits }),
  })
  if (!response.ok) {
    throw await readRefusal(response, 'This brief is not ready to search.')
  }
  return response.json() as Promise<ConfirmationResponse>
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

export const setWorkspaceArranged = async (searchId: string, arranged: boolean): Promise<void> => {
  const response = await fetch(`${API_BASE_URL}/search/${encodeURIComponent(searchId)}/workspace`, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ arranged }),
  })
  if (!response.ok) {
    throw new Error('Failed to save workspace state')
  }
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

