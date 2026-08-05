import { useEffect, useMemo, useRef, useState } from 'react'
import { Pencil, Upload, UserMinus, UserPlus, X } from 'lucide-react'
import type { SearchBrief } from '../models/searchBrief'
import type { SearchResponse } from '../types'
import {
  buildDiscoveryCandidates,
  formatExperienceYears,
  formatMatchScore,
  sortDiscoveryCandidates,
  type SortKey,
} from '../models/discovery'
import { SearchBriefReview, summarizeCompanies, summarizeExperience, summarizeLocations, summarizeSkills } from './SearchBriefReview'

type FieldChange = (path: string, updater: (current: SearchBrief) => SearchBrief) => void

type SearchState = 'idle' | 'searching' | 'done' | 'error'

type CandidateDiscoveryScreenProps = {
  brief: SearchBrief
  onChangeBrief: FieldChange
  searchResponse: SearchResponse | null
  searchState: SearchState
  onRunSearch: () => void
}

type Note = { id: string; text: string; createdAt: string }
type Resume = { name: string; uploadedAt: string }

const SORT_OPTIONS: Array<{ value: SortKey; label: string }> = [
  { value: 'match', label: 'Match' },
  { value: 'experience', label: 'Experience' },
  { value: 'recent', label: 'Recently updated' },
  { value: 'name', label: 'Name' },
]

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

export function CandidateDiscoveryScreen({ brief, onChangeBrief, searchResponse, searchState, onRunSearch }: CandidateDiscoveryScreenProps) {
  const [sortKey, setSortKey] = useState<SortKey>('match')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [isEditingBrief, setIsEditingBrief] = useState(false)
  const [pipelineIds, setPipelineIds] = useState<ReadonlySet<string>>(new Set())
  const [resumes, setResumes] = useState<Record<string, Resume>>({})
  const [notes, setNotes] = useState<Record<string, Note[]>>({})
  const [recencyById, setRecencyById] = useState<Record<string, number>>({})
  const [noteDraft, setNoteDraft] = useState('')
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    setSelectedId(null)
    setIsEditingBrief(false)
  }, [searchResponse])

  const candidates = useMemo(() => (searchResponse ? buildDiscoveryCandidates(searchResponse) : []), [searchResponse])
  const sortedCandidates = useMemo(() => sortDiscoveryCandidates(candidates, sortKey, recencyById), [candidates, sortKey, recencyById])
  const selectedCandidate = candidates.find((candidate) => candidate.id === selectedId) ?? null

  const touch = (id: string) => {
    setRecencyById((current) => ({ ...current, [id]: Date.now() }))
  }

  const togglePipeline = (id: string) => {
    setPipelineIds((current) => {
      const next = new Set(current)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
    touch(id)
  }

  const uploadResume = (id: string, file: File) => {
    setResumes((current) => ({ ...current, [id]: { name: file.name, uploadedAt: new Date().toISOString() } }))
    touch(id)
  }

  const addNote = (id: string) => {
    const text = noteDraft.trim()
    if (!text) return
    setNotes((current) => ({
      ...current,
      [id]: [...(current[id] ?? []), { id: `${Date.now()}`, text, createdAt: new Date().toISOString() }],
    }))
    setNoteDraft('')
    touch(id)
  }

  const hasSearchedOnce = searchResponse !== null
  const showSkeleton = searchState === 'searching'
  const showZeroResults = searchState === 'done' && hasSearchedOnce && candidates.length === 0
  const showError = searchState === 'error' && !showSkeleton

  return (
    <div className="discovery">
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

        <button type="button" className="discovery-edit-brief" onClick={() => setIsEditingBrief((current) => !current)}>
          <Pencil size={14} aria-hidden="true" />
          {isEditingBrief ? 'Close Search Brief' : 'Edit Brief'}
        </button>
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
                <dd>{summarizeSkills(brief.skills.required, brief.skills.preferred, brief.skills.excluded)}</dd>
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
                  <span>Candidate</span>
                  <span>Company</span>
                  <span>Location</span>
                  <span>Experience</span>
                  <span>Match</span>
                  <span>Resume</span>
                  <span>Pipeline</span>
                </div>

                {sortedCandidates.map((candidate) => (
                  <button
                    key={candidate.id}
                    type="button"
                    className={`candidate-row${selectedId === candidate.id ? ' is-selected' : ''}`}
                    onClick={() => setSelectedId(candidate.id)}
                  >
                    <span className="candidate-row__identity">
                      <span className="candidate-row__name">{candidate.name}</span>
                      <span className="candidate-row__title">{candidate.title}</span>
                    </span>
                    <span>{candidate.company}</span>
                    <span>{candidate.location}</span>
                    <span>{formatExperienceYears(candidate.experienceYears)}</span>
                    <span className="candidate-badge candidate-badge--score">{formatMatchScore(candidate.matchScore)}</span>
                    <span className={`candidate-badge${resumes[candidate.id] ? ' candidate-badge--positive' : ''}`}>
                      {resumes[candidate.id] ? 'Uploaded' : 'Missing'}
                    </span>
                    <span className={`candidate-badge${pipelineIds.has(candidate.id) ? ' candidate-badge--positive' : ''}`}>
                      {pipelineIds.has(candidate.id) ? 'In Pipeline' : 'Not in pipeline'}
                    </span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>

          {selectedCandidate ? (
            <aside className="discovery-profile" aria-label="Candidate profile">
              <div className="discovery-profile__head">
                <div>
                  <h2>{selectedCandidate.name}</h2>
                  <p>
                    {selectedCandidate.title} · {selectedCandidate.company}
                  </p>
                </div>
                <button type="button" className="discovery-profile__close" onClick={() => setSelectedId(null)} aria-label="Close profile">
                  <X size={16} />
                </button>
              </div>

              <div className="brief-section">
                <h3 className="brief-section__title">Overview</h3>
                <dl className="workspace__preview-list">
                  {selectedCandidate.bio ? (
                    <div className="workspace__preview-row">
                      <dt>Summary</dt>
                      <dd>{selectedCandidate.bio}</dd>
                    </div>
                  ) : null}
                  <div className="workspace__preview-row">
                    <dt>Current role</dt>
                    <dd>{selectedCandidate.title}</dd>
                  </div>
                  <div className="workspace__preview-row">
                    <dt>Company</dt>
                    <dd>{selectedCandidate.company}</dd>
                  </div>
                  <div className="workspace__preview-row">
                    <dt>Experience</dt>
                    <dd>{formatExperienceYears(selectedCandidate.experienceYears)}</dd>
                  </div>
                  <div className="workspace__preview-row">
                    <dt>Location</dt>
                    <dd>{selectedCandidate.location}</dd>
                  </div>
                </dl>
              </div>

              <div className="brief-section">
                <h3 className="brief-section__title">Match</h3>

                <div className="discovery-chip-group">
                  <span className="discovery-chip-group__label">Required skills matched</span>
                  {selectedCandidate.explanation.matchedRequiredSkills.length ? (
                    selectedCandidate.explanation.matchedRequiredSkills.map((skill) => (
                      <span key={skill} className="discovery-chip discovery-chip--matched">
                        {skill}
                      </span>
                    ))
                  ) : (
                    <span className="discovery-chip-group__empty">None</span>
                  )}
                </div>

                <div className="discovery-chip-group">
                  <span className="discovery-chip-group__label">Required skills missing</span>
                  {selectedCandidate.explanation.missingRequiredSkills.length ? (
                    selectedCandidate.explanation.missingRequiredSkills.map((skill) => (
                      <span key={skill} className="discovery-chip discovery-chip--missing">
                        {skill}
                      </span>
                    ))
                  ) : (
                    <span className="discovery-chip-group__empty">None</span>
                  )}
                </div>

                <div className="discovery-chip-group">
                  <span className="discovery-chip-group__label">Preferred skills matched</span>
                  {selectedCandidate.explanation.matchedPreferredSkills.length ? (
                    selectedCandidate.explanation.matchedPreferredSkills.map((skill) => (
                      <span key={skill} className="discovery-chip discovery-chip--matched">
                        {skill}
                      </span>
                    ))
                  ) : (
                    <span className="discovery-chip-group__empty">None</span>
                  )}
                </div>

                <div className="discovery-chip-group">
                  <span className="discovery-chip-group__label">Preferred skills missing</span>
                  {selectedCandidate.explanation.missingPreferredSkills.length ? (
                    selectedCandidate.explanation.missingPreferredSkills.map((skill) => (
                      <span key={skill} className="discovery-chip discovery-chip--missing">
                        {skill}
                      </span>
                    ))
                  ) : (
                    <span className="discovery-chip-group__empty">None</span>
                  )}
                </div>

                <dl className="workspace__preview-list">
                  <div className="workspace__preview-row">
                    <dt>Overall reasoning</dt>
                    <dd>{selectedCandidate.explanation.summary || 'Not available'}</dd>
                  </div>
                  <div className="workspace__preview-row">
                    <dt>Confidence score</dt>
                    <dd>{formatMatchScore(selectedCandidate.explanation.finalScore ?? selectedCandidate.matchScore)}</dd>
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
                <h3 className="brief-section__title">Candidate Actions</h3>
                <div className="discovery-actions-row">
                  <button type="button" className="discovery-action" onClick={() => togglePipeline(selectedCandidate.id)}>
                    {pipelineIds.has(selectedCandidate.id) ? (
                      <>
                        <UserMinus size={14} aria-hidden="true" />
                        Remove from Pipeline
                      </>
                    ) : (
                      <>
                        <UserPlus size={14} aria-hidden="true" />
                        Add to Pipeline
                      </>
                    )}
                  </button>
                </div>
              </div>
            </aside>
          ) : null}
        </div>
      )}
    </div>
  )
}
