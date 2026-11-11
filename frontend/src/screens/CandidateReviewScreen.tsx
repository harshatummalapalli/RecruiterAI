import { useEffect, useMemo, useRef, useState } from 'react'
import { Pencil } from 'lucide-react'
import type { SearchBrief } from '../models/searchBrief'
import type { SearchResponse } from '../types'
import { buildDiscoveryCandidates } from '../models/discovery'
import { buildWorkspaceCandidates, normalizeDecision, stableOrder, type Decision } from '../models/workspace'
import { CandidateRecord, type RecordNote } from '../components/CandidateRecord'
import { CandidateFilters, candidatePassesFilters, EMPTY_FILTERS, type CandidateFilterState } from '../components/CandidateFilters'
import { CandidateWorkspace } from '../components/CandidateWorkspace'
import { RefinePanel } from '../components/RefinePanel'
import { AvailabilityNotice, CalibrationNote, NewCandidatesNotice, OtherReviewed, PausedPanel, RoleBar, ShowMoreBar } from '../components/RoleControls'
import {
  availabilityNotice,
  calibrationNote,
  isRoleSearch,
  newCandidatesNotice,
  orderPresented,
  ROLE_ORDER_NOTE,
  pauseCopy,
  splitByPresentation,
  type PauseAction,
} from '../models/roleWorkspace'
import { loadPersistedSearch, refineSearch, revealNextCandidate, updateCandidateRecord, type RefineDeltas } from '../services/recruiterWorkflow'
import type { SearchBoundary } from '../models/searchBoundary'
import type { IntakeIssue, IntakeResult } from '../models/intake'
import { LivingBrief } from './LivingBrief'

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
  // Edit Brief reuses the exact Living Brief experience — same role
  // understanding, same requirements, same "Adjust before searching" form
  // — instead of a parallel raw-fields view. Null exactly when the
  // original intake reading could not be resumed (same condition boundary
  // already used to be unavailable under), in which case Edit Brief says
  // so rather than showing a broken or fabricated reading.
  intakeResult?: IntakeResult | null
  onAnswer?: (issue: IntakeIssue, value: string, label: string) => void
  onRetier?: (assignments: Record<string, string>) => void
  isAnswering?: boolean
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
  // Reports whether a candidate record is open, so the role sidebar can collapse to give the record pane room.
  onSelectionChange?: (hasSelection: boolean) => void
}

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

/** Every profile the campaign has retrieved so far, as a flat read-only list. Lives in
 * the "All profiles" tab (#3): the Top-5 / To-review drip is the opinionated funnel; this
 * is the full pulled set for a recruiter who wants to browse everything at once. */
function CampaignPoolView({ entries }: { entries: NonNullable<SearchResponse['pool_candidates']> }) {
  if (entries.length === 0) return null
  return (
    <div className="ws-pool">
      <p className="ws-pool__note">
        Everything pulled for this campaign. “Not assessed” means the profile has not had deeper analysis — it is not a rejection or a fit decision. The strongest are surfaced for review under the other tabs.
      </p>
      <ul className="ws-pool__list">
        {entries.map((entry) => (
          <li key={entry.candidate_id} className="ws-pool__row">
            <span className="ws-pool__identity">
              <strong>{entry.name || 'Name not returned'}</strong>
              <span>{[entry.title, entry.company, entry.location].filter(Boolean).join(' · ') || 'Profile details unavailable'}</span>
            </span>
            <span className={`ws-pool__state ws-pool__state--${entry.assessment_state}`}>
              {entry.assessment_state === 'shown' ? 'Shown above' : entry.assessment_state === 'assessed' ? 'Deeply assessed' : 'Not assessed'}
            </span>
            {entry.profile_url ? (
              <a href={entry.profile_url} target="_blank" rel="noreferrer" className="ws-pool__link">Profile</a>
            ) : null}
          </li>
        ))}
      </ul>
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
  intakeResult = null,
  onAnswer = () => {},
  onRetier = () => {},
  isAnswering = false,
  searchErrors = [],
  onShowMore,
  onRoleAction,
  onCorrectCalibration,
  onSearchResponse,
  roleMessage = null,
  searchNotice = null,
  onSelectionChange,
}: CandidateReviewScreenProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [isEditingBrief, setIsEditingBrief] = useState(false)
  // The pool-first refine overlay, and the in-flight state of an Apply. Reset on a new search.
  const [isRefining, setIsRefining] = useState(false)
  const [refineBusy, setRefineBusy] = useState(false)
  const [decisions, setDecisions] = useState<Record<string, Decision | undefined>>({})
  // Local Include/Exclude filters over deterministic attributes — never re-searches, never spends credits.
  const [filters, setFilters] = useState<CandidateFilterState>(EMPTY_FILTERS)
  const [roleBusy, setRoleBusy] = useState(false)
  const [pauseDismissed, setPauseDismissed] = useState(false)
  // Recruiter working memory — separate from AI-generated evidence. Persisted per candidate via updateCandidateRecord.
  const [notes, setNotes] = useState<Record<string, RecordNote[]>>({})
  const [noteDraft, setNoteDraft] = useState('')
  // A save that failed (network/server). Shown so a Shortlist/Reject/note never looks saved when it wasn't.
  const [writeError, setWriteError] = useState<string | null>(null)
  // Choices made here that the server has not confirmed yet. A poll that lands between a click and its save must not
  // flip the card back, so these are laid over whatever the server returns until it agrees.
  const pendingDecisions = useRef<Record<string, Decision | null>>({})
  const feedbackPollRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const activeSearchIdRef = useRef(searchId)
  // The order candidates first arrived in, kept for the whole search. The server re-orders its own list once when the
  // search finishes; the workspace does not follow that until the recruiter chooses to group.
  const arrivalOrder = useRef<{ generation: number; ids: string[] }>({ generation: searchGeneration, ids: [] })

  // Progressive Candidate Workspace: searchResponse updates repeatedly (once per poll tick) while the SAME search is
  // still running, so the open-record/edit-brief reset is keyed to a NEW search (searchGeneration), not to every update.
  useEffect(() => {
    setSelectedId(null)
    setIsEditingBrief(false)
    setIsRefining(false)
    setPauseDismissed(false)
    setFilters(EMPTY_FILTERS)
    pendingDecisions.current = {}
  }, [searchGeneration, searchId])

  useEffect(() => () => {
    if (feedbackPollRef.current !== null) clearTimeout(feedbackPollRef.current)
  }, [searchId])

  useEffect(() => {
    activeSearchIdRef.current = searchId
  }, [searchId])

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
    const hydratedNotes: Record<string, RecordNote[]> = {}
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
  // Include/Exclude is a pure local view filter over the presented set — it narrows what's shown,
  // it never re-searches or re-admits. Reserve ("other reviewed") is filtered the same way.
  const filteredItems = useMemo(() => flatItems.filter((item) => candidatePassesFilters(item.candidate, filters)), [flatItems, filters])
  const filteredReserveItems = useMemo(() => reserveItems.filter((item) => candidatePassesFilters(item.candidate, filters)), [reserveItems, filters])
  const selectedCandidate = candidates.find((candidate) => candidate.id === selectedId) ?? null
  // Prev/next inside the open record: the same order the list is already shown in, so it never jumps around.
  const orderedIds = filteredItems.map((item) => item.candidate.id)
  const selectedIndex = selectedId ? orderedIds.indexOf(selectedId) : -1
  const prevCandidateId = selectedIndex > 0 ? orderedIds[selectedIndex - 1] : null
  const nextCandidateId = selectedIndex >= 0 && selectedIndex < orderedIds.length - 1 ? orderedIds[selectedIndex + 1] : null

  useEffect(() => {
    onSelectionChange?.(Boolean(selectedCandidate))
  }, [selectedCandidate, onSelectionChange])

  const progress = searchResponse?.progress
  const isRole = isRoleSearch(searchResponse)
  // New engine: ask for a structured reason on Maybe/Reject even though it is not a
  // multi-search "role". Legacy pre-role searches leave this off, so they are unchanged.
  const captureFeedback = isRole || Boolean(searchResponse?.feedback_capture)
  const role = searchResponse?.role ?? null
  // While a later cycle runs, the candidates already on screen stay as they are; only the first read shows progress.
  // Retrieval counts, funnel breakdowns and "how this list was made" are deliberately not shown to the recruiter —
  // "Reading profiles: N of M" below (from `progress`, not from here) is the only in-progress signal kept.

  const saved = (response: SearchResponse | undefined) => {
    // The server's answer keeps the role, feedback and the one-time summary current. Anything else is ignored.
    if (response && typeof response === 'object' && 'search_id' in response) onSearchResponse?.(response)
  }

  const waitForFeedbackAnalysis = (id: string) => {
    if (feedbackPollRef.current !== null) clearTimeout(feedbackPollRef.current)
    let attempts = 0
    const tick = async () => {
      attempts += 1
      const response = await loadPersistedSearch(id).catch(() => null)
      if (!response || id !== activeSearchIdRef.current) return
      saved(response)
      if (response.role?.reserve_analysis_state === 'running' && attempts < 120) {
        feedbackPollRef.current = setTimeout(tick, 1500)
      }
    }
    void tick()
  }

  const decide = (id: string, next: Decision | undefined) => {
    const previous = decisions[id]
    pendingDecisions.current[id] = next ?? null
    setDecisions((current) => ({ ...current, [id]: next }))
    setWriteError(null)
    // Pool-first reveal: a reject opens a slot, so bring the next already-read
    // profile forward from the held pool — free, no new search — if any remain.
    const revealAfterReject = next === 'reject' && captureFeedback && !searchResponse?.initial_validation_pending && (searchResponse?.reserve_available ?? 0) > 0
    if (searchId) {
      // An empty decision clears it on the server.
      updateCandidateRecord(searchId, id, { decision: next ?? '' })
        .then((response) => {
          saved(response)
          if (response.role?.reserve_analysis_state === 'running') waitForFeedbackAnalysis(searchId)
          if (revealAfterReject) {
            revealNextCandidate(searchId)
              .then(saved)
              .catch(() => setWriteError('The next profile could not be brought forward — check your connection and try again.'))
          }
        })
        .catch(() => {
          // The save failed — roll the card back to what's actually stored and say so,
          // rather than leaving a decision that looks saved but isn't.
          delete pendingDecisions.current[id]
          setDecisions((current) => ({ ...current, [id]: previous }))
          setWriteError('That change could not be saved — check your connection and try again.')
        })
    }
  }

  const giveFeedback = (id: string, update: { reason?: string; note?: string }) => {
    if (!searchId) return
    setWriteError(null)
    updateCandidateRecord(searchId, id, { feedback_reason: update.reason, feedback_note: update.note })
      .then((response) => {
        saved(response)
        if (response.role?.reserve_analysis_state === 'running') waitForFeedbackAnalysis(searchId)
      })
      .catch(() => setWriteError('That change could not be saved — check your connection and try again.'))
  }

  // Pool-first refine: re-check the already-read profiles against the tighter brief.
  // Free — no new search, no credits. The panel stays open so the recruiter sees the outcome.
  const applyRefine = (deltas: RefineDeltas) => {
    if (!searchId) return
    setRefineBusy(true)
    setWriteError(null)
    refineSearch(searchId, deltas)
      .then(saved)
      .catch(() => setWriteError('That refinement could not be applied — check your connection and try again.'))
      .finally(() => setRefineBusy(false))
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

  const addNote = (id: string) => {
    const text = noteDraft.trim()
    if (!text) return
    const noteId = `${Date.now()}`
    setNotes((current) => ({
      ...current,
      [id]: [...(current[id] ?? []), { id: noteId, text, createdAt: new Date().toISOString() }],
    }))
    setWriteError(null)
    if (searchId) {
      updateCandidateRecord(searchId, id, { note: text })
        .then(saved)
        .catch(() => {
          // Drop the optimistic note so it doesn't look saved, and surface the error.
          setNotes((current) => ({ ...current, [id]: (current[id] ?? []).filter((note) => note.id !== noteId) }))
          setWriteError('That note could not be saved — check your connection and try again.')
        })
    }
    setNoteDraft('')
  }

  // Export what's already on screen — no re-search, no credits, no data leaves that the recruiter can't already see.
  const exportCsv = () => {
    const header = ['Name', 'Title', 'Company', 'Location', 'Years', 'Decision', 'Email', 'Profile URL']
    const esc = (value: string) => `"${value.replace(/"/g, '""')}"`
    const rows = candidates.map((c) => [
      c.name, c.title, c.company, c.location,
      c.experienceYears != null ? String(Math.round(c.experienceYears)) : '',
      decisions[c.id] ?? '', c.contactEmail ?? '', c.profileUrl ?? '',
    ])
    const csv = [header, ...rows].map((row) => row.map((cell) => esc(String(cell ?? ''))).join(',')).join('\r\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `candidates-${searchId ?? 'export'}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  const hasSearchedOnce = searchResponse !== null
  // The skeleton is only for the brief window before the FIRST candidates are admitted.
  const showSkeleton = searchState === 'searching' && (isRole ? arrangedItems.length === 0 : candidates.length === 0)
  const showZeroResults = searchState === 'done' && hasSearchedOnce && candidates.length === 0
  const showError = searchState === 'error' && !showSkeleton && candidates.length === 0
  // Answer "where did the other candidates go?": the shown few are the strongest of a
  // larger reviewed pool. Honest, without exposing raw retrieval counts.
  const diag = (searchResponse?.diagnostics ?? {}) as Record<string, unknown>
  const reviewedCount = Number(diag.judged ?? diag.admitted ?? 0)
  // The whole market matching the hard filters — the universe we read the strongest
  // few from. Surfaced so "N reviewed" is never mistaken for "N found".
  const universe = Number(diag.total_available ?? 0)
  const reviewedNote =
    !isRole && searchState === 'done' && candidates.length > 0 && reviewedCount > candidates.length
      ? universe > reviewedCount
        ? `Found ${universe.toLocaleString()} matching profiles — showing the ${candidates.length} strongest, read in depth.`
        : `Showing the ${candidates.length} strongest of ${reviewedCount} read in depth.`
      : null

  const availability = availabilityNotice(searchResponse?.availability)
  const paused = role ? pauseCopy(role) : null
  const newNotice = newCandidatesNotice(searchResponse?.new_candidates ?? 0)
  const note = calibrationNote(searchResponse?.calibration)
  const cycleRunning = searchState === 'searching'
  const nothingMore = isRole && reserveItems.length === 0 && Boolean(searchResponse?.retrieval_exhausted)
  const moreMessage = roleMessage ?? (nothingMore ? "We haven't found additional candidates in the current search." : null)
  const hasStoredCampaignPool = (searchResponse?.pool_candidate_count ?? 0) > 0
  const hasMoreToReveal = hasStoredCampaignPool
    ? (searchResponse?.reserve_available ?? 0) > 0
    : arrangedItems.length > 0 || reserveItems.length > 0

  return (
    <div className="discovery">
      <div className="discovery-toolbar">
        <div className="discovery-toolbar__actions">
          <button type="button" className="discovery-edit-brief" onClick={() => setIsEditingBrief((current) => !current)}>
            <Pencil size={14} aria-hidden="true" />
            {isEditingBrief ? 'Close Search Brief' : 'Edit Brief'}
          </button>
        </div>
      </div>

      {isEditingBrief ? (
        <div className="workspace__brief">
          <div className="brief-actions brief-actions--top">
            <button type="button" className="brief-back" onClick={() => setIsEditingBrief(false)}>
              Cancel
            </button>
          </div>

          {/* The exact same Living Brief the recruiter already saw before confirming this search — role
             understanding, requirements, boundary, notes — reused as-is, never a parallel raw-fields form.
             "Search" (LivingBrief's own confirm action) is wired to the SAME onRunSearch this screen already
             used for "Run Search Again": editing here changes no backend/confirmation behavior, only which UI
             component the recruiter edits through. */}
          {intakeResult && boundary ? (
            <LivingBrief
              result={intakeResult}
              boundary={boundary}
              brief={brief}
              onChangeBrief={onChangeBrief}
              onAnswer={onAnswer}
              onRetier={onRetier}
              isAnswering={isAnswering}
              onApplyBoundary={onApplyBoundary}
              onSearch={onRunSearch}
              isSearching={searchState === 'searching'}
              searchErrors={searchErrors.length ? searchErrors : showError ? ["We couldn't complete this search. You can try again."] : []}
            />
          ) : (
            <p className="discovery-empty">
              The original role understanding for this search is no longer available, so Edit Brief can't be shown here. Start a new search to change it.
            </p>
          )}
        </div>
      ) : (
        <div className="discovery-layout">
          <div className="discovery-main" id="role-candidates">
            {role ? <RoleBar role={role} running={cycleRunning} busy={roleBusy} onPause={() => void runRoleAction(() => onRoleAction?.('pause'))} onResume={() => void runRoleAction(() => onRoleAction?.('resume'))} /> : null}

            {availability && !(paused && !pauseDismissed && role?.pause_kind === 'narrow') ? <AvailabilityNotice notice={availability} onReview={() => setIsEditingBrief(true)} /> : null}

            {paused && !pauseDismissed ? <PausedPanel copy={paused} busy={roleBusy} onAction={onPauseAction} /> : null}

            {newNotice ? <NewCandidatesNotice text={newNotice} busy={roleBusy} onReview={() => void runRoleAction(() => onShowMore?.(true))} /> : null}

            {searchNotice ? <p className="role-more__message">{searchNotice}</p> : null}

            {writeError ? (
              <p className="discovery-write-error" role="alert">
                {writeError}{' '}
                <button type="button" className="discovery-write-error__dismiss" onClick={() => setWriteError(null)}>Dismiss</button>
              </p>
            ) : null}

            {showSkeleton ? <SkeletonRows /> : null}
            {showSkeleton && progress?.admitted ? (
              <p className="role-more__message">
                {universe > progress.admitted
                  ? `Found ${universe.toLocaleString()} matching profiles — reading the strongest ${progress.admitted} in depth (${progress.review_ready ?? 0} done).`
                  : `Reading profiles: ${progress.review_ready ?? 0} of ${progress.admitted}.`}
              </p>
            ) : null}

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

            {!showSkeleton && candidates.length > 0 ? (
              <div className="discovery-toolbar">
                {reviewedNote ? <span className="discovery-reviewed-note">{reviewedNote}</span> : <span />}
                <div className="discovery-toolbar__actions">
                  {captureFeedback ? (
                    <button type="button" className="discovery-refine" onClick={() => setIsRefining(true)}>Refine search</button>
                  ) : null}
                  <button type="button" className="discovery-export" onClick={exportCsv}>Export CSV</button>
                </div>
              </div>
            ) : null}

            {!showSkeleton && arrangedItems.length > 0 ? (
              <CandidateFilters
                candidates={flatItems.map((item) => item.candidate)}
                state={filters}
                onChange={setFilters}
                shown={filteredItems.length}
                total={flatItems.length}
              />
            ) : null}

            {!showSkeleton && arrangedItems.length > 0 && filteredItems.length === 0 ? (
              <p className="discovery-empty">No candidates match the current filters. <button type="button" className="record-more" onClick={() => setFilters(EMPTY_FILTERS)}>Clear filters</button></p>
            ) : null}

            {!showSkeleton && filteredItems.length > 0 ? (
              <CandidateWorkspace
                flatItems={filteredItems}
                decisions={decisions}
                selectedId={selectedId}
                onOpen={setSelectedId}
                onDecide={decide}
                orderNote={isRole ? ROLE_ORDER_NOTE : 'Strongest matches first.'}
                feedback={captureFeedback ? (searchResponse?.feedback ?? {}) : undefined}
                onFeedback={captureFeedback ? giveFeedback : undefined}
                poolTab={
                  isRole && (searchResponse?.pool_candidates?.length ?? 0) > 0
                    ? {
                        count: searchResponse?.pool_candidate_count ?? searchResponse?.pool_candidates?.length ?? 0,
                        render: () => <CampaignPoolView entries={searchResponse?.pool_candidates ?? []} />,
                      }
                    : undefined
                }
              />
            ) : null}

            {note ? (
              <CalibrationNote
                text={note.text}
                dimensions={note.dimensions}
                onRemove={(dimension) => void onCorrectCalibration?.([...(searchResponse?.calibration?.dismissed ?? []), dimension])}
              />
            ) : null}

            {isRole && !showSkeleton && searchResponse?.initial_validation_pending ? (
              <div className="role-more"><p className="role-more__message">Review all five initial candidates to unlock the next group.</p></div>
            ) : null}

            {isRole && !showSkeleton && role?.reserve_analysis_state === 'running' ? (
              <div className="role-more" aria-live="polite"><p className="role-more__message">Checking the remaining profiles against your validations. Only close matches will be enriched and added here.</p></div>
            ) : null}

            {isRole && !showSkeleton && role?.reserve_analysis_state === 'complete' && role.reserve_analysis_added === 0 ? (
              <div className="role-more"><p className="role-more__message">No additional profiles were added from the stored pool. Any profiles that did not pass the screen remain un-enriched in reserve.</p></div>
            ) : null}

            {isRole && !showSkeleton && role?.reserve_analysis_state === 'failed' ? (
              <div className="role-more"><p className="role-more__message">The held profiles could not be assessed. They remain in reserve; updating a validation will retry the screen.</p></div>
            ) : null}

            {isRole && !showSkeleton && !searchResponse?.initial_validation_pending && hasMoreToReveal && onShowMore ? (
              <ShowMoreBar busy={cycleRunning || roleBusy || role?.reserve_analysis_state === 'running'} message={moreMessage} remaining={searchResponse?.reserve_available ?? undefined} onMore={() => void runRoleAction(() => onShowMore())} />
            ) : null}

            {isRole && !showSkeleton && filteredReserveItems.length > 0 ? (
              <OtherReviewed count={filteredReserveItems.length}>
                <CandidateWorkspace
                  compact
                  flatItems={filteredReserveItems}
                  decisions={decisions}
                  selectedId={selectedId}
                  onOpen={setSelectedId}
                  onDecide={decide}
                  feedback={searchResponse?.feedback ?? {}}
                  onFeedback={giveFeedback}
                />
              </OtherReviewed>
            ) : null}

            {/* The full retrieved pool now lives in the workspace's "All profiles" tab (#3),
                so the old always-open expander here is gone — no more showing the Top-5 drip
                and all N profiles at once. */}
          </div>

          {selectedCandidate ? (
            <CandidateRecord
              candidate={selectedCandidate}
              decision={decisions[selectedCandidate.id]}
              onDecision={(decision) => toggleDecision(selectedCandidate.id, decision)}
              onClose={() => setSelectedId(null)}
              onPrev={prevCandidateId ? () => setSelectedId(prevCandidateId) : undefined}
              onNext={nextCandidateId ? () => setSelectedId(nextCandidateId) : undefined}
              notes={notes[selectedCandidate.id] ?? []}
              noteDraft={noteDraft}
              onNoteDraftChange={setNoteDraft}
              onAddNote={() => addNote(selectedCandidate.id)}
            />
          ) : null}

          {isRefining ? (
            <RefinePanel
              onClose={() => setIsRefining(false)}
              intakeResult={intakeResult}
              boundary={boundary}
              outcome={searchResponse?.refine_outcome ?? null}
              busy={refineBusy}
              onApply={applyRefine}
            />
          ) : null}
        </div>
      )}
    </div>
  )
}
