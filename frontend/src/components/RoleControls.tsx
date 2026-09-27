import { useState, type ReactNode } from 'react'
import { ChevronDown, ChevronUp, X } from 'lucide-react'
import type { RoleState } from '../types'
import {
  DIMENSION_LABEL,
  feedbackPrompt,
  otherReviewedLabel,
  roleStatusLabel,
  type Notice,
  type PauseAction,
  type PauseCopy,
} from '../models/roleWorkspace'
import './RoleControls.css'

/** Where the role stands, and the one control that goes with it: pause while it is searching, resume while paused. */
export function RoleBar({
  role,
  running,
  busy,
  onPause,
  onResume,
}: {
  role: RoleState
  running: boolean
  busy: boolean
  onPause: () => void
  onResume: () => void
}) {
  const paused = role.status === 'paused'
  return (
    <div className={`role-bar${paused ? ' is-paused' : ''}`} role="status">
      <span className="role-bar__state">
        <span className={`role-bar__dot${running && !paused ? ' is-working' : ''}`} aria-hidden="true" />
        {roleStatusLabel(role, running)}
      </span>
      {paused ? (
        role.can_resume ? (
          <button type="button" className="role-bar__action" onClick={onResume} disabled={busy}>
            Resume search
          </button>
        ) : null
      ) : (
        <button type="button" className="role-bar__action" onClick={onPause} disabled={busy}>
          Pause role
        </button>
      )}
    </div>
  )
}

/** A factual note about what the provider returned. Never a count of qualified candidates. */
export function AvailabilityNotice({ notice, onReview }: { notice: Notice; onReview?: () => void }) {
  return (
    <section className="role-notice role-notice--amber" aria-label="Search availability">
      <p className="role-notice__title">{notice.title}</p>
      <p className="role-notice__body">{notice.body}</p>
      {onReview ? (
        <button type="button" className="role-link" onClick={onReview}>
          Review search criteria
        </button>
      ) : null}
    </section>
  )
}

export function PausedPanel({
  copy,
  busy,
  onAction,
}: {
  copy: PauseCopy
  busy: boolean
  onAction: (action: PauseAction | 'keep_paused') => void
}) {
  return (
    <section className="role-paused" aria-label="Role paused">
      <h3 className="role-paused__title">{copy.title}</h3>
      <p className="role-paused__body">{copy.body}</p>
      {copy.suggestions.length > 0 ? (
        <ul className="role-paused__suggestions">
          {copy.suggestions.map((suggestion) => (
            <li key={suggestion}>{suggestion}</li>
          ))}
        </ul>
      ) : null}
      <div className="role-paused__actions">
        <button type="button" className="role-primary" onClick={() => onAction(copy.primary.action)} disabled={busy}>
          {copy.primary.label}
        </button>
        {copy.secondary ? (
          <button type="button" className="role-link" onClick={() => onAction(copy.secondary!.action)}>
            {copy.secondary.label}
          </button>
        ) : null}
      </div>
    </section>
  )
}

/** Candidates found by the background search. Quiet: it never moves the recruiter or the list they are reviewing. */
export function NewCandidatesNotice({ text, onReview, busy }: { text: string; onReview: () => void; busy: boolean }) {
  return (
    <div className="role-new" role="status">
      <span className="role-new__dot" aria-hidden="true" />
      <span>{text}</span>
      <button type="button" className="role-link" onClick={onReview} disabled={busy}>
        Review
      </button>
    </div>
  )
}

/** The one-time note after the first candidates are reviewed. The recruiter can remove anything it got wrong. */
export function CalibrationNote({ text, dimensions, onRemove }: { text: string; dimensions: string[]; onRemove: (dimension: string) => void }) {
  return (
    <section className="role-calibration" aria-label="What RecruiterAI will look for">
      <p className="role-calibration__text">{text}</p>
      {dimensions.length > 0 ? (
        <p className="role-calibration__fix">
          <span>Not quite right?</span>
          {dimensions.map((dimension) => (
            <button key={dimension} type="button" className="role-chip role-chip--removable" onClick={() => onRemove(dimension)} title="Stop looking for this">
              {DIMENSION_LABEL[dimension] ?? dimension}
              <X size={12} aria-hidden="true" />
            </button>
          ))}
        </p>
      ) : null}
    </section>
  )
}

export function ShowMoreBar({ busy, message, onMore }: { busy: boolean; message: string | null; onMore: () => void }) {
  return (
    <div className="role-more">
      <button type="button" className="role-primary" onClick={onMore} disabled={busy}>
        {busy ? (
          <>
            <span className="workspace__spinner" aria-hidden="true" />
            <span>Finding more candidates…</span>
          </>
        ) : (
          <span>Show me more</span>
        )}
      </button>
      {message ? <p className="role-more__message">{message}</p> : null}
    </div>
  )
}

/** Reviewed candidates that are not on screen yet. Collapsed, counted, and never described as rejected. */
export function OtherReviewed({ count, children }: { count: number; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <section className="role-other" aria-label="Other reviewed candidates">
      <button type="button" className="role-other__toggle" aria-expanded={open} onClick={() => setOpen((current) => !current)}>
        {open ? <ChevronUp size={15} aria-hidden="true" /> : <ChevronDown size={15} aria-hidden="true" />}
        <span>{otherReviewedLabel(count)}</span>
      </button>
      {open ? (
        <>
          <p className="role-other__note">These were read as part of the search and are kept. They are not rejected.</p>
          {children}
        </>
      ) : null}
    </section>
  )
}

/** Shown under a card after Maybe or Reject. One tap and it is done; every part is optional. */
export function FeedbackPrompt({
  decision,
  onReason,
  onNote,
  onSkip,
}: {
  decision: 'maybe' | 'reject'
  onReason: (reason: string) => void
  onNote: (note: string) => void
  onSkip: () => void
}) {
  const { question, options } = feedbackPrompt(decision)
  const [noting, setNoting] = useState(false)
  const [note, setNote] = useState('')
  return (
    <div className="ws-feedback" role="group" aria-label={question}>
      <p className="ws-feedback__question">{question}</p>
      <div className="ws-feedback__options">
        {options.map((option) => (
          <button key={option.value} type="button" className="role-chip" onClick={() => onReason(option.value)}>
            {option.label}
          </button>
        ))}
      </div>
      <div className="ws-feedback__more">
        {noting ? (
          <div className="ws-feedback__note">
            <textarea aria-label="Add a note" rows={2} maxLength={500} value={note} onChange={(event) => setNote(event.target.value)} placeholder="A few words are enough" />
            <button type="button" className="role-link" disabled={!note.trim()} onClick={() => onNote(note.trim())}>
              Save note
            </button>
          </div>
        ) : (
          <button type="button" className="role-link" onClick={() => setNoting(true)}>
            Add a note
          </button>
        )}
        <button type="button" className="role-link role-link--quiet" onClick={onSkip}>
          Skip
        </button>
      </div>
    </div>
  )
}
