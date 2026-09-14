import { useEffect, useRef, useState } from 'react'
import { Pencil } from 'lucide-react'
import { parseJobDescription, runCandidateSearch, loadPersistedSearch } from '../services/recruiterWorkflow'
import {
  applyAiParse,
  applyClarificationAnswer,
  applyLocalExtraction,
  briefToSearchIntent,
  briefToLocationDetail,
  createEmptySearchBrief,
  CLARIFICATION_LOCK_PATHS,
  type SearchBrief,
} from '../models/searchBrief'
import { buildClarificationQuestions, type ClarificationQuestion } from '../models/clarification'
import { SearchBriefReview } from './SearchBriefReview'
import { ClarificationReview } from './ClarificationReview'
import { CandidateReviewScreen } from './CandidateReviewScreen'
import { DebugPanel } from './DebugPanel'
import type { SearchResponse } from '../types'
import './RecruiterWorkspaceScreen.css'

type ParseState = 'idle' | 'parsing' | 'success' | 'error'
type Step = 'jd' | 'clarify' | 'brief' | 'review'
type SearchState = 'idle' | 'searching' | 'done' | 'error'

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

function formatExperience(minimumYears: string, maximumYears: string): string | null {
  if (!minimumYears && !maximumYears) return null
  if (minimumYears && maximumYears) return `${minimumYears}–${maximumYears} years`
  if (minimumYears) return `${minimumYears}+ years`
  return `Up to ${maximumYears} years`
}

function formatLocations(brief: SearchBrief): string | null {
  if (!brief.location.locations.length) return null
  const labels = brief.location.locations
    .map((entry) => [entry.city, entry.state, entry.country].filter((part) => part.trim()).join(', '))
    .filter(Boolean)
  return labels.length ? labels.join(' · ') : null
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function PreviewRow({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="workspace__preview-row">
      <dt>{label}</dt>
      <dd className={value ? '' : 'workspace__preview-value--empty'}>{value ?? 'Not detected yet'}</dd>
    </div>
  )
}

export function RecruiterWorkspaceScreen() {
  const [jdText, setJdText] = useState('')
  const [brief, setBrief] = useState<SearchBrief>(createEmptySearchBrief)
  const [lockedFields, setLockedFields] = useState<ReadonlySet<string>>(new Set())
  const [isEditingTitle, setIsEditingTitle] = useState(false)
  const [parseState, setParseState] = useState<ParseState>('idle')
  const [step, setStep] = useState<Step>('jd')
  const [clarificationQuestions, setClarificationQuestions] = useState<ClarificationQuestion[]>([])
  const [clarificationAnswers, setClarificationAnswers] = useState<Record<string, string>>({})
  const [searchState, setSearchState] = useState<SearchState>('idle')
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null)
  const [searchId, setSearchId] = useState<string | null>(null)
  const titleInputRef = useRef<HTMLInputElement | null>(null)

  const greeting = `${getGreeting(new Date().getHours())}, ${RECRUITER_NAME}.`
  const hasJdText = jdText.trim().length > 0
  const canParse = hasJdText && parseState !== 'parsing'
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
      setSearchState('done')
      setParseState('success')
      setStep('review')
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Stage 1 — local extraction. Recomputes on every keystroke and writes
  // straight into the canonical SearchBrief; fields the recruiter has
  // manually edited are locked and left untouched.
  useEffect(() => {
    if (step !== 'jd') {
      return
    }
    setBrief((current) => applyLocalExtraction(current, jdText, lockedFields))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jdText, step])

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

  // Confidence assessment. If the JD is unambiguous, skip straight to the AI
  // parse and the Search Brief. Otherwise, ask only the minimum structured
  // clarifying questions first — never more than five, never free text.
  const handleParse = async () => {
    if (!hasJdText) {
      return
    }

    const questions = buildClarificationQuestions(jdText)
    if (questions.length > 0) {
      setClarificationQuestions(questions)
      setClarificationAnswers({})
      setStep('clarify')
      return
    }

    await generateSearchBrief()
  }

  const handleAnswerClarification = (questionId: string, value: string) => {
    setClarificationAnswers((current) => ({ ...current, [questionId]: value }))
  }

  // Stage 2 — AI parse. Enriches the existing SearchBrief in place rather
  // than replacing it; locked (recruiter-edited) fields are left alone.
  // Clarification answers, if any, are applied last so nothing overwrites them.
  const generateSearchBrief = async () => {
    setParseState('parsing')

    try {
      const intent = await parseJobDescription(jdText)
      let nextBrief = applyAiParse(brief, intent, lockedFields)
      const newlyLocked = new Set(lockedFields)

      for (const question of clarificationQuestions) {
        const answer = clarificationAnswers[question.id]
        if (!answer) {
          continue
        }
        nextBrief = applyClarificationAnswer(nextBrief, question.id, answer)
        for (const path of CLARIFICATION_LOCK_PATHS[question.id] ?? []) {
          newlyLocked.add(path)
        }
      }

      setBrief(nextBrief)
      setLockedFields(newlyLocked)
      setParseState('success')
      setSearchState('idle')
      setStep('brief')
    } catch {
      setParseState('error')
    }
  }

  const handleFindCandidates = async () => {
    setSearchState('searching')

    try {
      const response = await runCandidateSearch(jdText, briefToSearchIntent(brief), briefToLocationDetail(brief), {
        searchId: searchId ?? undefined,
        debug: import.meta.env.DEV,
      })
      setSearchResponse(response)
      setSearchState('done')
      setStep('review')
      setSearchId(response.search_id)
      savePersistedSearchPointer({
        searchId: response.search_id,
        jdText,
        brief,
        lockedFields: Array.from(lockedFields),
      })
    } catch {
      setSearchState('error')
    }
  }

  // Persistence means a page load always restores the last search — this is
  // the only way back to a blank slate. Clears the pointer (not the backend
  // record itself, which stays reloadable by its old URL/id) and resets to
  // the JD step.
  const handleStartNewSearch = () => {
    clearPersistedSearchPointer()
    setJdText('')
    setBrief(createEmptySearchBrief())
    setLockedFields(new Set())
    setParseState('idle')
    setStep('jd')
    setClarificationQuestions([])
    setClarificationAnswers({})
    setSearchState('idle')
    setSearchResponse(null)
    setSearchId(null)
  }

  const locationText = formatLocations(brief)
  const experienceText = formatExperience(brief.experience.minimumYears, brief.experience.maximumYears)
  const requiredSkillsText = brief.skills.required.length ? brief.skills.required.join(', ') : null
  const preferredSkillsText = brief.skills.preferred.length ? brief.skills.preferred.join(', ') : null

  return (
    <main className="workspace">
      <div className="workspace__content">
        <header className="workspace__greeting">
          <div>
            <h1>{greeting}</h1>
            <p>What are you hiring for today?</p>
          </div>
          {step !== 'jd' ? (
            <button type="button" className="workspace__new-search" onClick={handleStartNewSearch}>
              Start New Search
            </button>
          ) : null}
        </header>

        {step === 'jd' ? (
          <div className="workspace__grid">
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

              <textarea
                className="workspace__editor"
                value={jdText}
                onChange={(event) => setJdText(event.target.value)}
                placeholder="Paste a job description or simply describe the role in your own words…"
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

            <aside className="workspace__preview" aria-label="Live preview">
              <p className="workspace__preview-label">Live preview</p>

              {hasJdText ? (
                <dl className="workspace__preview-list">
                  <PreviewRow label="Role title" value={brief.role.primaryTitle || null} />
                  <PreviewRow label="Location" value={locationText} />
                  <PreviewRow
                    label="Work mode"
                    value={brief.location.workModes.length ? brief.location.workModes.map(capitalize).join(', ') : null}
                  />
                  <PreviewRow label="Experience" value={experienceText} />
                  <PreviewRow label="Required skills" value={requiredSkillsText} />
                  <PreviewRow label="Preferred skills" value={preferredSkillsText} />
                  <PreviewRow
                    label="Employment type"
                    value={brief.employmentTypes.length ? brief.employmentTypes.join(', ') : null}
                  />
                </dl>
              ) : (
                <p className="workspace__preview-empty">Start typing to see a live preview.</p>
              )}
            </aside>
          </div>
        ) : null}

        {step === 'clarify' ? (
          <ClarificationReview
            questions={clarificationQuestions}
            answers={clarificationAnswers}
            onAnswer={handleAnswerClarification}
            onGenerate={generateSearchBrief}
            onBackToJd={() => {
              setClarificationQuestions([])
              setClarificationAnswers({})
              setStep('jd')
            }}
            isGenerating={parseState === 'parsing'}
          />
        ) : null}

        {step === 'brief' ? (
          <SearchBriefReview
            brief={brief}
            onChange={updateBriefField}
            onFindCandidates={handleFindCandidates}
            onBackToJd={() => setStep('jd')}
            isSearching={searchState === 'searching'}
            searchState={searchState}
          />
        ) : null}

        {step === 'review' ? (
          <CandidateReviewScreen
            brief={brief}
            onChangeBrief={updateBriefField}
            searchResponse={searchResponse}
            searchState={searchState}
            onRunSearch={handleFindCandidates}
            searchId={searchId}
          />
        ) : null}

        <DebugPanel jdText={jdText} brief={brief} searchResponse={searchResponse} />
      </div>
    </main>
  )
}
