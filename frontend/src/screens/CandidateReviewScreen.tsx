import { useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, ExternalLink, Pencil, Upload, X } from 'lucide-react'
import type { SearchBrief } from '../models/searchBrief'
import type { SearchResponse } from '../types'
import {
  buildDiscoveryCandidates,
  emailStatusLine,
  phoneStatusLine,
  relevanceLabel,
  sortDiscoveryCandidates,
  type DiscoveryCandidate,
  type RelevanceTier,
  type SortKey,
} from '../models/discovery'
import { updateCandidateRecord } from '../services/recruiterWorkflow'
import { SearchBriefReview, summarizeCompanies, summarizeExperience, summarizeLocations, summarizeSkills } from './SearchBriefReview'

type FieldChange = (path: string, updater: (current: SearchBrief) => SearchBrief) => void

type SearchState = 'idle' | 'searching' | 'done' | 'error'

type CandidateReviewScreenProps = {
  brief: SearchBrief
  onChangeBrief: FieldChange
  searchResponse: SearchResponse | null
  searchState: SearchState
  onRunSearch: () => void
  searchId: string | null
}

type Note = { id: string; text: string; createdAt: string }
type Resume = { name: string; uploadedAt: string }
type Decision = 'shortlist' | 'maybe' | 'reject'

const SORT_OPTIONS: Array<{ value: SortKey; label: string }> = [
  { value: 'relevance', label: 'Relevance' },
  { value: 'updated', label: 'Profile Updated' },
  { value: 'name', label: 'Name' },
]

const DECISION_OPTIONS: Array<{ value: Decision; label: string }> = [
  { value: 'shortlist', label: 'Shortlist' },
  { value: 'maybe', label: 'Maybe' },
  { value: 'reject', label: 'Reject' },
]

const MAX_COMPARE = 3

function pipelineLabel(decision: Decision | undefined): string {
  if (decision === 'shortlist') return 'Shortlisted'
  if (decision === 'maybe') return 'Maybe'
  if (decision === 'reject') return 'Rejected'
  return 'Not reviewed'
}

function tierClassName(tier: RelevanceTier): string {
  if (tier === 'direct') return 'assessment-verdict--excellent'
  if (tier === 'adjacent') return 'assessment-verdict--good'
  if (tier === 'tangential') return 'assessment-verdict--partial'
  return 'assessment-verdict--weak'
}

function SkeletonRows() {
  return (
    <div className="discovery-list" aria-hidden="true">
      {Array.from({ length: 6 }).map((_, index) => (
        <div key={index} className="candidate-row candidate-row--skeleton">
          <div className="discovery-skeleton discovery-skeleton--wide" />
          <div className="discovery-skeleton" />
          <div className="discovery-skeleton" />
          <div className="discovery-skeleton discovery-skeleton--narrow" />
          <div className="discovery-skeleton discovery-skeleton--narrow" />
          <div className="discovery-skeleton discovery-skeleton--narrow" />
        </div>
      ))}
    </div>
  )
}

function ComparisonPanel({ candidates, onClose }: { candidates: DiscoveryCandidate[]; onClose: () => void }) {
  return (
    <div className="comparison-panel">
      <div className="comparison-panel__head">
        <h2>Comparing {candidates.length} candidates</h2>
        <button type="button" className="discovery-profile__close" onClick={onClose} aria-label="Close comparison">
          <X size={16} />
        </button>
      </div>

      <div className={`comparison-grid comparison-grid--${candidates.length}`}>
        {candidates.map((candidate) => (
          <div key={candidate.id} className="comparison-column">
            <div className="comparison-column__head">
              <h3>{candidate.name}</h3>
              <p>{candidate.title}</p>
            </div>

            <div className="comparison-row">
              <span className="comparison-row__label">Relevance</span>
              <span className={`candidate-badge candidate-badge--verdict ${tierClassName(candidate.relevanceTier)}`}>
                {relevanceLabel(candidate.relevanceTier)}
              </span>
            </div>

            <div className="comparison-row">
              <span className="comparison-row__label">Companies</span>
              <span>{candidate.company}</span>
            </div>

            <div className="comparison-row comparison-row--block">
              <span className="comparison-row__label">Strong Evidence</span>
              <div className="discovery-chip-group">
                {candidate.strongEvidence.length ? (
                  candidate.strongEvidence.slice(0, 3).map((item) => (
                    <span key={item} className="discovery-chip discovery-chip--matched">
                      {item}
                    </span>
                  ))
                ) : (
                  <span className="discovery-chip-group__empty">No specific evidence found</span>
                )}
              </div>
            </div>

            <div className="comparison-row comparison-row--block">
              <span className="comparison-row__label">Why Surfaced</span>
              <p className="comparison-summary">{candidate.whyThisCandidate || 'Not enough information to assess.'}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function CandidateReviewScreen({ brief, onChangeBrief, searchResponse, searchState, onRunSearch, searchId }: CandidateReviewScreenProps) {
  const [sortKey, setSortKey] = useState<SortKey>('relevance')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [isEditingBrief, setIsEditingBrief] = useState(false)
  const [decisions, setDecisions] = useState<Record<string, Decision>>({})
  const [resumes, setResumes] = useState<Record<string, Resume>>({})
  const [notes, setNotes] = useState<Record<string, Note[]>>({})
  const [noteDraft, setNoteDraft] = useState('')
  const [compareIds, setCompareIds] = useState<string[]>([])
  const [isComparing, setIsComparing] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    setSelectedId(null)
    setIsEditingBrief(false)
    setCompareIds([])
    setIsComparing(false)

    // Hydrate from whatever the backend already has persisted for this
    // search, rather than starting empty — this is the actual fix for
    // decisions/notes disappearing on refresh. Root cause was that neither
    // POST /search nor GET /search/{id} returned recruiter_decisions/notes
    // at all, so there was nothing here to read; the backend was already
    // saving them correctly (see services/search_store.py) the whole time.
    const decisionsRecord = searchResponse?.recruiter_decisions
    setDecisions((decisionsRecord as Record<string, Decision>) ?? {})

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
  const sortedCandidates = useMemo(() => sortDiscoveryCandidates(candidates, sortKey), [candidates, sortKey])
  const selectedCandidate = candidates.find((candidate) => candidate.id === selectedId) ?? null
  const compareCandidates = compareIds.map((id) => candidates.find((candidate) => candidate.id === id)).filter((c): c is DiscoveryCandidate => Boolean(c))

  const setDecision = (id: string, decision: Decision) => {
    const next = decisions[id] === decision ? undefined : decision
    setDecisions((current) => ({ ...current, [id]: next } as Record<string, Decision>))
    if (searchId && next) {
      updateCandidateRecord(searchId, id, { decision: next }).catch(() => {})
    }
  }

  const toggleCompare = (id: string) => {
    setCompareIds((current) => {
      if (current.includes(id)) {
        return current.filter((candidateId) => candidateId !== id)
      }
      if (current.length >= MAX_COMPARE) {
        return current
      }
      return [...current, id]
    })
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
  const showSkeleton = searchState === 'searching'
  const showZeroResults = searchState === 'done' && hasSearchedOnce && candidates.length === 0
  const showError = searchState === 'error' && !showSkeleton

  return (
    <div className="discovery">
      <h2 className="discovery-heading">Candidate Review</h2>

      <div className="discovery-toolbar">
        <div className="brief-segmented" role="group" aria-label="Sort candidates">
          {SORT_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`brief-segmented__option${sortKey === option.value ? ' is-active' : ''}`}
              onClick={() => setSortKey(option.value)}
              disabled={candidates.length === 0}
            >
              {option.label}
            </button>
          ))}
        </div>

        <div className="discovery-toolbar__actions">
          {compareIds.length >= 2 ? (
            <button type="button" className="discovery-edit-brief" onClick={() => setIsComparing(true)}>
              Compare ({compareIds.length})
            </button>
          ) : null}

          <button
            type="button"
            className="discovery-edit-brief"
            onClick={() => {
              setIsComparing(false)
              setIsEditingBrief((current) => !current)
            }}
          >
            <Pencil size={14} aria-hidden="true" />
            {isEditingBrief ? 'Close Search Brief' : 'Edit Brief'}
          </button>
        </div>
      </div>

      {isEditingBrief ? (
        <div className="workspace__grid">
          <SearchBriefReview brief={brief} onChange={onChangeBrief} variant="embedded" />

          <aside className="workspace__preview" aria-label="Search summary">
            <p className="workspace__preview-label">Search Summary</p>
            <dl className="workspace__preview-list">
              <div className="workspace__preview-row">
                <dt>Role</dt>
                <dd>{brief.role.primaryTitle || 'Not specified'}</dd>
              </div>
              <div className="workspace__preview-row">
                <dt>Location</dt>
                <dd>{summarizeLocations(brief)}</dd>
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
              {showError ? (
                <div className="workspace__status workspace__status--error" role="alert">
                  <p>We couldn't reach the search provider. You can try again.</p>
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
                    <span>Searching Crustdata…</span>
                  </>
                ) : (
                  <span>Run Search Again</span>
                )}
              </button>
            </div>
          </div>
        </div>
      ) : isComparing ? (
        <ComparisonPanel candidates={compareCandidates} onClose={() => setIsComparing(false)} />
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
              <div className="discovery-list">
                <div className="candidate-row candidate-row--head" aria-hidden="true">
                  <span></span>
                  <span>Candidate</span>
                  <span>Company</span>
                  <span>Location</span>
                  <span>Relevance</span>
                  <span>Why Surfaced</span>
                  <span>Resume</span>
                  <span>Pipeline</span>
                </div>

                {sortedCandidates.map((candidate) => (
                  <div key={candidate.id} className={`candidate-row${selectedId === candidate.id ? ' is-selected' : ''}`}>
                    <span className="candidate-row__compare">
                      <input
                        type="checkbox"
                        checked={compareIds.includes(candidate.id)}
                        onChange={() => toggleCompare(candidate.id)}
                        disabled={!compareIds.includes(candidate.id) && compareIds.length >= MAX_COMPARE}
                        aria-label={`Select ${candidate.name} for comparison`}
                        onClick={(event) => event.stopPropagation()}
                      />
                    </span>
                    <button type="button" className="candidate-row__open" onClick={() => setSelectedId(candidate.id)}>
                      <span className="candidate-row__identity">
                        <span className="candidate-row__name">{candidate.name}</span>
                        <span className="candidate-row__title">{candidate.title}</span>
                      </span>
                    </button>
                    <button type="button" className="candidate-row__open" onClick={() => setSelectedId(candidate.id)}>
                      {candidate.company}
                    </button>
                    <button type="button" className="candidate-row__open" onClick={() => setSelectedId(candidate.id)}>
                      {candidate.location}
                    </button>
                    <button type="button" className="candidate-row__open" onClick={() => setSelectedId(candidate.id)}>
                      <span className={`candidate-badge candidate-badge--verdict ${tierClassName(candidate.relevanceTier)}`}>
                        {relevanceLabel(candidate.relevanceTier)}
                      </span>
                      {candidate.potentialConcerns.length ? (
                        <AlertTriangle size={13} className="candidate-row__concern-flag" aria-label="Potential concern — see profile" />
                      ) : null}
                    </button>
                    <button type="button" className="candidate-row__open candidate-row__why" onClick={() => setSelectedId(candidate.id)}>
                      {candidate.strongEvidence[0] || candidate.whyThisCandidate || 'No specific evidence found in the available profile data'}
                    </button>
                    <button type="button" className="candidate-row__open" onClick={() => setSelectedId(candidate.id)}>
                      <span className={`candidate-badge${resumes[candidate.id] ? ' candidate-badge--positive' : ''}`}>
                        {resumes[candidate.id] ? 'Uploaded' : 'Missing'}
                      </span>
                    </button>
                    <button type="button" className="candidate-row__open" onClick={() => setSelectedId(candidate.id)}>
                      <span className={`candidate-badge${decisions[candidate.id] === 'shortlist' ? ' candidate-badge--positive' : ''}${decisions[candidate.id] === 'reject' ? ' candidate-badge--negative' : ''}`}>
                        {pipelineLabel(decisions[candidate.id])}
                      </span>
                    </button>
                  </div>
                ))}
              </div>
            ) : null}
          </div>

          {selectedCandidate ? (
            <aside className="discovery-profile" aria-label="Candidate review">
              <div className="discovery-profile__head">
                <div>
                  <h2>{selectedCandidate.name}</h2>
                  <p>
                    {selectedCandidate.title} · {selectedCandidate.company}
                  </p>
                  {selectedCandidate.profileUrl ? (
                    <a
                      className="discovery-profile__linkedin"
                      href={selectedCandidate.profileUrl}
                      target="_blank"
                      rel="noreferrer noopener"
                    >
                      <ExternalLink size={13} aria-hidden="true" />
                      LinkedIn · Open Profile
                    </a>
                  ) : null}
                </div>
                <button type="button" className="discovery-profile__close" onClick={() => setSelectedId(null)} aria-label="Close profile">
                  <X size={16} />
                </button>
              </div>

              <div className="brief-section">
                <div className="discovery-profile__tier-row">
                  <div className={`assessment-verdict ${tierClassName(selectedCandidate.relevanceTier)}`}>
                    {relevanceLabel(selectedCandidate.relevanceTier)}
                  </div>
                  {selectedCandidate.potentialConcerns.length ? (
                    <span className="discovery-profile__concern-pill">
                      <AlertTriangle size={12} aria-hidden="true" /> {selectedCandidate.potentialConcerns.length} concern
                      {selectedCandidate.potentialConcerns.length === 1 ? '' : 's'}
                    </span>
                  ) : null}
                </div>
                <p className="assessment-narrative">{selectedCandidate.whyThisCandidate || 'Not enough information was returned to assess this candidate.'}</p>
              </div>

              <div className="brief-section">
                <h3 className="brief-section__title">Strong Evidence</h3>
                <ul className="assessment-list assessment-list--strengths">
                  {selectedCandidate.strongEvidence.length ? (
                    selectedCandidate.strongEvidence.map((item) => <li key={item}>{item}</li>)
                  ) : (
                    <li className="assessment-list__empty">No specific evidence found in the available profile data.</li>
                  )}
                </ul>
              </div>

              {selectedCandidate.potentialConcerns.length ? (
                <div className="brief-section brief-section--concerns">
                  <h3 className="brief-section__title brief-section__title--concerns">
                    <AlertTriangle size={15} aria-hidden="true" />
                    Potential Concerns
                  </h3>
                  <ul className="assessment-list assessment-list--concerns">
                    {selectedCandidate.potentialConcerns.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                </div>
              ) : null}

              <div className="brief-section">
                <h3 className="brief-section__title">What We Don't Know</h3>
                <ul className="assessment-list">
                  {selectedCandidate.whatWeDontKnow.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>

              <div className="brief-section">
                <h3 className="brief-section__title">Recruiter Decision</h3>
                <div className="brief-segmented" role="group" aria-label="Recruiter decision">
                  {DECISION_OPTIONS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      className={`brief-segmented__option${decisions[selectedCandidate.id] === option.value ? ' is-active' : ''}`}
                      onClick={() => setDecision(selectedCandidate.id, option.value)}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="brief-section">
                <h3 className="brief-section__title">Career</h3>
                {selectedCandidate.pastRoles.length ? (
                  <ul className="assessment-list">
                    {selectedCandidate.pastRoles.slice(0, 3).map((role, index) => (
                      <li key={`${role.title}-${index}`}>
                        {role.title || 'Role'}
                        {role.company ? ` · ${role.company}` : ''}
                      </li>
                    ))}
                    {selectedCandidate.pastRoles.length > 3 ? (
                      <li className="assessment-list__empty">+ {selectedCandidate.pastRoles.length - 3} earlier role(s) on record</li>
                    ) : null}
                  </ul>
                ) : (
                  <p className="discovery-resume-status discovery-resume-status--empty">No prior career history returned for this candidate.</p>
                )}
              </div>

              <div className="brief-section">
                <h3 className="brief-section__title">Education</h3>
                {selectedCandidate.education.length ? (
                  <ul className="assessment-list">
                    {selectedCandidate.education.map((entry, index) => (
                      <li key={index}>
                        {[entry.degree, entry.fieldOfStudy].filter(Boolean).join(', ') || 'Degree not specified'}
                        {entry.institution ? ` · ${entry.institution}` : ''}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="discovery-resume-status discovery-resume-status--empty">Education was not returned for this candidate.</p>
                )}
              </div>

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
            </aside>
          ) : null}
        </div>
      )}
    </div>
  )
}
