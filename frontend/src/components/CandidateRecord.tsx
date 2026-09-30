import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Check, ChevronDown, ChevronUp, ExternalLink, HelpCircle, Minus, Plus, X } from 'lucide-react'
import { initialsOf, relevanceLabel, type DiscoveryCandidate, type LedgerGroup, type LedgerRow } from '../models/discovery'
import './CandidateRecord.css'

export type RecordDecision = 'shortlist' | 'maybe' | 'reject'

const DECISIONS: Array<{ value: RecordDecision; label: string }> = [
  { value: 'shortlist', label: 'Shortlist' },
  { value: 'maybe', label: 'Maybe' },
  { value: 'reject', label: 'Reject' },
]

const CAREER_SHOWN = 5
const SKILLS_SHOWN = 10
const EDUCATION_SHOWN = 2

export type RecordNote = { id: string; text: string; createdAt: string }

type CandidateRecordProps = {
  candidate: DiscoveryCandidate
  decision?: RecordDecision
  onDecision: (decision: RecordDecision) => void
  onClose: () => void
  /** Move to the previous/next candidate in the same list, without closing and reopening the pane. */
  onPrev?: () => void
  onNext?: () => void
  /** Recruiter working memory — separate from AI-generated evidence, persisted per candidate. */
  notes: RecordNote[]
  noteDraft: string
  onNoteDraftChange: (value: string) => void
  onAddNote: () => void
}

function Avatar({ name, url }: { name: string; url: string | null }) {
  const [failed, setFailed] = useState(false)
  if (url && !failed) {
    return <img className="record-avatar" src={url} alt="" referrerPolicy="no-referrer" onError={() => setFailed(true)} />
  }
  return (
    <span className="record-avatar record-avatar--initials" aria-hidden="true">
      {initialsOf(name)}
    </span>
  )
}

function LedgerRowView({ row }: { row: LedgerRow }) {
  const met = row.verdict === 'met'
  return (
    <li className={`record-ledger__row record-ledger__row--${met ? 'met' : 'partly'}`}>
      <span className="record-ledger__mark" aria-label={met ? 'Evidenced' : 'Related, not counted'}>
        {met ? <Check size={14} aria-hidden="true" /> : <Minus size={14} aria-hidden="true" />}
      </span>
      <div className="record-ledger__body">
        <p className="record-ledger__req">{row.requirement}</p>
        {row.quote ? (
          <p className="record-ledger__quote">
            {row.derived ? row.quote : <>“{row.quote.replace(/^[-•\s]+/, '')}”</>}
          </p>
        ) : null}
        {row.sourceLabel ? <p className="record-ledger__source">{row.sourceLabel}</p> : null}
        {!met ? <p className="record-ledger__note">Related to this requirement, but it does not show it. Not counted.</p> : null}
      </div>
    </li>
  )
}

function LedgerSection({ group }: { group: LedgerGroup }) {
  const shown = group.rows.filter((row) => row.verdict !== 'not_evidenced')
  const missing = group.rows.filter((row) => row.verdict === 'not_evidenced')
  // "unknown" (nothing was available to check) reads very differently from
  // "not_evidenced" (checked, didn't demonstrate it) — a recruiter must be
  // able to tell them apart at a glance, never as an implied negative.
  const notDemonstrated = missing.filter((row) => row.evidenceState !== 'unknown')
  const unavailable = missing.filter((row) => row.evidenceState === 'unknown')
  // Core gaps matter most, so each gets its own line. Supporting and preferred
  // gaps collapse into one line so the ledger stays readable.
  const perRowGaps = group.tier === 'core'
  return (
    <div className="record-ledger">
      <div className="record-ledger__head">
        <h4>{group.label}</h4>
        <span className="record-ledger__count">
          {group.evidenced} of {group.total} evidenced
        </span>
      </div>
      <ul className="record-ledger__list">
        {shown.map((row) => (
          <LedgerRowView key={row.requirement} row={row} />
        ))}
        {perRowGaps
          ? missing.map((row) => {
              const unknown = row.evidenceState === 'unknown'
              return (
                <li key={row.requirement} className={`record-ledger__row record-ledger__row--missing${unknown ? ' record-ledger__row--unknown' : ''}`}>
                  <span className="record-ledger__mark" aria-label={unknown ? 'Evidence unavailable' : 'Not demonstrated'}>
                    {unknown ? <HelpCircle size={14} aria-hidden="true" /> : <Minus size={14} aria-hidden="true" />}
                  </span>
                  <div className="record-ledger__body">
                    <p className="record-ledger__req">{row.requirement}</p>
                    <p className="record-ledger__note">{unknown ? 'Role evidence unavailable.' : 'Not demonstrated in available role evidence.'}</p>
                  </div>
                </li>
              )
            })
          : null}
      </ul>
      {!perRowGaps && notDemonstrated.length ? (
        <p className="record-ledger__gaps">
          <Minus size={13} aria-hidden="true" /> Not demonstrated: {notDemonstrated.map((row) => row.requirement).join(' · ')}
        </p>
      ) : null}
      {!perRowGaps && unavailable.length ? (
        <p className="record-ledger__gaps record-ledger__gaps--unknown">
          <HelpCircle size={13} aria-hidden="true" /> Evidence unavailable: {unavailable.map((row) => row.requirement).join(' · ')}
        </p>
      ) : null}
    </div>
  )
}

export function CandidateRecord({ candidate, decision, onDecision, onClose, onPrev, onNext, notes, noteDraft, onNoteDraftChange, onAddNote }: CandidateRecordProps) {
  const [showAllCareer, setShowAllCareer] = useState(false)
  const [showAllSkills, setShowAllSkills] = useState(false)
  const noteInputRef = useRef<HTMLTextAreaElement>(null)

  const focusNoteComposer = () => {
    noteInputRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    noteInputRef.current?.focus()
  }

  const career = showAllCareer ? candidate.career : candidate.career.slice(0, CAREER_SHOWN)
  const skills = showAllSkills ? candidate.skills : candidate.skills.slice(0, SKILLS_SHOWN)
  const educationHead = candidate.education.slice(0, EDUCATION_SHOWN)
  const educationRest = candidate.education.slice(EDUCATION_SHOWN)
  const hasLedger = candidate.ledger.length > 0
  const educationLine = (entry: DiscoveryCandidate['education'][number]) =>
    [[entry.degree, entry.fieldOfStudy].filter(Boolean).join(', ') || 'Degree not specified', entry.institution, entry.years].filter(Boolean).join(' · ')

  // Move to the next/previous candidate without leaving the record — inspect, next, inspect, next.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (target?.closest('input, textarea, select, [contenteditable="true"]')) return
      if (event.metaKey || event.ctrlKey || event.altKey) return
      const key = event.key.toLowerCase()
      if ((key === 'j' || key === 'arrowdown') && onNext) {
        event.preventDefault()
        onNext()
      } else if ((key === 'k' || key === 'arrowup') && onPrev) {
        event.preventDefault()
        onPrev()
      } else if (key === 'escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onNext, onPrev, onClose])

  return (
    <aside className="discovery-profile record" aria-label="Candidate record">
      <header className="record-head">
        <Avatar name={candidate.name} url={candidate.photoUrl} />
        <div className="record-head__identity">
          <h2>{candidate.name}</h2>
          <p className="record-head__headline">{candidate.headline || candidate.title}</p>
          <p className="record-head__meta">
            {[candidate.company !== 'Not specified' ? candidate.company : null, candidate.location !== 'Not specified' ? candidate.location : null]
              .filter(Boolean)
              .join(' · ')}
          </p>
          <div className="record-head__chips">
            {candidate.profileUrl ? (
              <a className="record-chip record-chip--link" href={candidate.profileUrl} target="_blank" rel="noreferrer noopener">
                <ExternalLink size={12} aria-hidden="true" /> LinkedIn
              </a>
            ) : null}
            {candidate.openToWork === true ? (
              <span className="record-chip" title="Stated on the candidate's own profile. Shown for information only; it is never used to rank.">
                Open to work
              </span>
            ) : null}
          </div>
        </div>
        <div className="record-head__nav">
          <button type="button" className="record-nav-button" onClick={focusNoteComposer} aria-label="Add a note" title="Add a note">
            <Plus size={15} />
          </button>
          <button type="button" className="record-nav-button" onClick={onPrev} disabled={!onPrev} aria-label="Previous candidate" title="Previous (K)">
            <ChevronUp size={15} />
          </button>
          <button type="button" className="record-nav-button" onClick={onNext} disabled={!onNext} aria-label="Next candidate" title="Next (J)">
            <ChevronDown size={15} />
          </button>
          <button type="button" className="discovery-profile__close" onClick={onClose} aria-label="Close record">
            <X size={16} />
          </button>
        </div>
      </header>

      <div className="brief-segmented record-decision" role="group" aria-label="Recruiter decision">
        {DECISIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            className={`brief-segmented__option${decision === option.value ? ' is-active' : ''}`}
            onClick={() => onDecision(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>

      {candidate.aboutExcerpt || candidate.headline ? (
        <section className="record-section" aria-labelledby="record-snapshot">
          <h3 id="record-snapshot" className="record-section__title">
            Candidate Snapshot
          </h3>
          <p className="record-muted">{candidate.aboutExcerpt || candidate.headline}</p>
        </section>
      ) : null}

      <section className="record-section" aria-labelledby="record-review-first">
        <h3 id="record-review-first" className="record-section__title">
          Why this candidate
        </h3>
        {candidate.reviewFirst.length ? (
          <ul className="record-review">
            {candidate.reviewFirst.map((line, index) => (
              <li key={index} className={line.startsWith('Watch:') ? 'record-review__watch' : undefined}>
                {line.startsWith('Watch:') ? <AlertTriangle size={14} aria-hidden="true" /> : null}
                <span>{line}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="record-muted">{candidate.whyThisCandidate || 'Not enough information was returned to assess this candidate.'}</p>
        )}
        <p className="record-position">{relevanceLabel(candidate.relevanceTier)}</p>
      </section>

      <section className="record-section" aria-labelledby="record-ledger">
        <h3 id="record-ledger" className="record-section__title">
          Evidence for this role
        </h3>
        {hasLedger ? (
          <>
            <p className="record-muted record-ledger__intro">Each row is a requirement from the brief. A check needs a quote from the profile beside it.</p>
            {candidate.ledger.map((group) => (
              <LedgerSection key={group.tier} group={group} />
            ))}
            {candidate.potentialConcerns.length ? (
              <ul className="record-ledger__concerns">
                {candidate.potentialConcerns.map((item) => (
                  <li key={item}>
                    <AlertTriangle size={13} aria-hidden="true" /> {item}
                  </li>
                ))}
              </ul>
            ) : null}
          </>
        ) : (
          <>
            <p className="record-muted">The requirements were not checked against this profile, so there is no ledger. What we have:</p>
            <ul className="assessment-list assessment-list--strengths">
              {candidate.strongEvidence.length ? (
                candidate.strongEvidence.map((item) => <li key={item}>{item}</li>)
              ) : (
                <li className="assessment-list__empty">No specific evidence found in the available profile data.</li>
              )}
            </ul>
          </>
        )}
      </section>

      <section className="record-section" aria-labelledby="record-career">
        <h3 id="record-career" className="record-section__title">
          Experience
        </h3>
        {candidate.career.length ? (
          <>
            <ol className="record-career">
              {career.map((entry, index) => (
                <li key={`${entry.title}-${entry.company}-${index}`} className="record-career__item">
                  <p className="record-career__role">
                    {entry.title || 'Role'}
                    {entry.company ? <span> · {entry.company}</span> : null}
                  </p>
                  <p className="record-career__dates">
                    {[entry.start, entry.current ? 'present' : entry.end].filter(Boolean).join(' – ')}
                    {entry.duration ? ` · ${entry.duration}` : ''}
                    {entry.current ? ' · current' : ''}
                  </p>
                  {entry.description ? (
                    <details className="record-career__details">
                      <summary>What they did there</summary>
                      <p>{entry.description}</p>
                    </details>
                  ) : null}
                </li>
              ))}
            </ol>
            {candidate.career.length > CAREER_SHOWN ? (
              <button type="button" className="record-more" onClick={() => setShowAllCareer((current) => !current)}>
                {showAllCareer ? 'Show fewer roles' : `Show ${candidate.career.length - CAREER_SHOWN} earlier roles`}
              </button>
            ) : null}
          </>
        ) : (
          <p className="record-muted">No career history was returned for this candidate.</p>
        )}
      </section>

      {candidate.skills.length ? (
        <section className="record-section" aria-labelledby="record-skills">
          <h3 id="record-skills" className="record-section__title">
            Skills <span className="record-count">{candidate.skills.length} listed on the profile</span>
          </h3>
          <div className="record-skills">
            {skills.map((skill) => (
              <span key={skill} className="record-skill">
                {skill}
              </span>
            ))}
          </div>
          {candidate.skills.length > SKILLS_SHOWN ? (
            <button type="button" className="record-more" onClick={() => setShowAllSkills((current) => !current)}>
              {showAllSkills ? 'Show fewer' : `Show ${candidate.skills.length - SKILLS_SHOWN} more`}
            </button>
          ) : null}
        </section>
      ) : null}

      <section className="record-section" aria-labelledby="record-education">
        <h3 id="record-education" className="record-section__title">
          Education
        </h3>
        {candidate.education.length ? (
          <>
            <ul className="assessment-list">
              {educationHead.map((entry, index) => (
                <li key={index}>{educationLine(entry)}</li>
              ))}
            </ul>
            {educationRest.length ? (
              <details className="record-career__details">
                <summary>{educationRest.length} earlier {educationRest.length === 1 ? 'entry' : 'entries'}</summary>
                <ul className="assessment-list">
                  {educationRest.map((entry, index) => (
                    <li key={index}>{educationLine(entry)}</li>
                  ))}
                </ul>
              </details>
            ) : null}
          </>
        ) : (
          <p className="record-muted">Education was not returned for this candidate.</p>
        )}
      </section>

      <section className="record-section" aria-labelledby="record-notes">
        <h3 id="record-notes" className="record-section__title">
          Recruiter Notes
        </h3>
        <div className="discovery-notes">
          {notes.length ? (
            notes.map((note) => (
              <p key={note.id} className="discovery-note">
                {note.text}
              </p>
            ))
          ) : (
            <p className="discovery-note discovery-note--empty">No notes yet.</p>
          )}
        </div>
        <div className="discovery-note-form">
          <textarea
            ref={noteInputRef}
            className="discovery-note-input"
            placeholder="Add a note…"
            value={noteDraft}
            onChange={(event) => onNoteDraftChange(event.target.value)}
            rows={2}
          />
          <button type="button" className="record-more" onClick={onAddNote} disabled={!noteDraft.trim()}>
            Add note
          </button>
        </div>
      </section>
    </aside>
  )
}
