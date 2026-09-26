import { useState, type ReactNode } from 'react'
import { AlertTriangle, Check, ExternalLink, Minus, X } from 'lucide-react'
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
const CERTS_SHOWN = 3
const EDUCATION_SHOWN = 2

type CandidateRecordProps = {
  candidate: DiscoveryCandidate
  decision?: RecordDecision
  onDecision: (decision: RecordDecision) => void
  onClose: () => void
  /** Contact, resume, notes and the rest of the recruiter workflow, unchanged, below the record. */
  children?: ReactNode
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
          ? missing.map((row) => (
              <li key={row.requirement} className="record-ledger__row record-ledger__row--missing">
                <span className="record-ledger__mark" aria-label="Not evidenced">
                  <Minus size={14} aria-hidden="true" />
                </span>
                <div className="record-ledger__body">
                  <p className="record-ledger__req">{row.requirement}</p>
                  <p className="record-ledger__note">Not evidenced on this profile.</p>
                </div>
              </li>
            ))
          : null}
      </ul>
      {!perRowGaps && missing.length ? (
        <p className="record-ledger__gaps">
          <Minus size={13} aria-hidden="true" /> Not evidenced: {missing.map((row) => row.requirement).join(' · ')}
        </p>
      ) : null}
    </div>
  )
}

export function CandidateRecord({ candidate, decision, onDecision, onClose, children }: CandidateRecordProps) {
  const [showAllCareer, setShowAllCareer] = useState(false)
  const [showAllSkills, setShowAllSkills] = useState(false)
  const [showAllCerts, setShowAllCerts] = useState(false)

  const career = showAllCareer ? candidate.career : candidate.career.slice(0, CAREER_SHOWN)
  const skills = showAllSkills ? candidate.skills : candidate.skills.slice(0, SKILLS_SHOWN)
  const certs = showAllCerts ? candidate.certifications : candidate.certifications.slice(0, CERTS_SHOWN)
  const educationHead = candidate.education.slice(0, EDUCATION_SHOWN)
  const educationRest = candidate.education.slice(EDUCATION_SHOWN)
  const hasLedger = candidate.ledger.length > 0
  const educationLine = (entry: DiscoveryCandidate['education'][number]) =>
    [[entry.degree, entry.fieldOfStudy].filter(Boolean).join(', ') || 'Degree not specified', entry.institution, entry.years].filter(Boolean).join(' · ')

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
        <button type="button" className="discovery-profile__close" onClick={onClose} aria-label="Close record">
          <X size={16} />
        </button>
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

      <section className="record-section" aria-labelledby="record-review-first">
        <h3 id="record-review-first" className="record-section__title">
          Why review first
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
          Requirement ledger
        </h3>
        {hasLedger ? (
          <>
            <p className="record-muted record-ledger__intro">Each row is a requirement from the brief. A check needs a quote from the profile beside it.</p>
            {candidate.ledger.map((group) => (
              <LedgerSection key={group.tier} group={group} />
            ))}
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

      {candidate.experienceLine || candidate.levelLine ? (
        <section className="record-section" aria-labelledby="record-level">
          <h3 id="record-level" className="record-section__title">
            Experience and level
          </h3>
          <dl className="record-facts">
            {candidate.experienceLine ? (
              <>
                <dt>Experience</dt>
                <dd>{candidate.experienceLine}</dd>
              </>
            ) : null}
            {candidate.levelLine ? (
              <>
                <dt>Level</dt>
                <dd>{candidate.levelLine}</dd>
              </>
            ) : null}
          </dl>
        </section>
      ) : null}

      {candidate.potentialConcerns.length ? (
        <section className="record-section record-section--concerns" aria-labelledby="record-concerns">
          <h3 id="record-concerns" className="record-section__title">
            <AlertTriangle size={15} aria-hidden="true" /> What concerns us
          </h3>
          <ul className="assessment-list assessment-list--concerns">
            {candidate.potentialConcerns.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="record-section" aria-labelledby="record-unknown">
        <h3 id="record-unknown" className="record-section__title">
          What we don't know
        </h3>
        <ul className="assessment-list">
          {candidate.whatWeDontKnow
            // The level line already has its own place under Experience and level.
            .filter((item) => !(candidate.levelLine && item.startsWith('Level alignment:')))
            .map((item) => (
              <li key={item}>{item}</li>
            ))}
        </ul>
      </section>

      <section className="record-section" aria-labelledby="record-career">
        <h3 id="record-career" className="record-section__title">
          Career
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

      {candidate.certifications.length ? (
        <section className="record-section" aria-labelledby="record-certs">
          <h3 id="record-certs" className="record-section__title">
            Certifications <span className="record-count">{candidate.certifications.length}</span>
          </h3>
          <ul className="assessment-list">
            {certs.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          {candidate.certifications.length > CERTS_SHOWN ? (
            <button type="button" className="record-more" onClick={() => setShowAllCerts((current) => !current)}>
              {showAllCerts ? 'Show fewer' : `Show ${candidate.certifications.length - CERTS_SHOWN} more`}
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

      {candidate.aboutExcerpt ? (
        <section className="record-section" aria-labelledby="record-own-words">
          <h3 id="record-own-words" className="record-section__title">
            In their own words <span className="record-count">self-reported, not verified</span>
          </h3>
          <blockquote className="record-own-words">{candidate.aboutExcerpt}</blockquote>
        </section>
      ) : null}

      {children}
    </aside>
  )
}
