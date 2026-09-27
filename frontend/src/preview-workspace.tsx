// Local-only preview of the multi-search workspace (roles, first five, feedback, calibration, Show me more, pause).
// Not part of the app or the production build (vite builds index.html only). It renders the REAL screens against a tiny
// in-browser stand-in for the backend, seeded from the saved search in src/preview-data/response.json (run
// `python -m backend.experiments.record_preview <saved search>` first) and the saved intake fixtures. No login, no
// backend, no network. Open /preview-workspace.html?scenario=review (see SCENARIOS below).
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { RecruiterWorkspaceScreen } from './screens/RecruiterWorkspaceScreen'
import { buildDiscoveryCandidates } from './models/discovery'
import { sectionOf } from './models/workspace'
import type { SearchIntent, SearchListItem, SearchResponse } from './types'

const base = Object.values(import.meta.glob('./preview-data/response.json', { eager: true }))[0] as { default: SearchResponse } | undefined
const intakes = Object.entries(import.meta.glob('./preview-data/intake-*.json', { eager: true })).sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true })).map(([, module]) => (module as { default: any }).default)

if (!base || intakes.length < 2) {
  document.body.innerHTML = '<p style="font:15px sans-serif;padding:24px">No preview data yet. Run the record_preview and intake_preview commands (see the top of this file).</p>'
  throw new Error('no preview data')
}

const scenario = new URLSearchParams(window.location.search).get('scenario') ?? 'compose'
const RESPONSE = base.default

type Sim = { response: SearchResponse; sessionId: string; startedAt?: number; final?: SearchResponse; initialIds: string[] }
const roles = new Map<string, Sim>()

const LEVEL_OF: Record<string, number> = { start: 0, worth: 1, unchecked: 2, thin: 3 }

function levelOrder(response: SearchResponse): string[] {
  const candidates = buildDiscoveryCandidates(response)
  const items = candidates.map((candidate, index) => ({ id: candidate.id, index, level: LEVEL_OF[sectionOf(candidate)] ?? 3, section: sectionOf(candidate) }))
  const pick = (section: string, count: number) => items.filter((item) => item.section === section).slice(0, count).map((item) => item.id)
  const first = [...pick('start', 3), ...pick('worth', 2)]
  const rest = items.filter((item) => !first.includes(item.id)).sort((a, b) => a.level - b.level || a.index - b.index).map((item) => item.id)
  return [...first, ...rest]
}

function roleResponse(id: string, title: string, options: { count?: number; presented?: number; role?: Partial<NonNullable<SearchResponse['role']>>; extra?: Partial<SearchResponse> } = {}): SearchResponse {
  const count = options.count ?? 25
  const trimmed: SearchResponse = {
    ...RESPONSE,
    search_id: id,
    candidates: RESPONSE.candidates.slice(0, count),
    explanations: RESPONSE.explanations.slice(0, count),
    evidence: (RESPONSE.evidence ?? []).slice(0, count),
    candidate_count: count,
    workspace_arranged: false,
  }
  const order = levelOrder(trimmed)
  const presentedIds = order.slice(0, options.presented ?? 5)
  const presentation: NonNullable<SearchResponse['presentation']> = {}
  for (const candidate of trimmed.candidates) {
    const cid = candidate.candidate_id as string
    presentation[cid] = { state: presentedIds.includes(cid) ? 'presented' : 'reserve', source: 'initial', seen: presentedIds.includes(cid), stale: false, batch: presentedIds.includes(cid) ? 1 : null }
  }
  return {
    ...trimmed,
    confirmed_brief: { confirmation_id: `conf-${id}`, session_id: `session-${id}`, posted_title: title, posted_title_source: 'recruiter', candidate_identity: title, content_hash: 'x' },
    role: { status: 'searching', pause_reason: null, pause_kind: null, can_resume: true, has_feedback: false, exhausted: false, label: { company: 'Northwind Payments', place: 'Toronto' }, ...options.role },
    presentation,
    availability: { kind: 'ok', profiles_returned: 110577, retrieved: 50 },
    calibration: { state: 'pending', summary: null, dismissed: [] },
    feedback: {},
    new_candidates: 0,
    retrieval_exhausted: false,
    recruiter_decisions: {},
    notes: {},
    ...options.extra,
  } as SearchResponse
}

function addRole(id: string, title: string, options: Parameters<typeof roleResponse>[2] = {}): Sim {
  const response = roleResponse(id, title, options)
  const sim: Sim = { response, sessionId: `session-${id}`, initialIds: Object.entries(response.presentation ?? {}).filter(([, entry]) => entry.state === 'presented').map(([cid]) => cid) }
  roles.set(id, sim)
  return sim
}

// ---- scenarios -----------------------------------------------------------------------------------------------------------------

let activeKey: { kind: 'search' | 'draft'; id: string } | null = null
addRole('role-a', 'AI Engineer')
addRole('role-b', 'Staff Backend Engineer', { count: 25 }).response.role!.label = { company: 'Epiq', place: 'Hyderabad' }
addRole('role-c', 'ML Platform Engineer').response.role!.label = { company: 'Acme', place: 'Remote · United States' }

const decisionsFor = (sim: Sim, ids: string[], decisions: Array<[string, string | null]>) => {
  ids.forEach((cid, index) => {
    const [decision, reason] = decisions[index] ?? [null, null]
    if (!decision) return
    sim.response.recruiter_decisions![cid] = decision
    if (reason) sim.response.feedback![cid] = { decision, reason, note: null }
  })
}

switch (scenario) {
  case 'review':
    activeKey = { kind: 'search', id: 'role-a' }
    break
  case 'searching': {
    const sim = addRole('role-a', 'AI Engineer', { presented: 0, extra: { status: 'running', progress: { admitted: 25, review_ready: 11, building_context: 14, surfaced: 0 } } })
    sim.response.candidate_states = Object.fromEntries(sim.response.candidates.map((c, i) => [c.candidate_id as string, i < 11 ? 'review_ready' : 'building_context']))
    activeKey = { kind: 'search', id: 'role-a' }
    break
  }
  case 'narrow':
    addRole('role-a', 'AI Engineer', { count: 12, extra: { availability: { kind: 'narrow', profiles_returned: 12, retrieved: 12 } } })
    activeKey = { kind: 'search', id: 'role-a' }
    break
  case 'new': {
    const sim = addRole('role-a', 'AI Engineer', { extra: { new_candidates: 5 } })
    Object.keys(sim.response.presentation!).slice(20).forEach((cid) => (sim.response.presentation![cid] = { state: 'reserve', source: 'daily', seen: false, stale: false }))
    activeKey = { kind: 'search', id: 'role-a' }
    break
  }
  case 'paused-none':
  case 'paused-feedback':
  case 'paused-narrow':
  case 'paused-exhausted': {
    const kind = scenario === 'paused-none' ? 'no_engagement' : scenario === 'paused-feedback' ? 'feedback' : scenario === 'paused-narrow' ? 'narrow' : 'exhausted'
    const sim = addRole('role-a', 'AI Engineer', {
      count: kind === 'narrow' ? 12 : 25,
      role: { status: 'paused', pause_reason: 'window_ended', pause_kind: kind, has_feedback: kind === 'feedback' },
      extra: kind === 'narrow' ? { availability: { kind: 'narrow', profiles_returned: 12, retrieved: 12 }, retrieval_exhausted: true } : kind === 'exhausted' ? { retrieval_exhausted: true } : {},
    })
    if (kind === 'feedback') decisionsFor(sim, sim.initialIds, [['shortlist', null], ['reject', 'seniority'], ['maybe', 'type_of_work']])
    activeKey = { kind: 'search', id: 'role-a' }
    break
  }
  case 'brief':
    activeKey = { kind: 'draft', id: 'draft-1' }
    break
  case 'ready':
    activeKey = { kind: 'draft', id: 'draft-2' }
    break
  default:
    activeKey = null
}
if (activeKey) window.localStorage.setItem('recruiterai:activeSearch', JSON.stringify(activeKey))
else window.localStorage.removeItem('recruiterai:activeSearch')
window.localStorage.removeItem('recruiterai:composeDraft')

// ---- the stand-in backend -------------------------------------------------------------------------------------------------------

const PROPOSED: SearchIntent = (intakes[1].intent ?? {}) as SearchIntent
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

function summaryFor(sim: Sim) {
  const dims = new Set<string>()
  const missing: string[] = []
  const candidates = buildDiscoveryCandidates(sim.response)
  for (const [cid, feedback] of Object.entries(sim.response.feedback ?? {})) {
    const reason = feedback.reason ?? ''
    if (reason.includes('technology') || reason === 'skill_not_demonstrated') {
      dims.add('technology')
      const candidate = candidates.find((entry) => entry.id === cid)
      const row = candidate?.ledger.find((group) => group.tier === 'core')?.rows.find((entry) => entry.verdict !== 'met' && !entry.derived)
      if (row && !missing.includes(row.requirement)) missing.push(row.requirement.replace(/[.\s]+$/, ''))
    }
    if (reason.startsWith('seniority')) dims.add('seniority')
    if (reason.includes('experience')) dims.add('experience')
    if (reason === 'type_of_work') dims.add('work_type')
  }
  const dismissed = sim.response.calibration?.dismissed ?? []
  const dimensions = [...dims].filter((dimension) => !dismissed.includes(dimension))
  const phrase: Record<string, string> = { technology: missing.length ? `stronger evidence of ${missing.slice(0, 2).join(' and ')}` : 'stronger evidence of the required technology', seniority: 'profiles closer to the level of this role', experience: 'clearer relevant experience', work_type: 'a closer fit to the type of work' }
  const parts = dimensions.map((dimension) => phrase[dimension])
  const text = parts.length ? `Got it. I'll look for ${parts.length === 1 ? parts[0] : `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`}.` : "Got it. I'll keep searching against your brief."
  return { text, dimensions, requirements: missing }
}

function refreshCalibration(sim: Sim) {
  const calibration = sim.response.calibration
  if (!calibration || calibration.state === 'closed') return
  const decided = sim.initialIds.filter((cid) => ['shortlist', 'maybe', 'reject'].includes(sim.response.recruiter_decisions?.[cid] ?? '')).length
  const withReason = sim.initialIds.filter((cid) => Boolean(sim.response.feedback?.[cid]?.reason)).length
  if (calibration.state === 'pending' && decided >= 2 && withReason >= 1) calibration.state = 'ready'
  if (calibration.state === 'ready') calibration.summary = summaryFor(sim)
}

function currentResponse(sim: Sim): SearchResponse {
  if (sim.startedAt && sim.final && Date.now() - sim.startedAt > 2500) {
    sim.response = sim.final
    sim.startedAt = undefined
  }
  return sim.response
}

function searchList(): SearchListItem[] {
  const items: SearchListItem[] = []
  for (const [id, sim] of roles) {
    const response = sim.response
    const label = response.role?.label ?? {}
    const decisions = response.recruiter_decisions ?? {}
    items.push({
      id,
      kind: 'search',
      title: response.confirmed_brief?.posted_title ?? id,
      company: label.company ?? '',
      place: label.place ?? '',
      status: response.status ?? 'complete',
      role_status: response.role?.status ?? null,
      pause_kind: response.role?.pause_kind ?? null,
      new_count: response.new_candidates ?? 0,
      to_review_count: Object.entries(response.presentation ?? {}).filter(([cid, entry]) => entry.state === 'presented' && !decisions[cid]).length,
      updated_at: null,
    })
  }
  if (scenario === 'brief' || scenario === 'ready' || scenario === 'compose') {
    items.push({ id: 'draft-1', kind: 'draft', title: 'Data Engineer', company: 'Northwind Payments', place: 'Toronto', status: 'needs_clarification', role_status: null, pause_kind: null, new_count: 0, to_review_count: null, updated_at: null })
  }
  return items
}

const realFetch = window.fetch.bind(window)
window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, window.location.href)
  if (!url.pathname.startsWith('/search') && !url.pathname.startsWith('/intake') && !url.pathname.startsWith('/auth')) return realFetch(input, init)
  const method = (init?.method ?? 'GET').toUpperCase()
  const body = init?.body ? JSON.parse(init.body as string) : {}
  const path = url.pathname

  if (path === '/searches') return json({ searches: searchList() })

  const intakeMatch = path.match(/^\/intake\/([^/]+)(?:\/(.+))?$/)
  if (intakeMatch) {
    const [, id, action] = intakeMatch
    const fixture = id === 'draft-2' ? intakes[1] : id === 'draft-1' ? intakes[0] : intakes[1]
    if (path === '/intake/start') return json({ session_id: 'draft-1', result: intakes[0].result, boundary: body.boundary ?? intakes[0].boundary })
    if (!action) return json({ session_id: id, result: fixture.result, boundary: fixture.boundary, posted_title_input: fixture.posted_title_input })
    if (action === 'confirm') return json(PROPOSED)
    if (action === 'answer') return json({ session_id: id, result: intakes[1].result })
    if (action === 'confirmations') return json({ confirmation_id: 'conf-new', session_id: id, posted_title: fixture.posted_title_input, candidate_identity: 'Backend Engineer', content_hash: 'y', search_intent: PROPOSED, edits: {} })
  }

  const searchMatch = path.match(/^\/search(?:\/([^/]+))?(?:\/(.+))?$/)
  if (searchMatch) {
    const [, id, action] = searchMatch
    if (path === '/search' && method === 'POST') {
      const newId = body.search_id ?? 'role-new'
      const sim = roles.get(newId) ?? addRole(newId, 'Data Engineer')
      const finished = roleResponse(newId, 'Data Engineer')
      sim.final = finished
      sim.startedAt = Date.now()
      sim.initialIds = Object.entries(finished.presentation ?? {}).filter(([, entry]) => entry.state === 'presented').map(([cid]) => cid)
      sim.response = { ...finished, status: 'running', presentation: {}, progress: { admitted: 25, review_ready: 8, building_context: 17, surfaced: 0 } } as SearchResponse
      return json(sim.response)
    }
    const sim = id ? roles.get(id) : undefined
    if (!sim) return json({ detail: 'Search not found.' }, 404)
    if (!action && method === 'GET') return json(currentResponse(sim))
    if (action === 'candidate') {
      const response = currentResponse(sim)
      if (body.decision !== undefined) {
        if (body.decision) response.recruiter_decisions![body.candidate_id] = body.decision
        else delete response.recruiter_decisions![body.candidate_id]
        delete response.feedback![body.candidate_id]
      }
      if (body.feedback_reason || body.feedback_note) {
        response.feedback![body.candidate_id] = { decision: response.recruiter_decisions![body.candidate_id], reason: body.feedback_reason ?? response.feedback![body.candidate_id]?.reason ?? null, note: body.feedback_note ?? null }
      }
      refreshCalibration(sim)
      return json(response)
    }
    if (action === 'more') {
      const response = currentResponse(sim)
      if (response.calibration && response.calibration.state !== 'closed') response.calibration.state = 'closed'
      const reserve = Object.entries(response.presentation ?? {}).filter(([, entry]) => entry.state === 'reserve' && (!body.only_new || entry.source === 'daily'))
      const chosen = reserve.slice(0, 5)
      const nextBatch = Math.max(0, ...Object.values(response.presentation ?? {}).map((entry) => entry.batch ?? 0)) + 1
      chosen.forEach(([cid]) => (response.presentation![cid] = { state: 'presented', source: response.presentation![cid].source, seen: true, stale: false, batch: nextBatch }))
      if (body.only_new) response.new_candidates = Math.max(0, (response.new_candidates ?? 0) - chosen.length)
      return json({ presented: chosen.length, cycle_started: false, exhausted: chosen.length === 0 })
    }
    if (action === 'role') {
      const response = currentResponse(sim)
      if (response.role) {
        response.role.status = body.action === 'pause' ? 'paused' : 'searching'
        response.role.pause_reason = body.action === 'pause' ? 'manual' : null
        response.role.pause_kind = body.action === 'pause' ? 'no_engagement' : null
      }
      return json(response)
    }
    if (action === 'calibration') {
      const response = currentResponse(sim)
      if (response.calibration) {
        response.calibration.dismissed = body.dismiss ?? []
        response.calibration.summary = summaryFor(sim)
      }
      return json(response)
    }
    if (action === 'workspace') return json({ workspace_arranged: Boolean(body.arranged) })
  }
  return json({ detail: 'Not handled by the preview.' }, 404)
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RecruiterWorkspaceScreen />
  </StrictMode>,
)
