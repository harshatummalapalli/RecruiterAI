import { useEffect, useRef, useState } from 'react'
import { Pencil } from 'lucide-react'
import {
  runCandidateSearch,
  loadPersistedSearch,
  logout,
  startIntake,
  answerIntake,
  confirmIntake,
} from '../services/recruiterWorkflow'
import {
  briefToSearchIntent,
  briefToLocationDetail,
  createEmptySearchBrief,
  searchIntentToBrief,
  type SearchBrief,
} from '../models/searchBrief'
import type { IntakeIssue, IntakeResult } from '../models/intake'
import { SearchBriefReview } from './SearchBriefReview'
import { CandidateReviewScreen } from './CandidateReviewScreen'
import { DebugPanel } from './DebugPanel'
import { SearchBoundaryForm } from './SearchBoundaryForm'
import { createEmptySearchBoundary, isSearchBoundaryComplete, type SearchBoundary } from '../models/searchBoundary'
import type { SearchResponse } from '../types'
import './RecruiterWorkspaceScreen.css'

type ParseState = 'idle' | 'parsing' | 'success' | 'error'
type Step = 'jd' | 'brief' | 'review'
type SearchState = 'idle' | 'searching' | 'done' | 'error'
type IntakeState = 'idle' | 'loading' | 'answering' | 'confirming' | 'ready' | 'error'

const RECRUITER_NAME = 'Harsha'

// A page refresh must reload the last search, not re-run OpenAI/CrustData.
// The search RESULT lives on the backend (see backend/services/search_store.py);
// this only remembers *which* search to reload, plus enough of the
// recruiter's Search Brief editing state to make "Edit Brief" work
// immediately after a reload without re-deriving it from scratch.
const PERSISTED_SEARCH_KEY = 'recruiterai:lastSearch'

type PersistedSearchPointer = {
  searchId: string
  jdText: string
  brief: SearchBrief
  lockedFields: string[]
}

function savePersistedSearchPointer(pointer: PersistedSearchPointer): void {
  try {
    window.localStorage.setItem(PERSISTED_SEARCH_KEY, JSON.stringify(pointer))
  } catch {
    // Best-effort only — persistence is a convenience, not a correctness requirement.
  }
}

function readPersistedSearchPointer(): PersistedSearchPointer | null {
  try {
    const raw = window.localStorage.getItem(PERSISTED_SEARCH_KEY)
    return raw ? (JSON.parse(raw) as PersistedSearchPointer) : null
  } catch {
    return null
  }
}

function clearPersistedSearchPointer(): void {
  try {
    window.localStorage.removeItem(PERSISTED_SEARCH_KEY)
  } catch {
    // Best-effort only.
  }
}

function getGreeting(hour: number): string {
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

export function RecruiterWorkspaceScreen() {
  const [jdText, setJdText] = useState('')
  const [boundary, setBoundary] = useState<SearchBoundary>(createEmptySearchBoundary)
  const [brief, setBrief] = useState<SearchBrief>(createEmptySearchBrief)
  const [lockedFields, setLockedFields] = useState<ReadonlySet<string>>(new Set())
  const [isEditingTitle, setIsEditingTitle] = useState(false)
  const [parseState, setParseState] = useState<ParseState>('idle')
  const [step, setStep] = useState<Step>('jd')
  const [intakeSessionId, setIntakeSessionId] = useState<string | null>(null)
  const [intakeResult, setIntakeResult] = useState<IntakeResult | null>(null)
  const [intakeState, setIntakeState] = useState<IntakeState>('idle')
  const [hiringCompanyPrefilled, setHiringCompanyPrefilled] = useState(false)
  const [searchState, setSearchState] = useState<SearchState>('idle')
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null)
  const [searchId, setSearchId] = useState<string | null>(null)
  // Bumped once per "Find Candidates"/"Run Search Again" click — lets
  // CandidateReviewScreen reset its open-profile/compare/edit-brief UI
  // state exactly once per NEW search, without resetting on every
  // progressive poll tick of the SAME still-running search (search_id
  // alone doesn't distinguish those: a "Run Search Again" reuses the same
  // search_id).
  const [searchGeneration, setSearchGeneration] = useState(0)
  const titleInputRef = useRef<HTMLInputElement | null>(null)
  // Progressive Candidate Workspace — the poll loop for a running search.
  // Ref (not state) because it's plumbing, not something that should ever
  // trigger a re-render on its own; cleared whenever a new search starts or
  // the component unmounts, so at most one poll loop is ever active.
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const greeting = `${getGreeting(new Date().getHours())}, ${RECRUITER_NAME}.`
  const hasJdText = jdText.trim().length > 0
  const isBoundaryComplete = isSearchBoundaryComplete(boundary)
  const canParse = hasJdText && isBoundaryComplete && parseState !== 'parsing'
  const isBusy = parseState === 'parsing'

  // On mount: if a previous search was persisted, reload it from the
  // backend store and restore straight to Candidate Review — a refresh
  // must never re-run OpenAI or CrustData. Only an explicit "Find
  // Candidates" / "Run Search Again" click (handleFindCandidates) does that.
  useEffect(() => {
    const pointer = readPersistedSearchPointer()
    if (!pointer) {
      return
    }
    let cancelled = false
    void (async () => {
      const response = await loadPersistedSearch(pointer.searchId).catch(() => null)
      if (cancelled || !response) {
        return
      }
      setJdText(pointer.jdText)
      setBrief(pointer.brief)
      setLockedFields(new Set(pointer.lockedFields))
      setSearchId(pointer.searchId)
      setSearchResponse(response)
      setParseState('success')
      setStep('review')
      if (response.status === 'running') {
        // The search was still in progress when the browser was closed/
        // refreshed — resume polling rather than treating it as finished.
        setSearchState('searching')
        pollSearch(pointer.searchId, pointer.brief)
      } else {
        setSearchState(response.status === 'error' ? 'error' : 'done')
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (isEditingTitle) {
      titleInputRef.current?.focus()
      titleInputRef.current?.select()
    }
  }, [isEditingTitle])

  const lockField = (path: string) => {
    setLockedFields((current) => {
      const next = new Set(current)
      next.add(path)
      return next
    })
  }

  const updateBriefField: (path: string, updater: (current: SearchBrief) => SearchBrief) => void = (path, updater) => {
    lockField(path)
    setBrief((current) => updater(current))
  }

  const commitTitleEdit = () => {
    setIsEditingTitle(false)
  }

  // Once intake reaches "ready" (no pending questions/contradictions), turn
  // it into the executable SearchIntent server-side (build_confirmed_hiring_
  // intent + to_search_intent — see backend/services/search_translator.py)
  // and populate the editable Search Brief immediately, so the recruiter
  // sees interpretation and the executable brief together on one screen
  // rather than confirming only at the moment they click Search.
  const confirmAndPopulateBrief = async (sessionId: string) => {
    setIntakeState('confirming')
    try {
      const confirmedIntent = await confirmIntake(sessionId)
      setBrief(searchIntentToBrief(confirmedIntent))
      setHiringCompanyPrefilled(Boolean(confirmedIntent.company_preferences?.exclude_current_companies?.length))
      setIntakeState('ready')
    } catch {
      setIntakeState('error')
    }
  }

  // RecruiterAI understands the role before searching: submit the raw input
  // to the backend intake reasoning layer (Task A / Task B / contradiction
  // backstop — see backend/services/intake_reasoning.py) and show the
  // Search Brief. No local heuristic decides what to ask any more; the
  // backend is the sole authority on ambiguity/questions.
  const handleParse = async () => {
    if (!hasJdText || !isBoundaryComplete) {
      return
    }

    setParseState('parsing')
    setIntakeState('loading')
    setHiringCompanyPrefilled(false)
    try {
      const { session_id, result } = await startIntake(jdText, boundary)
      setIntakeSessionId(session_id)
      setIntakeResult(result)
      setParseState('success')
      setStep('brief')
      if (result.status === 'ready') {
        await confirmAndPopulateBrief(session_id)
      } else {
        setIntakeState('idle')
      }
    } catch {
      setParseState('error')
      setIntakeState('error')
    }
  }

  const handleAnswerIntake = async (issue: IntakeIssue, value: string, label: string) => {
    if (!intakeSessionId || !issue.id) {
      return
    }
    setIntakeState('answering')
    try {
      const { result } = await answerIntake(intakeSessionId, issue.id, value, label)
      setIntakeResult(result)
      if (result.status === 'ready') {
        await confirmAndPopulateBrief(intakeSessionId)
      } else {
        setIntakeState('idle')
      }
    } catch {
      setIntakeState('error')
    }
  }

  // Progressive Candidate Workspace: POST /search now returns almost
  // immediately with status="running" — the actual CrustData/Harvest
  // pipeline runs on a backend background thread (see backend/services/
  // search_pipeline.py). This polls GET /search/{id} every 1.5s and
  // updates the on-screen candidate list as candidates move SURFACED ->
  // BUILDING_CONTEXT -> REVIEW_READY, stopping once the search leaves
  // "running" (complete/error/interrupted).
  const POLL_INTERVAL_MS = 1500

  const stopPolling = () => {
    if (pollTimeoutRef.current !== null) {
      clearTimeout(pollTimeoutRef.current)
      pollTimeoutRef.current = null
    }
  }

  const pollSearch = (id: string, activeBrief: SearchBrief) => {
    stopPolling()
    // One failed or empty poll (a network blip, a deploy restart) must not end
    // the loop: it would leave the workspace frozen mid-search with no error.
    // Retry a few times, then surface the error state.
    let consecutiveFailures = 0
    const tick = async () => {
      const response = await loadPersistedSearch(id).catch(() => null)
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
      savePersistedSearchPointer({
        searchId: id,
        jdText,
        brief: activeBrief,
        lockedFields: Array.from(lockedFields),
      })
    }
    void tick()
  }

  const handleFindCandidates = async (briefOverride?: SearchBrief) => {
    const activeBrief = briefOverride ?? brief
    setSearchState('searching')
    setSearchGeneration((current) => current + 1)
    stopPolling()

    try {
      const response = await runCandidateSearch(
        jdText,
        briefToSearchIntent(activeBrief),
        briefToLocationDetail(activeBrief),
        {
          searchId: searchId ?? undefined,
          debug: import.meta.env.DEV,
        },
      )
      // The search has already started server-side — show the workspace
      // immediately (0 candidates, "running") rather than waiting for the
      // whole pipeline; polling fills it in progressively.
      setSearchResponse(response)
      setStep('review')
      setSearchId(response.search_id)
      pollSearch(response.search_id, activeBrief)
    } catch {
      setSearchState('error')
    }
  }

  useEffect(() => stopPolling, [])

  // Persistence means a page load always restores the last search — this is
  // the only way back to a blank slate. Clears the pointer (not the backend
  // record itself, which stays reloadable by its old URL/id) and resets to
  // the JD step.
  const handleStartNewSearch = () => {
    clearPersistedSearchPointer()
    setJdText('')
    setBoundary(createEmptySearchBoundary())
    setBrief(createEmptySearchBrief())
    setLockedFields(new Set())
    setParseState('idle')
    setStep('jd')
    setIntakeSessionId(null)
    setIntakeResult(null)
    setIntakeState('idle')
    setHiringCompanyPrefilled(false)
    setSearchState('idle')
    setSearchResponse(null)
    setSearchId(null)
  }

  // Candidate Review is contextual to the active search, not a generic
  // greeting — the recruiter is deep into one role by that point, and the
  // header's job shifts from "what are you hiring for" to "how is this
  // search going" (see backend's progress: admitted/surfaced/
  // building_context/review_ready counts, populated progressively).
  const progress = searchResponse?.progress
  const workspaceSubtitle = (() => {
    if (!progress || !progress.admitted) {
      return searchState === 'searching' ? 'Finding candidates…' : 'What are you hiring for today?'
    }
    const parts = [`${progress.admitted} candidate${progress.admitted === 1 ? '' : 's'} selected`]
    if (progress.review_ready) parts.push(`${progress.review_ready} ready for review`)
    if (progress.building_context) parts.push(`${progress.building_context} building context`)
    if (progress.surfaced) parts.push(`${progress.surfaced} surfaced`)
    return parts.join(' · ')
  })()

  return (
    <main className="workspace">
      <div className="workspace__content">
        <header className="workspace__greeting">
          {step === 'review' ? (
            <div>
              <h1>{brief.role.primaryTitle || 'Candidate Workspace'}</h1>
              <p>{workspaceSubtitle}</p>
            </div>
          ) : (
            <div>
              <h1>{greeting}</h1>
              <p>What are you hiring for today?</p>
            </div>
          )}
          <div style={{ display: 'flex', gap: 8 }}>
            {step !== 'jd' ? (
              <button type="button" className="workspace__new-search" onClick={handleStartNewSearch}>
                Start New Search
              </button>
            ) : null}
            <button
              type="button"
              className="workspace__new-search"
              onClick={() => {
                logout().finally(() => window.location.reload())
              }}
            >
              Sign out
            </button>
          </div>
        </header>

        {step === 'jd' ? (
          <div className="workspace__grid workspace__grid--single">
            <section className="workspace__composer" aria-label="Job description composer">
              <div className="workspace__title-row">
                {isEditingTitle ? (
                  <input
                    ref={titleInputRef}
                    className="workspace__title-input"
                    type="text"
                    value={brief.role.primaryTitle}
                    onChange={(event) => updateBriefField('role.primaryTitle', (current) => ({ ...current, role: { ...current.role, primaryTitle: event.target.value } }))}
                    onBlur={commitTitleEdit}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault()
                        commitTitleEdit()
                      }
                    }}
                    placeholder="Untitled role"
                    aria-label="Role title"
                  />
                ) : (
                  <button
                    type="button"
                    className="workspace__title-display"
                    onClick={() => setIsEditingTitle(true)}
                    aria-label="Edit role title"
                  >
                    <span className={brief.role.primaryTitle ? '' : 'workspace__title-display--placeholder'}>
                      {brief.role.primaryTitle || 'Untitled role'}
                    </span>
                    <Pencil size={15} className="workspace__title-pencil" aria-hidden="true" />
                  </button>
                )}
              </div>

              <SearchBoundaryForm
                boundary={boundary}
                onChange={(updater) => setBoundary(updater)}
                disabled={isBusy}
              />

              <textarea
                className="workspace__editor"
                value={jdText}
                onChange={(event) => setJdText(event.target.value)}
                placeholder="What are you hiring for? Paste the full job description, rough hiring-manager notes, or just describe the role in your own words."
                disabled={isBusy}
                aria-label="Job description"
                rows={16}
              />

              <div className="workspace__composer-foot">
                <span className="workspace__char-count">
                  {jdText.length > 0 ? `${jdText.length.toLocaleString()} characters` : ''}
                </span>

                <div className="workspace__actions">
                  <div className="workspace__status-slot" aria-live="polite">
                    {parseState === 'success' ? (
                      <p className="workspace__status workspace__status--success">
                        <span aria-hidden="true">✓</span> Job description understood successfully.
                      </p>
                    ) : null}

                    {parseState === 'error' ? (
                      <div className="workspace__status workspace__status--error" role="alert">
                        <p>Unable to understand this job description.</p>
                        <button type="button" className="workspace__retry" onClick={handleParse}>
                          Retry
                        </button>
                      </div>
                    ) : null}
                  </div>

                  <button
                    type="button"
                    className={`workspace__parse${isBusy ? ' workspace__parse--busy' : ''}`}
                    onClick={handleParse}
                    disabled={!canParse}
                  >
                    {isBusy ? (
                      <>
                        <span className="workspace__spinner" aria-hidden="true" />
                        <span>Understanding the role…</span>
                      </>
                    ) : (
                      <span>Build Search Brief</span>
                    )}
                  </button>
                </div>
              </div>
            </section>
          </div>
        ) : null}

        {step === 'brief' && intakeResult ? (
          <SearchBriefReview
            brief={brief}
            onChange={updateBriefField}
            onFindCandidates={() => handleFindCandidates()}
            onBackToJd={() => setStep('jd')}
            isSearching={searchState === 'searching'}
            searchState={searchState}
            intakeContext={{
              result: intakeResult,
              onAnswer: handleAnswerIntake,
              isAnswering: intakeState === 'answering',
              hiringCompanyPrefilled,
              boundary,
            }}
          />
        ) : null}

        {step === 'review' ? (
          <CandidateReviewScreen
            brief={brief}
            onChangeBrief={updateBriefField}
            searchResponse={searchResponse}
            searchState={searchState}
            onRunSearch={() => handleFindCandidates()}
            searchId={searchId}
            searchGeneration={searchGeneration}
          />
        ) : null}

        <DebugPanel jdText={jdText} brief={brief} searchResponse={searchResponse} />
      </div>
    </main>
  )
}
