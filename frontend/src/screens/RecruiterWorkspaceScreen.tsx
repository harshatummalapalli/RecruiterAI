import { useEffect, useRef, useState } from 'react'
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
} from '../services/recruiterWorkflow'
import { createEmptySearchBrief, searchIntentToBrief, type SearchBrief } from '../models/searchBrief'
import { diffBriefEdits, formatBoundaryLocation } from '../models/livingBrief'
import type { IntakeIssue, IntakeResult } from '../models/intake'
import { CandidateReviewScreen } from './CandidateReviewScreen'
import { DebugPanel } from './DebugPanel'
import { LivingBrief } from './LivingBrief'
import { SearchBoundaryForm } from './SearchBoundaryForm'
import { createEmptySearchBoundary, isSearchBoundaryComplete, type SearchBoundary } from '../models/searchBoundary'
import type { SearchResponse } from '../types'
import './RecruiterWorkspaceScreen.css'

type ParseState = 'idle' | 'parsing' | 'success' | 'error'
type Step = 'jd' | 'brief' | 'review'
type SearchState = 'idle' | 'searching' | 'done' | 'error'

const RECRUITER_NAME = 'Harsha'

// A page refresh must reload the last search, not re-run OpenAI/CrustData.
// The search RESULT lives on the backend (see backend/services/search_store.py);
// this only remembers *which* search to reload, which intake session it came
// from, and the recruiter's working copy of the adjustable brief.
const PERSISTED_SEARCH_KEY = 'recruiterai:lastSearch'

type PersistedSearchPointer = {
  searchId: string
  jdText: string
  brief: SearchBrief
  intakeSessionId?: string | null
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
  const [step, setStep] = useState<Step>('jd')
  const [intakeSessionId, setIntakeSessionId] = useState<string | null>(null)
  const [intakeResult, setIntakeResult] = useState<IntakeResult | null>(null)
  const [isAnswering, setIsAnswering] = useState(false)
  const [searchState, setSearchState] = useState<SearchState>('idle')
  const [searchErrors, setSearchErrors] = useState<string[]>([])
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null)
  const [searchId, setSearchId] = useState<string | null>(null)
  // Bumped once per search start — lets CandidateReviewScreen reset its open-record/edit-brief UI state exactly once
  // per NEW search, without resetting on every progressive poll tick of the SAME still-running search.
  const [searchGeneration, setSearchGeneration] = useState(0)
  // Progressive Candidate Workspace — the poll loop for a running search. A ref because it is plumbing, cleared when a
  // new search starts or the component unmounts, so at most one poll loop is ever active.
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const greeting = `${getGreeting(new Date().getHours())}, ${RECRUITER_NAME}.`
  const hasJdText = jdText.trim().length > 0
  const isBoundaryComplete = isSearchBoundaryComplete(boundary)
  const canParse = hasJdText && isBoundaryComplete && parseState !== 'parsing'
  const isBusy = parseState === 'parsing'

  // What the server proposed for this brief, shown in the adjustable panel and used as the baseline for real edits.
  const refreshProposal = async (sessionId: string) => {
    try {
      const proposed = searchIntentToBrief(await confirmIntake(sessionId))
      setBrief(proposed)
      setBaselineBrief(proposed)
    } catch {
      // Only reachable while a question is open; the brief is not ready, so there is nothing to propose yet.
    }
  }

  // On mount: if a previous search was persisted, reload it from the backend store and restore straight to Candidate
  // Review — a refresh must never re-run OpenAI or CrustData. The intake session it came from is resumed read-only, so
  // the boundary can still be edited and the brief re-confirmed.
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
      setSearchId(pointer.searchId)
      setSearchResponse(response)
      setParseState('success')
      setStep('review')
      if (response.status === 'running') {
        setSearchState('searching')
        pollSearch(pointer.searchId, pointer.brief, pointer.intakeSessionId ?? null)
      } else {
        setSearchState(response.status === 'error' ? 'error' : 'done')
      }

      const sessionId = response.confirmed_brief?.session_id ?? pointer.intakeSessionId ?? null
      if (sessionId) {
        const session = await loadIntakeSession(sessionId).catch(() => null)
        if (cancelled || !session) return
        setIntakeSessionId(sessionId)
        setIntakeResult(session.result)
        if (session.boundary) setBoundary(session.boundary)
        if (session.posted_title_input) setPostedTitle(session.posted_title_input)
        try {
          setBaselineBrief(searchIntentToBrief(await confirmIntake(sessionId)))
        } catch {
          // The baseline is only needed to send edits; without it the brief is re-confirmed as the server proposes it.
        }
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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

  // Progressive Candidate Workspace: POST /search returns almost immediately with status="running" — the actual
  // pipeline runs on a backend background thread. This polls GET /search/{id} every 1.5s and updates the list as
  // candidates move SURFACED -> BUILDING_CONTEXT -> REVIEW_READY, stopping once the search leaves "running".
  const POLL_INTERVAL_MS = 1500

  const stopPolling = () => {
    if (pollTimeoutRef.current !== null) {
      clearTimeout(pollTimeoutRef.current)
      pollTimeoutRef.current = null
    }
  }

  const pollSearch = (id: string, activeBrief: SearchBrief, sessionId: string | null) => {
    stopPolling()
    // One failed or empty poll (a network blip, a deploy restart) must not end the loop: it would leave the workspace
    // frozen mid-search with no error. Retry a few times, then surface the error state.
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
      savePersistedSearchPointer({ searchId: id, jdText, brief: activeBrief, intakeSessionId: sessionId })
    }
    void tick()
  }

  // The recruiter presses Search. The server checks that the brief is ready, builds the executable search itself from
  // what was confirmed (plus only the edits made here), and stores it. The browser never supplies the search.
  const handleSearch = async (briefOverride?: SearchBrief) => {
    if (!intakeSessionId) {
      setSearchErrors(['This search has no brief to confirm. Start a new search.'])
      return
    }
    const activeBrief = briefOverride ?? brief
    setSearchState('searching')
    setSearchErrors([])
    stopPolling()

    try {
      const confirmation = await createConfirmation(intakeSessionId, baselineBrief ? diffBriefEdits(baselineBrief, activeBrief) : {})
      setSearchGeneration((current) => current + 1)
      const response = await runCandidateSearch(confirmation.confirmation_id, { searchId: searchId ?? undefined, debug: import.meta.env.DEV })
      // The search has already started server-side — show the workspace immediately (0 candidates, "running") rather
      // than waiting for the whole pipeline; polling fills it in progressively.
      setSearchResponse(response)
      setStep('review')
      setSearchId(response.search_id)
      pollSearch(response.search_id, activeBrief, intakeSessionId)
    } catch (error) {
      // A refusal (open questions, an incomplete boundary) is explained in plain words; anything else is an error.
      const explained = (error as { messages?: string[] } | null)?.messages
      setSearchErrors(explained ?? ['The search could not be started. Please try again.'])
      setSearchState(step === 'review' ? 'error' : 'idle')
    }
  }

  useEffect(() => stopPolling, [])

  // Persistence means a page load always restores the last search — this is the only way back to a blank slate.
  // Clears the pointer (not the backend record itself, which stays reloadable by its old id) and resets to the first step.
  const handleStartNewSearch = () => {
    clearPersistedSearchPointer()
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
  }

  // Candidate Review is contextual to the active search: the header names the ROLE as it was posted, and shows what
  // is actually being searched for separately, so the AI's reading never looks like the posted title.
  const confirmed = searchResponse?.confirmed_brief
  const posted = confirmed?.posted_title ?? intakeResult?.role_understanding.posted_title ?? (postedTitle.trim() || null)
  const identity = confirmed?.candidate_identity ?? brief.role.primaryTitle ?? ''
  const showIdentity = Boolean(posted && identity && !sameTitle(posted, identity))

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
              <h1>{posted || identity || 'Candidate Workspace'}</h1>
              {showIdentity ? (
                <p className="workspace__identity">
                  <span className="workspace__identity-label">Searching for</span> {identity}
                </p>
              ) : null}
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
              <div className="brief-field workspace__title-field">
                <label className="brief-field__label" htmlFor="posted-title">
                  Role title <span className="workspace__optional">optional</span>
                </label>
                <input
                  id="posted-title"
                  type="text"
                  className="brief-input"
                  value={postedTitle}
                  disabled={isBusy}
                  placeholder="Exactly as the role is called, e.g. AI Engineer"
                  onChange={(event) => setPostedTitle(event.target.value)}
                />
                <span className="boundary-form__caption">Kept exactly as you type it. Leave it blank and the title in the description is used.</span>
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
            boundaryLimitation={intakeResult?.decision.limitations?.[0] ?? null}
            searchErrors={searchErrors}
          />
        ) : null}

        <DebugPanel jdText={jdText} brief={brief} searchResponse={searchResponse} />
      </div>
    </main>
  )
}
