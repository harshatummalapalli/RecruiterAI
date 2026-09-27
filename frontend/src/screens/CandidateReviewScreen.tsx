import { useEffect, useMemo, useRef, useState } from 'react'
import { Pencil, Upload } from 'lucide-react'
import type { SearchBrief } from '../models/searchBrief'
import type { SearchResponse } from '../types'
import { buildDiscoveryCandidates, emailStatusLine, phoneStatusLine } from '../models/discovery'
import {
  buildWorkspaceCandidates,
  funnelCopy,
  normalizeDecision,
  readFunnel,
  stableOrder,
  type Decision,
} from '../models/workspace'
import { CandidateRecord } from '../components/CandidateRecord'
import { CandidateWorkspace } from '../components/CandidateWorkspace'
import { AvailabilityNotice, CalibrationNote, NewCandidatesNotice, OtherReviewed, PausedPanel, RoleBar, ShowMoreBar } from '../components/RoleControls'
import {
  availabilityNotice,
  calibrationNote,
  isRoleSearch,
  newCandidatesNotice,
  orderPresented,
  ROLE_ORDER_NOTE,
  pauseCopy,
  reviewHeading,
  splitByPresentation,
  type PauseAction,
} from '../models/roleWorkspace'
import { updateCandidateRecord } from '../services/recruiterWorkflow'
import { BoundaryEditor } from '../components/BoundaryEditor'
import { formatBoundaryLocation, workModeLabel } from '../models/livingBrief'
import type { SearchBoundary } from '../models/searchBoundary'
import { SearchBriefReview, summarizeCompanies, summarizeExperience, summarizeSkills } from './SearchBriefReview'

type FieldChange = (path: string, updater: (current: SearchBrief) => SearchBrief) => void

type SearchState = 'idle' | 'searching' | 'done' | 'error'

type CandidateReviewScreenProps = {
  brief: SearchBrief
  onChangeBrief: FieldChange
  searchResponse: SearchResponse | null
  searchState: SearchState
  onRunSearch: () => void
  searchId: string | null
  // The Search Boundary is the single source for where and work mode. Null only when the brief this search came from
  // could not be resumed, in which case it is shown as unavailable rather than editable.
  boundary: SearchBoundary | null
  onApplyBoundary: (boundary: SearchBoundary) => Promise<void>
  boundaryLimitation?: string | null
  // Why the last attempt to search again was refused, in plain sentences.
  searchErrors?: string[]
  // Bumped once per "Find Candidates"/"Run Search Again" click — see
  // RecruiterWorkspaceScreen.tsx. Drives the open-profile/compare/edit-brief
  // UI reset without resetting on every progressive poll tick.
  searchGeneration: number
  // Roles (multiple searches). Optional so the screen still renders a search stored before roles existed.
  onShowMore?: (onlyNew?: boolean) => Promise<void>
  onRoleAction?: (action: 'pause' | 'resume') => Promise<void>
  onCorrectCalibration?: (dismiss: string[]) => Promise<void>
  // The server's answer to a saved decision or reason, so the role, feedback and calibration stay current.
  onSearchResponse?: (response: SearchResponse) => void
  // Why the last request to show more or change the role was refused, in plain words.
  roleMessage?: string | null
  // Set when a re-run changed nothing that is searched, so nothing was run.
  searchNotice?: string | null
}

type Note = { id: string; text: string; createdAt: string }
type Resume = { name: string; uploadedAt: string }

function SkeletonRows() {
  return (
    <div className="discovery-list" aria-hidden="true">
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={index} className="candidate-row candidate-row--skeleton">
          <div className="discovery-skeleton discovery-skeleton--wide" />
          <div className="discovery-skeleton" />
          <div className="discovery-skeleton discovery-skeleton--narrow" />
        </div>
      ))}
    </div>
  )
}

export function CandidateReviewScreen({
  brief,
  onChangeBrief,
  searchResponse,
  searchState,
  onRunSearch,
  searchId,
  searchGeneration,
  boundary,
  onApplyBoundary,
  boundaryLimitation = null,
  searchErrors = [],
  onShowMore,
  onRoleAction,
  onCorrectCalibration,
  onSearchResponse,
  roleMessage = null,
  searchNotice = null,
}: CandidateReviewScreenProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [isEditingBrief, setIsEditingBrief] = useState(false)
  const [decisions, setDecisions] = useState<Record<string, Decision | undefined>>({})
  const [resumes, setResumes] = useState<Record<string, Resume>>({})
  const [notes, setNotes] = useState<Record<string, Note[]>>({})
  const [noteDraft, setNoteDraft] = useState('')
  const [roleBusy, setRoleBusy] = useState(false)
  const [pauseDismissed, setPauseDismissed] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  // Choices made here that the server has not confirmed yet. A poll that lands between a click and its save must not
  // flip the card back, so these are laid over whatever the server returns until it agrees.
  const pendingDecisions = useRef<Record<string, Decision | null>>({})
  // The order candidates first arrived in, kept for the whole search. The server re-orders its own list once when the
  // search finishes; the workspace does not follow that until the recruiter chooses to group.
  const arrivalOrder = useRef<{ generation: number; ids: string[] }>({ generation: searchGeneration, ids: [] })

  // Progressive Candidate Workspace: searchResponse updates repeatedly (once per poll tick) while the SAME search is
  // still running, so the open-record/edit-brief reset is keyed to a NEW search (searchGeneration), not to every update.
  useEffect(() => {
    setSelectedId(null)
    setIsEditingBrief(false)
    setPauseDismissed(false)
    pendingDecisions.current = {}
  }, [searchGeneration, searchId])

  useEffect(() => {
    // Hydrate from whatever the backend already has persisted for this search (decisions and notes are keyed by the
    // stable candidate_id), then lay unconfirmed local choices on top. Re-applying on every poll tick is harmless.
    const hydrated: Record<string, Decision | undefined> = {}
    for (const [candidateId, value] of Object.entries(searchResponse?.recruiter_decisions ?? {})) {
      hydrated[candidateId] = normalizeDecision(value)
    }
    for (const [candidateId, pending] of Object.entries(pendingDecisions.current)) {
      if ((hydrated[candidateId] ?? null) === pending) delete pendingDecisions.current[candidateId]
      else hydrated[candidateId] = pending ?? undefined
    }
    setDecisions(hydrated)

    const notesRecord = searchResponse?.notes ?? {}
    const hydratedNotes: Record<string, Note[]> = {}
    for (const [candidateId, entries] of Object.entries(notesRecord)) {
      hydratedNotes[candidateId] = entries.map((entry, index) => ({
        id: `${candidateId}-${index}`,
        text: entry.text,
        createdAt: entry.created_at,
      }))
    }
    setNotes(hydratedNotes)
  }, [searchResponse])

  const candidates = useMemo(() => (searchResponse ? buildDiscoveryCandidates(searchResponse) : []), [searchResponse])
  const allItems = useMemo(() => buildWorkspaceCandidates(candidates), [candidates])
  // For a role only what the server presented is on screen; everything else it read is kept below. A search stored
  // before roles existed presents everything, exactly as before.
  const { presented: arrangedItems, reserve: reserveItems } = useMemo(() => splitByPresentation(allItems, searchResponse), [allItems, searchResponse])
  const flatItems = useMemo(() => {
    if (isRoleSearch(searchResponse)) return orderPresented(arrangedItems, searchResponse)
    if (arrivalOrder.current.generation !== searchGeneration) {
      arrivalOrder.current = { generation: searchGeneration, ids: [] }
    }
    arrivalOrder.current.ids = stableOrder(arrivalOrder.current.ids, arrangedItems.map((item) => item.candidate.id))
    const byId = new Map(arrangedItems.map((item) => [item.candidate.id, item]))
    return arrivalOrder.current.ids.map((id) => byId.get(id)).filter((item): item is (typeof arrangedItems)[number] => Boolean(item))
  }, [arrangedItems, searchGeneration, searchResponse])
  const selectedCandidate = candidates.find((candidate) => candidate.id === selectedId) ?? null

  const progress = searchResponse?.progress
  const isRole = isRoleSearch(searchResponse)
  const role = searchResponse?.role ?? null
  // While a later cycle runs, the candidates already on screen stay as they are; only the first read shows progress.
  const running = searchState === 'searching' && progress?.admitted && !(isRole && arrangedItems.length > 0) ? { read: progress.review_ready ?? 0, total: progress.admitted } : null
  const funnel = !running && arrangedItems.length > 0 ? funnelCopy(readFunnel(searchResponse?.diagnostics), isRole ? (searchResponse?.candidate_count ?? candidates.length) : candidates.length) : null

  const saved = (response: SearchResponse | undefined) => {
    // The server's answer keeps the role, feedback and the one-time summary current. Anything else is ignored.
    if (response && typeof response === 'object' && 'search_id' in response) onSearchResponse?.(response)
  }

  const decide = (id: string, next: Decision | undefined) => {
    pendingDecisions.current[id] = next ?? null
    setDecisions((current) => ({ ...current, [id]: next }))
    if (searchId) {
      // An empty decision clears it on the server.
      updateCandidateRecord(searchId, id, { decision: next ?? '' })
        .then(saved)
        .catch(() => {})
    }
  }

  const giveFeedback = (id: string, update: { reason?: string; note?: string }) => {
    if (!searchId) return
    updateCandidateRecord(searchId, id, { feedback_reason: update.reason, feedback_note: update.note })
      .then(saved)
      .catch(() => {})
  }

  const runRoleAction = async (task: () => Promise<void> | undefined) => {
    setRoleBusy(true)
    try {
      await task()
    } finally {
      setRoleBusy(false)
    }
  }

  const onPauseAction = (action: PauseAction | 'keep_paused') => {
    if (action === 'keep_paused') setPauseDismissed(true)
    else if (action === 'criteria') setIsEditingBrief(true)
    else if (action === 'resume') void runRoleAction(() => onRoleAction?.('resume'))
    else if (action === 'more') void runRoleAction(() => onShowMore?.())
    else document.getElementById('role-candidates')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const toggleDecision = (id: string, choice: Decision) => decide(id, decisions[id] === choice ? undefined : choice)

  const uploadResume = (id: string, file: File) => {
    setResumes((current) => ({ ...current, [id]: { name: file.name, uploadedAt: new Date().toISOString() } }))
  }

  const addNote = (id: string) => {
    const text = noteDraft.trim()
    if (!text) return
    setNotes((current) => ({
      ...current,
      [id]: [...(current[id] ?? []), { id: `${Date.now()}`, text, createdAt: new Date().toISOString() }],
    }))
    if (searchId) {
      updateCandidateRecord(searchId, id, { note: text }).catch(() => {})
    }
    setNoteDraft('')
  }

  const hasSearchedOnce = searchResponse !== null
  // The skeleton is only for the brief window before the FIRST candidates are admitted.
  const showSkeleton = searchState === 'searching' && (isRole ? arrangedItems.length === 0 : candidates.length === 0)
  const showZeroResults = searchState === 'done' && hasSearchedOnce && candidates.length === 0
  const showError = searchState === 'error' && !showSkeleton && candidates.length === 0

  const availability = availabilityNotice(searchResponse?.availability)
  const paused = role ? pauseCopy(role) : null
  const newNotice = newCandidatesNotice(searchResponse?.new_candidates ?? 0)
  const note = calibrationNote(searchResponse?.calibration)
  const undecided = arrangedItems.filter((item) => !decisions[item.candidate.id]).length
  const heading = isRole ? reviewHeading(arrangedItems.length, undecided) : null
  const cycleRunning = searchState === 'searching'
  const nothingMore = isRole && reserveItems.length === 0 && Boolean(searchResponse?.retrieval_exhausted)
  const moreMessage = roleMessage ?? (nothingMore ? "We haven't found additional candidates in the current search." : null)

  return (
    <div className="discovery">
      <h2 className="discovery-heading">Candidate Review</h2>

      <div className="discovery-toolbar">
        <div className="discovery-toolbar__actions">
          <button type="button" className="discovery-edit-brief" onClick={() => setIsEditingBrief((current) => !current)}>
            <Pencil size={14} aria-hidden="true" />
            {isEditingBrief ? 'Close Search Brief' : 'Edit Brief'}
          </button>
        </div>
      </div>

      {isEditingBrief ? (
        <div className="workspace__grid">
          <div className="discovery-edit-panel">
            {boundary ? (
              <section className="brief-panel" aria-label="Search boundary">
                <h2 className="brief-section__title">Search boundary</h2>
                <BoundaryEditor boundary={boundary} onApply={onApplyBoundary} limitation={boundaryLimitation} />
              </section>
            ) : (
              <p className="discovery-empty">The brief this search came from is no longer available, so the boundary cannot be edited. Start a new search to change it.</p>
            )}
            <SearchBriefReview brief={brief} onChange={onChangeBrief} />
          </div>

          <aside className="workspace__preview" aria-label="Search summary">
            <p className="workspace__preview-label">Search Summary</p>
            <dl className="workspace__preview-list">
              <div className="workspace__preview-row">
                <dt>Role</dt>
                <dd>{brief.role.primaryTitle || 'Not specified'}</dd>
              </div>
              <div className="workspace__preview-row">
                <dt>Location</dt>
                <dd>{boundary ? `${formatBoundaryLocation(boundary)} · ${workModeLabel(boundary)}` : 'Not available'}</dd>
              </div>
              <div className="workspace__preview-row">
                <dt>Experience</dt>
                <dd>{summarizeExperience(brief)}</dd>
              </div>
              <div className="workspace__preview-row">
                <dt>Skills</dt>
                <dd>
                  {brief.skills.required.length || brief.skills.preferred.length || brief.skills.excluded.length
                    ? summarizeSkills(brief.skills.required, brief.skills.preferred, brief.skills.excluded)
                    : 'Matched via natural-language search, not itemized filters'}
                </dd>
              </div>
              <div className="workspace__preview-row">
                <dt>Companies</dt>
                <dd>{summarizeCompanies(brief.companies.include, brief.companies.exclude)}</dd>
              </div>
            </dl>
          </aside>

          <div className="brief-actions">
            <button type="button" className="brief-back" onClick={() => setIsEditingBrief(false)}>
              Cancel
            </button>

            <div className="brief-find-slot">
              {searchErrors.length ? (
                <div className="workspace__status workspace__status--error" role="alert">
                  {searchErrors.map((message) => (
                    <p key={message}>{message}</p>
                  ))}
                </div>
              ) : showError ? (
                <div className="workspace__status workspace__status--error" role="alert">
                  <p>We couldn't complete this search. You can try again.</p>
                </div>
              ) : null}

              <button
                type="button"
                className={`workspace__parse${searchState === 'searching' ? ' workspace__parse--busy' : ''}`}
                onClick={onRunSearch}
                disabled={searchState === 'searching'}
              >
                {searchState === 'searching' ? (
                  <>
                    <span className="workspace__spinner" aria-hidden="true" />
                    <span>Searching the market…</span>
                  </>
                ) : (
                  <span>Run Search Again</span>
                )}
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="discovery-layout">
          <div className="discovery-main" id="role-candidates">
            {role ? <RoleBar role={role} running={cycleRunning} busy={roleBusy} onPause={() => void runRoleAction(() => onRoleAction?.('pause'))} onResume={() => void runRoleAction(() => onRoleAction?.('resume'))} /> : null}

            {availability && !(paused && !pauseDismissed && role?.pause_kind === 'narrow') ? <AvailabilityNotice notice={availability} onReview={() => setIsEditingBrief(true)} /> : null}

            {paused && !pauseDismissed ? <PausedPanel copy={paused} busy={roleBusy} onAction={onPauseAction} /> : null}

            {newNotice ? <NewCandidatesNotice text={newNotice} busy={roleBusy} onReview={() => void runRoleAction(() => onShowMore?.(true))} /> : null}

            {searchNotice ? <p className="role-more__message">{searchNotice}</p> : null}

            {showSkeleton ? <SkeletonRows /> : null}
            {showSkeleton && isRole && progress?.admitted ? <p className="role-more__message">Reading profiles: {progress.review_ready ?? 0} of {progress.admitted}</p> : null}

            {!showSkeleton && !hasSearchedOnce ? <p className="discovery-empty">No candidates yet.</p> : null}

            {!showSkeleton && showError ? (
              <div className="discovery-empty">
                <p>We couldn't complete this search.</p>
                <button type="button" className="workspace__retry" onClick={onRunSearch}>
                  Try again
                </button>
              </div>
            ) : null}

            {!showSkeleton && showZeroResults && !availability ? (
              <div className="discovery-empty">
                <p>No candidates matched this search.</p>
                <button type="button" className="workspace__retry" onClick={() => setIsEditingBrief(true)}>
                  Adjust Search Brief
                </button>
              </div>
            ) : null}

            {heading && !showSkeleton ? <h3 className="role-heading">{heading}</h3> : null}

            {!showSkeleton && arrangedItems.length > 0 ? (
              <CandidateWorkspace
                flatItems={flatItems}
                decisions={decisions}
                selectedId={selectedId}
                onOpen={setSelectedId}
                onDecide={decide}
                running={running}
                funnel={funnel}
                warnings={searchResponse?.warnings ?? []}
                orderNote={isRole ? ROLE_ORDER_NOTE : undefined}
                feedback={isRole ? (searchResponse?.feedback ?? {}) : undefined}
                onFeedback={isRole ? giveFeedback : undefined}
              />
            ) : null}

            {note ? (
              <CalibrationNote
                text={note.text}
                dimensions={note.dimensions}
                onRemove={(dimension) => void onCorrectCalibration?.([...(searchResponse?.calibration?.dismissed ?? []), dimension])}
              />
            ) : null}

            {isRole && !showSkeleton && (arrangedItems.length > 0 || reserveItems.length > 0) && onShowMore ? (
              <ShowMoreBar busy={cycleRunning || roleBusy} message={moreMessage} onMore={() => void runRoleAction(() => onShowMore())} />
            ) : null}

            {isRole && !showSkeleton && reserveItems.length > 0 ? (
              <OtherReviewed count={reserveItems.length}>
                <CandidateWorkspace
                  compact
                  flatItems={reserveItems}
                  decisions={decisions}
                  selectedId={selectedId}
                  onOpen={setSelectedId}
                  onDecide={decide}
                  running={null}
                  funnel={null}
                  warnings={[]}
                  feedback={searchResponse?.feedback ?? {}}
                  onFeedback={giveFeedback}
                />
              </OtherReviewed>
            ) : null}
          </div>

          {selectedCandidate ? (
            <CandidateRecord
              candidate={selectedCandidate}
              decision={decisions[selectedCandidate.id]}
              onDecision={(decision) => toggleDecision(selectedCandidate.id, decision)}
              onClose={() => setSelectedId(null)}
            >
            <div className="brief-section">
              <h3 className="brief-section__title">Contact</h3>
              <dl className="workspace__preview-list">
                <div className="workspace__preview-row">
                  <dt>Email</dt>
                  <dd className={selectedCandidate.contactEmail ? '' : 'discovery-resume-status--empty'}>{emailStatusLine(selectedCandidate)}</dd>
                </div>
                <div className="workspace__preview-row">
                  <dt>Phone</dt>
                  <dd className={selectedCandidate.contactPhone ? '' : 'discovery-resume-status--empty'}>{phoneStatusLine(selectedCandidate)}</dd>
                </div>
              </dl>
            </div>

            <div className="brief-section">
              <h3 className="brief-section__title">Resume</h3>
              {resumes[selectedCandidate.id] ? (
                <p className="discovery-resume-status">{resumes[selectedCandidate.id].name}</p>
              ) : (
                <p className="discovery-resume-status discovery-resume-status--empty">No resume on file.</p>
              )}
              <input
                ref={fileInputRef}
                type="file"
                className="discovery-file-input"
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  if (file) uploadResume(selectedCandidate.id, file)
                  event.target.value = ''
                }}
              />
              <button type="button" className="discovery-action" onClick={() => fileInputRef.current?.click()}>
                <Upload size={14} aria-hidden="true" />
                {resumes[selectedCandidate.id] ? 'Replace Resume' : 'Upload Resume'}
              </button>
            </div>

            <div className="brief-section">
              <h3 className="brief-section__title">Notes</h3>
              <div className="discovery-notes">
                {(notes[selectedCandidate.id] ?? []).map((note) => (
                  <p key={note.id} className="discovery-note">
                    {note.text}
                  </p>
                ))}
                {(notes[selectedCandidate.id] ?? []).length === 0 ? (
                  <p className="discovery-note discovery-note--empty">No notes yet.</p>
                ) : null}
              </div>
              <div className="discovery-note-form">
                <textarea
                  className="discovery-note-input"
                  placeholder="Add a note about this candidate…"
                  value={noteDraft}
                  onChange={(event) => setNoteDraft(event.target.value)}
                  rows={2}
                />
                <button type="button" className="discovery-action" onClick={() => addNote(selectedCandidate.id)} disabled={!noteDraft.trim()}>
                  Add Note
                </button>
              </div>
            </div>

            <div className="brief-section">
              <h3 className="brief-section__title">Coming Soon</h3>
              <ul className="assessment-list assessment-list--future">
                <li>Interview Questions</li>
                <li>Outreach Draft</li>
                <li>Compensation Analysis</li>
              </ul>
            </div>
            </CandidateRecord>
          ) : null}
        </div>
      )}
    </div>
  )
}
