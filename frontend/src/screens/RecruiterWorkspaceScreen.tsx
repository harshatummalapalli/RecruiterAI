import { useEffect, useRef, useState } from 'react'
import { Menu } from 'lucide-react'
import {
  runCandidateSearch,
  loadPersistedSearch,
  loadIntakeSession,
  logout,
  startIntake,
  answerIntake,
  confirmIntake,
  createConfirmation,
  updateIntakeBoundary,
  listSearches,
  showMoreCandidates,
  setRoleAction,
  correctCalibration,
} from '../services/recruiterWorkflow'
import { createEmptySearchBrief, searchIntentToBrief, type SearchBrief } from '../models/searchBrief'
import { diffBriefEdits, formatBoundaryLocation } from '../models/livingBrief'
import type { IntakeIssue, IntakeResult } from '../models/intake'
import type { ActiveSearch } from '../models/roleWorkspace'
import { CandidateReviewScreen } from './CandidateReviewScreen'
import { HomeScreen } from './HomeScreen'
import { LivingBrief } from './LivingBrief'
import { SettingsScreen } from './SettingsScreen'
import { SearchBoundaryForm } from './SearchBoundaryForm'
import { GlobalShell, type GlobalDestination } from '../components/GlobalShell'
import { SearchSidebar, type RoleNavInfo } from '../components/SearchSidebar'
import { createEmptySearchBoundary, isSearchBoundaryComplete, type SearchBoundary } from '../models/searchBoundary'
import type { SearchListItem, SearchResponse } from '../types'
import './RecruiterWorkspaceScreen.css'

type ParseState = 'idle' | 'parsing' | 'success' | 'error'
type Step = 'home' | 'settings' | 'jd' | 'brief' | 'review'
type SearchState = 'idle' | 'searching' | 'done' | 'error'

const RECRUITER_NAME = 'Harsha'

// The search RESULT lives on the backend (see backend/services/search_store.py); a refresh must never re-run
// OpenAI/CrustData. The browser only remembers which search was open, the working copy of each brief, and the one
// new-search form that has been typed but not built yet.
const ACTIVE_KEY = 'recruiterai:activeSearch'
const LEGACY_POINTER_KEY = 'recruiterai:lastSearch'
const BRIEFS_KEY = 'recruiterai:briefs'
const COMPOSE_KEY = 'recruiterai:composeDraft'
const SIDEBAR_PIN_KEY = 'recruiterai:sidebarPinned'
const SIDEBAR_REFRESH_MS = 30000

type ComposeDraft = { postedTitle: string; jdText: string; boundary: SearchBoundary }

function readJson<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

function writeJson(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Best-effort only: persistence is a convenience, not a correctness requirement.
  }
}

function removeKey(key: string): void {
  try {
    window.localStorage.removeItem(key)
  } catch {
    // Best-effort only.
  }
}

function saveWorkingBrief(searchId: string, brief: SearchBrief): void {
  const all = readJson<Record<string, SearchBrief>>(BRIEFS_KEY) ?? {}
  writeJson(BRIEFS_KEY, { ...all, [searchId]: brief })
}

function readWorkingBrief(searchId: string): SearchBrief | null {
  return (readJson<Record<string, SearchBrief>>(BRIEFS_KEY) ?? {})[searchId] ?? null
}

function getGreeting(hour: number): string {
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

function messagesOf(error: unknown, fallback: string): string[] {
  const messages = (error as { messages?: string[] } | null)?.messages
  return messages && messages.length ? messages : [fallback]
}

function sameTitle(a: string, b: string): boolean {
  const normalize = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
  return normalize(a) === normalize(b)
}

export function RecruiterWorkspaceScreen() {
  const [postedTitle, setPostedTitle] = useState('')
  const [jdText, setJdText] = useState('')
  const [boundary, setBoundary] = useState<SearchBoundary>(createEmptySearchBoundary)
  // The recruiter's working copy of what can still be adjusted, and what the server proposed (to send only real edits).
  const [brief, setBrief] = useState<SearchBrief>(createEmptySearchBrief)
  const [baselineBrief, setBaselineBrief] = useState<SearchBrief | null>(null)
  const [parseState, setParseState] = useState<ParseState>('idle')
  const [parseErrors, setParseErrors] = useState<string[]>([])
  const [step, setStep] = useState<Step>('home')
  const [intakeSessionId, setIntakeSessionId] = useState<string | null>(null)
  const [intakeResult, setIntakeResult] = useState<IntakeResult | null>(null)
  const [isAnswering, setIsAnswering] = useState(false)
  const [searchState, setSearchState] = useState<SearchState>('idle')
  const [searchErrors, setSearchErrors] = useState<string[]>([])
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null)
  const [searchId, setSearchId] = useState<string | null>(null)
  // Bumped once per search start or switch: lets CandidateReviewScreen reset its open-record/edit-brief UI state
  // exactly once per NEW search, without resetting on every progressive poll tick of the SAME still-running search.
  const [searchGeneration, setSearchGeneration] = useState(0)
  // Multiple searches: the sidebar's list and which one is open. `active === null` is the new-search form.
  const [searches, setSearches] = useState<SearchListItem[]>([])
  const [active, setActive] = useState<ActiveSearch | null>(null)
  const [roleMessage, setRoleMessage] = useState<string | null>(null)
  const [searchNotice, setSearchNotice] = useState<string | null>(null)
  // The role sidebar collapses to a narrow rail when a candidate record opens, so the record pane has the room —
  // unless the recruiter has pinned it open. "Keep roles open" persists across sessions; whether a candidate is
  // currently open does not (it's not meaningful state to remember on reload).
  //
  // One-directional on purpose: collapsing only ever happens because a candidate record OPENED. It never
  // auto-reopens just because a record closed — including when a candidate filter change closes the record as a
  // side effect (CandidateWorkspace.changeFilter's onOpen(null), when the open candidate doesn't match the new
  // filter). A candidate filter is candidate-content only; it must never visibly change the workspace shell. The
  // sidebar only reopens via an explicit recruiter action — the header hamburger (equivalent to Glue) or Glue
  // itself — never as a side effect of which candidates happen to be visible.
  const [sidebarPinned, setSidebarPinned] = useState<boolean>(() => readJson<boolean>(SIDEBAR_PIN_KEY) ?? false)
  const [candidateOpen, setCandidateOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  useEffect(() => {
    if (candidateOpen && !sidebarPinned) setSidebarCollapsed(true)
    else if (sidebarPinned) setSidebarCollapsed(false)
  }, [candidateOpen, sidebarPinned])
  // The poll loop for a running search. A ref because it is plumbing, cleared when a search is opened or started or the
  // component unmounts, so at most one poll loop is ever active.
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Guards against a slow load finishing after the recruiter has already switched to another search.
  const loadToken = useRef(0)
  const stateRef = useRef({ active, searchState, searchResponse })
  stateRef.current = { active, searchState, searchResponse }

  const greeting = `${getGreeting(new Date().getHours())}, ${RECRUITER_NAME}.`
  const hasJdText = jdText.trim().length > 0
  const isBoundaryComplete = isSearchBoundaryComplete(boundary)
  const canParse = hasJdText && isBoundaryComplete && parseState !== 'parsing'
  const isBusy = parseState === 'parsing'

  const refreshSearches = () => {
    void listSearches()
      .then(setSearches)
      .catch(() => {
        // The sidebar is a convenience; the open search keeps working without it.
      })
  }

  const setActiveSearch = (next: ActiveSearch | null) => {
    setActive(next)
    if (next) writeJson(ACTIVE_KEY, next)
    else removeKey(ACTIVE_KEY)
  }

  // What the server proposed for this brief, shown in the adjustable panel and used as the baseline for real edits.
  const refreshProposal = async (sessionId: string, keepWorkingCopy: SearchBrief | null = null) => {
    try {
      const proposed = searchIntentToBrief(await confirmIntake(sessionId))
      setBrief(keepWorkingCopy ?? proposed)
      setBaselineBrief(proposed)
    } catch {
      // Only reachable while a question is open; the brief is not ready, so there is nothing to propose yet.
    }
  }

  const stopPolling = () => {
    if (pollTimeoutRef.current !== null) {
      clearTimeout(pollTimeoutRef.current)
      pollTimeoutRef.current = null
    }
  }

  // Progressive Candidate Workspace: POST /search returns almost immediately with status="running" — the actual
  // pipeline runs on a backend background thread. This polls GET /search/{id} every 1.5s and updates the list as
  // candidates move SURFACED -> BUILDING_CONTEXT -> REVIEW_READY, stopping once the search leaves "running".
  const POLL_INTERVAL_MS = 1500

  const pollSearch = (id: string, activeBrief: SearchBrief | null) => {
    stopPolling()
    // One failed or empty poll (a network blip, a deploy restart) must not end the loop: it would leave the workspace
    // frozen mid-search with no error. Retry a few times, then surface the error state.
    let consecutiveFailures = 0
    const tick = async () => {
      const response = await loadPersistedSearch(id).catch(() => null)
      if (stateRef.current.active?.id !== id) return // the recruiter opened another search
      if (!response) {
        consecutiveFailures += 1
        if (consecutiveFailures >= 5) {
          setSearchState('error')
          return
        }
        pollTimeoutRef.current = setTimeout(tick, POLL_INTERVAL_MS)
        return
      }
      consecutiveFailures = 0
      setSearchResponse(response)
      if (response.status === 'running') {
        pollTimeoutRef.current = setTimeout(tick, POLL_INTERVAL_MS)
        return
      }
      setSearchState(response.status === 'complete' ? 'done' : 'error')
      if (activeBrief) saveWorkingBrief(id, activeBrief)
      refreshSearches()
    }
    void tick()
  }

  // Everything that belongs to ONE search goes back to a blank slate. The sidebar list and the recruiter's other
  // searches are untouched: each one is stored on the server.
  const clearWorkingState = () => {
    stopPolling()
    setPostedTitle('')
    setJdText('')
    setBoundary(createEmptySearchBoundary())
    setBrief(createEmptySearchBrief())
    setBaselineBrief(null)
    setParseState('idle')
    setParseErrors([])
    setStep('jd')
    setIntakeSessionId(null)
    setIntakeResult(null)
    setSearchState('idle')
    setSearchErrors([])
    setSearchResponse(null)
    setSearchId(null)
    setRoleMessage(null)
    setSearchNotice(null)
    // A fresh workspace context (new role opened, or back to composing) never starts pre-collapsed from
    // whatever the previous role left behind.
    setSidebarCollapsed(false)
  }

  // The brief and boundary a search came from, resumed read only so the boundary can still be edited and re-confirmed.
  const resumeSession = async (sessionId: string, token: number, workingCopy: SearchBrief | null) => {
    const session = await loadIntakeSession(sessionId).catch(() => null)
    if (token !== loadToken.current || !session) return false
    setIntakeSessionId(sessionId)
    setIntakeResult(session.result)
    if (session.boundary) setBoundary(session.boundary)
    if (session.posted_title_input) setPostedTitle(session.posted_title_input)
    setJdText(session.result.raw_input ?? '')
    await refreshProposal(sessionId, workingCopy)
    return true
  }

  const openRole = async (id: string, token: number) => {
    const response = await loadPersistedSearch(id).catch(() => null)
    if (token !== loadToken.current) return
    if (!response) {
      // The record is gone (or unreadable): fall back to the new-search form rather than showing a blank page.
      clearWorkingState()
      setActiveSearch(null)
      refreshSearches()
      return
    }
    const workingCopy = readWorkingBrief(id)
    if (workingCopy) setBrief(workingCopy)
    setSearchId(id)
    setSearchResponse(response)
    setParseState('success')
    setStep('review')
    setSearchGeneration((current) => current + 1)
    if (response.status === 'running') {
      setSearchState('searching')
      pollSearch(id, workingCopy)
    } else {
      setSearchState(response.status === 'error' ? 'error' : 'done')
    }
    const sessionId = response.confirmed_brief?.session_id ?? null
    if (sessionId) await resumeSession(sessionId, token, workingCopy)
  }

  const openDraft = async (sessionId: string, token: number) => {
    const opened = await resumeSession(sessionId, token, null)
    if (token !== loadToken.current) return
    if (!opened) {
      clearWorkingState()
      setActiveSearch(null)
      refreshSearches()
      return
    }
    setParseState('success')
    setStep('brief')
  }

  const openSearch = async (item: Pick<SearchListItem, 'kind' | 'id'>) => {
    loadToken.current += 1
    const token = loadToken.current
    saveComposeDraft()
    clearWorkingState()
    setActiveSearch({ kind: item.kind, id: item.id })
    if (item.kind === 'draft') await openDraft(item.id, token)
    else await openRole(item.id, token)
  }

  // Typed but not built yet: kept so switching to another search and back never loses it.
  const saveComposeDraft = () => {
    if (stateRef.current.active !== null) return
    if (postedTitle.trim() || jdText.trim()) writeJson(COMPOSE_KEY, { postedTitle, jdText, boundary } satisfies ComposeDraft)
  }

  const handleStartNewSearch = () => {
    loadToken.current += 1
    saveComposeDraft()
    clearWorkingState()
    setActiveSearch(null)
    const draft = readJson<ComposeDraft>(COMPOSE_KEY)
    if (draft) {
      setPostedTitle(draft.postedTitle ?? '')
      setJdText(draft.jdText ?? '')
      if (draft.boundary) setBoundary(draft.boundary)
    }
  }

  const toggleSidebarPin = () => {
    setSidebarPinned((current) => {
      const next = !current
      writeJson(SIDEBAR_PIN_KEY, next)
      return next
    })
  }

  const handleSignOut = () => {
    logout().finally(() => window.location.reload())
  }

  // On mount: list every search, then reopen the one that was open. A refresh must never re-run OpenAI or CrustData.
  useEffect(() => {
    refreshSearches()
    const remembered = readJson<ActiveSearch>(ACTIVE_KEY)
    const legacy = readJson<{ searchId?: string }>(LEGACY_POINTER_KEY)
    const target: ActiveSearch | null = remembered ?? (legacy?.searchId ? { kind: 'search', id: legacy.searchId } : null)
    if (target) {
      void openSearch(target)
    } else {
      const draft = readJson<ComposeDraft>(COMPOSE_KEY)
      if (draft) {
        setPostedTitle(draft.postedTitle ?? '')
        setJdText(draft.jdText ?? '')
        if (draft.boundary) setBoundary(draft.boundary)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // The new-search form is remembered as it is typed.
  useEffect(() => {
    if (step === 'jd' && active === null && (postedTitle.trim() || jdText.trim())) {
      writeJson(COMPOSE_KEY, { postedTitle, jdText, boundary } satisfies ComposeDraft)
    }
  }, [step, active, postedTitle, jdText, boundary])

  // Quiet background refresh: the sidebar, and the open role when the server has news (candidates found in the
  // background, a role that paused). Never while a search is being watched, and never moves anything the recruiter is
  // looking at: the workspace keeps the order it has.
  useEffect(() => {
    const sync = () => {
      refreshSearches()
      const { active: current, searchState: state, searchResponse: response } = stateRef.current
      if (current?.kind !== 'search' || state === 'searching') return
      void loadPersistedSearch(current.id)
        .then((fresh) => {
          if (!fresh || stateRef.current.active?.id !== current.id || stateRef.current.searchState === 'searching') return
          const changed =
            fresh.status !== response?.status ||
            fresh.new_candidates !== response?.new_candidates ||
            fresh.role?.status !== response?.role?.status ||
            fresh.candidate_count !== response?.candidate_count
          if (!changed) return
          setSearchResponse(fresh)
          if (fresh.status === 'running') {
            setSearchState('searching')
            pollSearch(current.id, null)
          }
        })
        .catch(() => {})
    }
    const interval = window.setInterval(sync, SIDEBAR_REFRESH_MS)
    window.addEventListener('focus', sync)
    return () => {
      window.clearInterval(interval)
      window.removeEventListener('focus', sync)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => stopPolling, [])

  // RecruiterAI understands the role before searching: the title, the description and the Search Boundary go to the
  // backend, which reads the role once and returns the brief. Nothing is searched yet.
  const handleParse = async () => {
    if (!canParse) {
      return
    }
    setParseState('parsing')
    setParseErrors([])
    try {
      const { session_id, result, boundary: stored } = await startIntake(jdText, boundary, postedTitle)
      setIntakeSessionId(session_id)
      setIntakeResult(result)
      if (stored) setBoundary(stored)
      setBaselineBrief(null)
      setParseState('success')
      setStep('brief')
      setActiveSearch({ kind: 'draft', id: session_id })
      removeKey(COMPOSE_KEY)
      refreshSearches()
      if (result.status === 'ready') {
        await refreshProposal(session_id)
      }
    } catch (error) {
      setParseState('error')
      setParseErrors(messagesOf(error, 'Unable to understand this job description.'))
    }
  }

  // An answer resolves ONE question. The role reading is pinned; only the fields the answer names change.
  const handleAnswerIntake = async (issue: IntakeIssue, value: string, label: string) => {
    if (!intakeSessionId || !issue.id) {
      return
    }
    setIsAnswering(true)
    try {
      const { result } = await answerIntake(intakeSessionId, issue.id, value, label)
      setIntakeResult(result)
      if (result.status === 'ready') {
        await refreshProposal(intakeSessionId)
      }
    } catch {
      setSearchErrors(['That answer could not be saved. Please try again.'])
    } finally {
      setIsAnswering(false)
    }
  }

  // Boundary edits are deterministic: validated and re-applied on the server with no model call. Rejects with plain
  // messages, which the boundary editor shows.
  const handleApplyBoundary = async (next: SearchBoundary) => {
    if (!intakeSessionId) {
      throw new Error('No brief to apply this to.')
    }
    const { result, boundary: stored } = await updateIntakeBoundary(intakeSessionId, next)
    setBoundary(stored ?? next)
    setIntakeResult(result)
    if (result.status === 'ready') {
      await refreshProposal(intakeSessionId)
    }
  }

  // The recruiter presses Search. The server checks that the brief is ready, builds the executable search itself from
  // what was confirmed (plus only the edits made here), and stores it. The browser never supplies the search. On a role
  // that is already searching, the server decides whether the change matters to what is searched.
  const handleSearch = async (briefOverride?: SearchBrief) => {
    if (!intakeSessionId) {
      setSearchErrors(['This search has no brief to confirm. Start a new search.'])
      return
    }
    const activeBrief = briefOverride ?? brief
    const rerun = searchId !== null
    setSearchState('searching')
    setSearchErrors([])
    setSearchNotice(null)
    stopPolling()

    try {
      const confirmation = await createConfirmation(intakeSessionId, baselineBrief ? diffBriefEdits(baselineBrief, activeBrief) : {})
      setSearchGeneration((current) => current + 1)
      const response = await runCandidateSearch(confirmation.confirmation_id, { searchId: searchId ?? undefined, debug: import.meta.env.DEV })
      // The search has already started server-side — show the workspace immediately rather than waiting for the
      // whole pipeline; polling fills it in progressively.
      setSearchResponse(response)
      setStep('review')
      setSearchId(response.search_id)
      setActiveSearch({ kind: 'search', id: response.search_id })
      saveWorkingBrief(response.search_id, activeBrief)
      refreshSearches()
      if (response.status === 'running') {
        pollSearch(response.search_id, activeBrief)
      } else {
        setSearchState(response.status === 'error' ? 'error' : 'done')
        if (rerun) setSearchNotice('Nothing that changes the search was edited, so no new search was run.')
      }
    } catch (error) {
      // A refusal (open questions, an incomplete boundary) is explained in plain words; anything else is an error.
      const explained = (error as { messages?: string[] } | null)?.messages
      setSearchErrors(explained ?? ['The search could not be started. Please try again.'])
      setSearchState(step === 'review' ? 'error' : 'idle')
    }
  }

  // "Show me more": what is already read comes first; when it is used up the server runs the next retrieval and this
  // watches it, exactly like the first one.
  const handleShowMore = async (onlyNew = false) => {
    if (!searchId) return
    setRoleMessage(null)
    try {
      const outcome = await showMoreCandidates(searchId, onlyNew)
      const response = await loadPersistedSearch(searchId)
      if (response && stateRef.current.active?.id === searchId) setSearchResponse(response)
      if (outcome.cycle_started) {
        setSearchState('searching')
        pollSearch(searchId, null)
      } else if (outcome.exhausted) {
        setRoleMessage("We haven't found additional candidates in the current search.")
      }
      refreshSearches()
    } catch (error) {
      setRoleMessage(messagesOf(error, 'More candidates could not be shown right now.')[0])
    }
  }

  const handleRoleAction = async (action: 'pause' | 'resume') => {
    if (!searchId) return
    setRoleMessage(null)
    try {
      const response = await setRoleAction(searchId, action)
      setSearchResponse(response)
      if (response.status === 'running') {
        setSearchState('searching')
        pollSearch(searchId, null)
      }
      refreshSearches()
    } catch (error) {
      setRoleMessage(messagesOf(error, 'The role could not be changed right now.')[0])
    }
  }

  const handleCorrectCalibration = async (dismiss: string[]) => {
    if (!searchId) return
    try {
      setSearchResponse(await correctCalibration(searchId, dismiss))
    } catch {
      // The summary stays as it was; nothing else depends on it.
    }
  }

  // Back to "Your searches": leaves whatever role was open without touching its data, and stops resuming it on
  // the next load — Home is the resting state until another row (or New Search) is clicked.
  const handleGoHome = () => {
    loadToken.current += 1
    clearWorkingState()
    setActiveSearch(null)
    setStep('home')
  }

  // Settings is a global destination, not a role one — it never touches
  // whatever role/search is currently open, so returning from it (via the
  // global shell's Home/role state) needs no special handling here.
  const handleGoSettings = () => {
    setStep('settings')
  }

  // Pause/Resume triggered from a Home row, for a role that is not the one currently open in the workspace.
  // Independent of searchId/searchResponse — only refreshes the Home list, never touches open-workspace state.
  const handleRoleActionFromHome = async (id: string, action: 'pause' | 'resume') => {
    try {
      await setRoleAction(id, action)
    } catch {
      // The list just won't reflect the change; nothing else depended on it succeeding.
    } finally {
      refreshSearches()
    }
  }

  const handleSearchResponse = (response: SearchResponse) => {
    if (response.search_id === stateRef.current.active?.id) {
      setSearchResponse(response)
      refreshSearches()
    }
  }

  // Candidate Review is contextual to the active search: the header names the ROLE as it was posted, and shows what
  // is actually being searched for separately, so the AI's reading never looks like the posted title.
  const confirmed = searchResponse?.confirmed_brief
  const posted = confirmed?.posted_title ?? intakeResult?.role_understanding.posted_title ?? (postedTitle.trim() || null)
  const identity = confirmed?.candidate_identity ?? brief.role.primaryTitle ?? ''
  const showIdentity = Boolean(posted && identity && !sameTitle(posted, identity))

  const progress = searchResponse?.progress
  const isRole = Boolean(searchResponse?.role)
  const presentedCount = isRole ? Object.values(searchResponse?.presentation ?? {}).filter((entry) => entry.state === 'presented').length : null
  const roleStatusLabel = searchResponse?.role?.status === 'paused' ? 'Paused' : 'Searching'
  const workspaceSubtitle = (() => {
    if (isRole) {
      if (searchState === 'searching' && !presentedCount) return 'Finding candidates…'
      const company = [searchResponse?.role?.label?.company, searchResponse?.role?.label?.place].filter(Boolean).join(' · ')
      return `${roleStatusLabel}${company ? ` · ${company}` : ''}`
    }
    if (!progress || !progress.admitted) {
      return searchState === 'searching' ? 'Finding candidates…' : 'What are you hiring for today?'
    }
    const parts = [`${progress.admitted} candidate${progress.admitted === 1 ? '' : 's'} selected`]
    if (progress.review_ready) parts.push(`${progress.review_ready} ready for review`)
    if (progress.building_context) parts.push(`${progress.building_context} building context`)
    if (progress.surfaced) parts.push(`${progress.surfaced} surfaced`)
    return parts.join(' · ')
  })()

  const globalDestination: GlobalDestination = step === 'home' ? 'home' : step === 'settings' ? 'settings' : 'role'

  // Role nav ("where am I inside this hiring mandate") once the role's own
  // reading exists — Understanding is always reachable; Candidates only
  // once a search has actually run (nothing to show before that).
  const roleTitle = posted || identity || 'Untitled role'
  const roleNavInfo: RoleNavInfo | undefined =
    intakeResult && (step === 'brief' || step === 'review')
      ? {
          title: roleTitle,
          statusLabel: isRole ? roleStatusLabel : 'Drafting',
          company: searchResponse?.role?.label?.company ?? '',
          section: step === 'brief' ? 'understanding' : 'candidates',
          candidatesEnabled: Boolean(searchResponse),
          onSelectUnderstanding: () => setStep('brief'),
          onSelectCandidates: () => {
            if (searchResponse) setStep('review')
          },
        }
      : undefined

  if (step === 'home') {
    return (
      <GlobalShell active={globalDestination} onHome={handleGoHome} onSettings={handleGoSettings} recruiterName={RECRUITER_NAME} onSignOut={handleSignOut}>
        <HomeScreen
          items={searches}
          recruiterName={RECRUITER_NAME}
          onOpen={(item) => void openSearch(item)}
          onNew={handleStartNewSearch}
          onPause={(id) => void handleRoleActionFromHome(id, 'pause')}
          onResume={(id) => void handleRoleActionFromHome(id, 'resume')}
        />
      </GlobalShell>
    )
  }

  if (step === 'settings') {
    return (
      <GlobalShell active={globalDestination} onHome={handleGoHome} onSettings={handleGoSettings} recruiterName={RECRUITER_NAME} onSignOut={handleSignOut}>
        <SettingsScreen recruiterName={RECRUITER_NAME} />
      </GlobalShell>
    )
  }

  return (
    <GlobalShell active={globalDestination} onHome={handleGoHome} onSettings={handleGoSettings} recruiterName={RECRUITER_NAME} onSignOut={handleSignOut}>
    <div className="app-shell">
      <SearchSidebar
        items={searches}
        active={active}
        onSelect={(item) => void openSearch(item)}
        onNew={handleStartNewSearch}
        isNewActive={active === null}
        collapsed={sidebarCollapsed}
        glued={sidebarPinned}
        onToggleGlue={toggleSidebarPin}
        roleNav={roleNavInfo}
      />
      <main className="workspace">
        <div className={`workspace__content${step === 'review' ? ' workspace__content--wide' : ''}`}>
          <header className="workspace__greeting">
            <div className="workspace__greeting-row">
              {step === 'review' && sidebarCollapsed ? (
                <button
                  type="button"
                  className="workspace__reopen-sidebar"
                  onClick={toggleSidebarPin}
                  aria-label="Show roles"
                  title="Show roles"
                >
                  <Menu size={16} aria-hidden="true" />
                </button>
              ) : null}
              {step === 'review' ? (
                <div>
                  <h1>{roleTitle}</h1>
                  {showIdentity ? (
                    <p className="workspace__identity">
                      <span className="workspace__identity-label">Searching for</span> {identity}
                    </p>
                  ) : null}
                  <p className="workspace__role-subtitle">
                    <span className={`workspace__role-dot${searchResponse?.role?.status !== 'paused' ? ' is-active' : ''}`} aria-hidden="true" />
                    {workspaceSubtitle}
                  </p>
                </div>
              ) : (
                <div>
                  <h1>{greeting}</h1>
                  <p>What are you hiring for today?</p>
                </div>
              )}
            </div>
          </header>

          {step === 'jd' ? (
            <div className="workspace__grid workspace__grid--single">
              <section className="workspace__composer" aria-label="Job description composer">
                <div className="brief-field workspace__title-field">
                  <label className="brief-field__label" htmlFor="posted-title">
                    Job Title
                  </label>
                  <input
                    id="posted-title"
                    type="text"
                    className="brief-input"
                    value={postedTitle}
                    disabled={isBusy}
                    placeholder="e.g. AI Engineer"
                    onChange={(event) => setPostedTitle(event.target.value)}
                  />
                  <span className="boundary-form__caption">The title you're hiring for.</span>
                </div>

                <textarea
                  className="workspace__editor"
                  value={jdText}
                  onChange={(event) => setJdText(event.target.value)}
                  placeholder="What are you hiring for? Paste the full job description, rough hiring-manager notes, or just describe the role in your own words."
                  disabled={isBusy}
                  aria-label="Job description"
                  rows={14}
                />

                <SearchBoundaryForm boundary={boundary} onChange={(updater) => setBoundary(updater)} disabled={isBusy} />

                <div className="workspace__composer-foot">
                  <span className="workspace__char-count">{jdText.length > 0 ? `${jdText.length.toLocaleString()} characters` : ''}</span>

                  <div className="workspace__actions">
                    <div className="workspace__status-slot" aria-live="polite">
                      {parseState === 'error' ? (
                        <div className="workspace__status workspace__status--error" role="alert">
                          {parseErrors.map((message) => (
                            <p key={message}>{message}</p>
                          ))}
                          <button type="button" className="workspace__retry" onClick={handleParse}>
                            Retry
                          </button>
                        </div>
                      ) : null}
                    </div>

                    <button type="button" className={`workspace__parse${isBusy ? ' workspace__parse--busy' : ''}`} onClick={handleParse} disabled={!canParse}>
                      {isBusy ? (
                        <>
                          <span className="workspace__spinner" aria-hidden="true" />
                          <span>Understanding the role…</span>
                        </>
                      ) : (
                        <span>Build brief</span>
                      )}
                    </button>
                  </div>
                </div>
              </section>
            </div>
          ) : null}

          {step === 'brief' && intakeResult ? (
            <div className="workspace__brief">
              <div className="workspace__inputs-line">
                <span>
                  <strong>{intakeResult.role_understanding.posted_title || postedTitle.trim() || 'Untitled role'}</strong> · {boundary.hiring_company} ·{' '}
                  {formatBoundaryLocation(boundary)}
                </span>
                <button type="button" className="workspace__link" onClick={() => setStep('jd')}>
                  Edit description
                </button>
              </div>
              <LivingBrief
                result={intakeResult}
                boundary={boundary}
                brief={brief}
                onChangeBrief={(_path, updater) => setBrief((current) => updater(current))}
                onAnswer={handleAnswerIntake}
                isAnswering={isAnswering}
                onApplyBoundary={handleApplyBoundary}
                onSearch={() => void handleSearch()}
                isSearching={searchState === 'searching'}
                searchErrors={searchErrors}
              />
            </div>
          ) : null}

          {step === 'review' ? (
            <CandidateReviewScreen
              brief={brief}
              onChangeBrief={(_path, updater) => setBrief((current) => updater(current))}
              searchResponse={searchResponse}
              searchState={searchState}
              onRunSearch={() => void handleSearch()}
              searchId={searchId}
              searchGeneration={searchGeneration}
              boundary={intakeSessionId ? boundary : null}
              onApplyBoundary={handleApplyBoundary}
              intakeResult={intakeSessionId ? intakeResult : null}
              onAnswer={handleAnswerIntake}
              isAnswering={isAnswering}
              searchErrors={searchErrors}
              onShowMore={handleShowMore}
              onRoleAction={handleRoleAction}
              onCorrectCalibration={handleCorrectCalibration}
              onSearchResponse={handleSearchResponse}
              roleMessage={roleMessage}
              searchNotice={searchNotice}
              onSelectionChange={setCandidateOpen}
            />
          ) : null}
        </div>
      </main>
    </div>
    </GlobalShell>
  )
}
