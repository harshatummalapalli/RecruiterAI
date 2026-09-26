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
import { setWorkspaceArranged, updateCandidateRecord } from '../services/recruiterWorkflow'
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

export function CandidateReviewScreen({ brief, onChangeBrief, searchResponse, searchState, onRunSearch, searchId, searchGeneration, boundary, onApplyBoundary, boundaryLimitation = null, searchErrors = [] }: CandidateReviewScreenProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [isEditingBrief, setIsEditingBrief] = useState(false)
  const [decisions, setDecisions] = useState<Record<string, Decision | undefined>>({})
  const [resumes, setResumes] = useState<Record<string, Resume>>({})
  const [notes, setNotes] = useState<Record<string, Note[]>>({})
  const [noteDraft, setNoteDraft] = useState('')
  const [arrangedLocally, setArrangedLocally] = useState(false)
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
    setArrangedLocally(false)
    pendingDecisions.current = {}
  }, [searchGeneration])

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
  const arrangedItems = useMemo(() => buildWorkspaceCandidates(candidates), [candidates])
  const flatItems = useMemo(() => {
    if (arrivalOrder.current.generation !== searchGeneration) {
      arrivalOrder.current = { generation: searchGeneration, ids: [] }
    }
    arrivalOrder.current.ids = stableOrder(arrivalOrder.current.ids, arrangedItems.map((item) => item.candidate.id))
    const byId = new Map(arrangedItems.map((item) => [item.candidate.id, item]))
    return arrivalOrder.current.ids.map((id) => byId.get(id)).filter((item): item is (typeof arrangedItems)[number] => Boolean(item))
  }, [arrangedItems, searchGeneration])
  const selectedCandidate = candidates.find((candidate) => candidate.id === selectedId) ?? null

  const arranged = Boolean(searchResponse?.workspace_arranged) || arrangedLocally
  const allRead = arrangedItems.length > 0 && arrangedItems.every((item) => item.facts.section !== 'preparing')
  const canArrange = searchState === 'done' && !arranged && allRead
  const progress = searchResponse?.progress
  const running = searchState === 'searching' && progress?.admitted ? { read: progress.review_ready ?? 0, total: progress.admitted } : null
  const funnel = !running && candidates.length > 0 ? funnelCopy(readFunnel(searchResponse?.diagnostics), candidates.length) : null

  const decide = (id: string, next: Decision | undefined) => {
    pendingDecisions.current[id] = next ?? null
    setDecisions((current) => ({ ...current, [id]: next }))
    if (searchId) {
      // An empty decision clears it on the server.
      updateCandidateRecord(searchId, id, { decision: next ?? '' }).catch(() => {})
    }
  }

  const toggleDecision = (id: string, choice: Decision) => decide(id, decisions[id] === choice ? undefined : choice)

  const arrange = () => {
    setArrangedLocally(true)
    if (searchId) {
      setWorkspaceArranged(searchId, true).catch(() => {})
    }
  }

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
  const showSkeleton = searchState === 'searching' && candidates.length === 0
  const showZeroResults = searchState === 'done' && hasSearchedOnce && candidates.length === 0
  const showError = searchState === 'error' && !showSkeleton && candidates.length === 0

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
          <div className="discovery-main">
            {showSkeleton ? <SkeletonRows /> : null}

            {!showSkeleton && !hasSearchedOnce ? <p className="discovery-empty">No candidates yet.</p> : null}

            {!showSkeleton && showError ? (
              <div className="discovery-empty">
                <p>We couldn't complete this search.</p>
                <button type="button" className="workspace__retry" onClick={onRunSearch}>
                  Try again
                </button>
              </div>
            ) : null}

            {!showSkeleton && showZeroResults ? (
              <div className="discovery-empty">
                <p>No candidates matched this search.</p>
                <button type="button" className="workspace__retry" onClick={() => setIsEditingBrief(true)}>
                  Adjust Search Brief
                </button>
              </div>
            ) : null}

            {!showSkeleton && candidates.length > 0 ? (
              <CandidateWorkspace
                flatItems={flatItems}
                arrangedItems={arrangedItems}
                decisions={decisions}
                selectedId={selectedId}
                onOpen={setSelectedId}
                onDecide={decide}
                arranged={arranged}
                canArrange={canArrange}
                onArrange={arrange}
                running={running}
                funnel={funnel}
                warnings={searchResponse?.warnings ?? []}
              />
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
