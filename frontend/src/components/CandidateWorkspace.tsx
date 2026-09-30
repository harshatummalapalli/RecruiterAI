import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from 'react'
import { RotateCcw } from 'lucide-react'
import { initialsOf } from '../models/discovery'
import {
  FILTERS,
  filterCounts,
  matchesFilter,
  type CardFacts,
  type Decision,
  type FilterKey,
  type FunnelCopy,
  type WorkspaceCandidate,
} from '../models/workspace'
import { FeedbackPrompt } from './RoleControls'
import { reasonLabel } from '../models/roleWorkspace'
import './CandidateWorkspace.css'

const DECISIONS: Array<{ value: Decision; label: string; key: string }> = [
  { value: 'shortlist', label: 'Shortlist', key: 'S' },
  { value: 'maybe', label: 'Maybe', key: 'M' },
  { value: 'reject', label: 'Reject', key: 'R' },
]

const DECISION_LABEL: Record<Decision, string> = { shortlist: 'Shortlisted', maybe: 'Maybe', reject: 'Rejected' }

// Calm, role-aware empty states — never implies the SEARCH found nothing
// (an empty filter is not an empty search) and never uses "Complete"/
// "Search complete"/"No candidates found" language.
const EMPTY_STATE: Record<FilterKey, { title: string; body?: string }> = {
  all: { title: 'No candidates yet.' },
  to_review: { title: 'No candidates are waiting for review.' },
  shortlist: { title: 'No candidates have been shortlisted yet.', body: 'Candidates you shortlist will appear here.' },
  maybe: { title: 'No candidates are marked Maybe yet.' },
  reject: { title: 'No candidates have been rejected.' },
}

type Decisions = Record<string, Decision | undefined>

type Props = {
  /** Every candidate in the order they arrived (stable while the search fills in). */
  flatItems: WorkspaceCandidate[]
  decisions: Decisions
  selectedId: string | null
  onOpen: (id: string | null) => void
  onDecide: (id: string, decision: Decision | undefined) => void

  /** Recorded reasons for Maybe and Reject, by candidate. When `onFeedback` is given, Maybe and Reject ask for one. */
  feedback?: Record<string, { decision?: string | null; reason?: string | null; note?: string | null }>
  onFeedback?: (id: string, update: { reason?: string; note?: string }) => void
  /** The plain list only: no funnel, no grouping banner, no filter. Used for the reviewed-but-not-shown section. */
  compact?: boolean
  /** What the order of the list means, when it is not simply the order the profiles were read. */
  orderNote?: string
}

function Avatar({ name, url }: { name: string; url: string | null }) {
  const [failed, setFailed] = useState(false)
  if (url && !failed) {
    return <img className="ws-avatar" src={url} alt="" referrerPolicy="no-referrer" onError={() => setFailed(true)} />
  }
  return (
    <span className="ws-avatar ws-avatar--initials" aria-hidden="true">
      {initialsOf(name)}
    </span>
  )
}

// Above this many core requirements the dots shrink so the row stays compact. Every requirement still gets its dot.
const DENSE_DOTS = 10

// Exported so CandidateRecord can render the exact same dots — the ONE
// evidence fingerprint, never a second parallel dots implementation. See
// CandidateRecord.tsx's own "Evidence Fingerprint" section.
export function EvidenceDots({ facts }: { facts: CardFacts }) {
  if (facts.dots.length === 0) return null
  const shown = facts.dots.filter((dot) => dot.shown).length
  return (
    <span
      className={`ws-dots${facts.dots.length > DENSE_DOTS ? ' is-dense' : ''}`}
      role="img"
      aria-label={`${shown} of ${facts.dots.length} core requirements shown, not counting total years`}
    >
      {facts.dots.map((dot, index) => (
        <span key={index} className={`ws-dot${dot.shown ? ' is-shown' : ''}`} title={`${dot.label}${dot.shown ? '' : ' — not shown on the profile'}`} />
      ))}
    </span>
  )
}

type CardProps = {
  item: WorkspaceCandidate
  decision: Decision | undefined
  selected: boolean
  onOpen: () => void
  onDecide: (decision: Decision) => void
  register: (element: HTMLElement | null) => void
  /** The reason prompt, when one is open, and the recorded reason line when one is not. */
  prompt?: ReactNode
  reason?: string | null
}

// One click opens the full record — no separate "Proof" preview mode. The card itself only ever shows a
// short preview of the evidence; the full requirement ledger and quotes live in the record pane.
function CandidateCard({ item, decision, selected, onOpen, onDecide, register, prompt, reason }: CardProps) {
  const { candidate, facts } = item
  const place = [candidate.title, candidate.company !== 'Not specified' ? candidate.company : null, candidate.location !== 'Not specified' ? candidate.location : null]
    .filter(Boolean)
    .join(' · ')
  const onCardClick = (event: MouseEvent<HTMLElement>) => {
    if ((event.target as HTMLElement).closest('button, a')) return
    onOpen()
  }

  return (
    <article
      ref={register}
      tabIndex={-1}
      data-card-id={candidate.id}
      className={`ws-card${selected ? ' is-selected' : ''}${decision ? ` is-${decision}` : ''}`}
      aria-label={candidate.name}
      onClick={onCardClick}
    >
      <div className="ws-card__who">
        <Avatar name={candidate.name} url={candidate.photoUrl} />
        <div className="ws-card__identity">
          <h3 className="ws-card__name">{candidate.name}</h3>
          <p className="ws-card__role">{place}</p>
        </div>
      </div>

      {/* Dots only — the ONE evidence fingerprint. The "N core requirements
         shown · M in described work" sentence this used to pair with is
         gone: the dots already say this, and the full requirement-by-
         requirement detail lives one click away in the Candidate Record's
         own Evidence for this role section. Never restate it here. */}
      {facts.dots.length > 0 ? (
        <div className="ws-card__why">
          <EvidenceDots facts={facts} />
        </div>
      ) : null}

      {facts.chips.length > 0 || facts.watch.length > 0 ? (
        <div className="ws-card__chips">
          {facts.chips.map((chip) => (
            <span key={chip.label} className="ws-chip ws-chip--proof" title={chip.requirement}>
              {chip.label}
            </span>
          ))}
          {facts.watch.map((chip) => (
            <span key={chip.key} className="ws-chip ws-chip--watch">
              {chip.label}
            </span>
          ))}
        </div>
      ) : null}

      <div className="ws-card__actions">
        <div className="ws-decisions" role="group" aria-label={`Decision for ${candidate.name}`}>
          {DECISIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`ws-decision${decision === option.value ? ` is-active is-${option.value}` : ''}`}
              aria-pressed={decision === option.value}
              onClick={() => onDecide(option.value)}
              title={`${option.label} (${option.key})`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {prompt}
      {!prompt && reason ? <p className="ws-reason">{reason}</p> : null}
    </article>
  )
}

function SlimRow({
  item,
  decision,
  onUndo,
  onOpen,
  register,
}: {
  item: WorkspaceCandidate
  decision: Decision | undefined
  onUndo: () => void
  onOpen: () => void
  register: (element: HTMLElement | null) => void
}) {
  const { candidate } = item
  return (
    <div ref={register} tabIndex={-1} data-card-id={candidate.id} className="ws-slim">
      <span className="ws-slim__who">
        <strong>{candidate.name}</strong>
        <span>{candidate.title}</span>
      </span>
      <span className={`ws-slim__status${decision ? ` is-${decision}` : ''}`}>{decision ? DECISION_LABEL[decision] : 'Cleared'}</span>
      <button type="button" className="ws-link" onClick={onUndo}>
        <RotateCcw size={12} aria-hidden="true" /> Undo
      </button>
      <button type="button" className="ws-link ws-link--quiet" onClick={onOpen}>
        Full record
      </button>
    </div>
  )
}

function PendingRow({ item }: { item: WorkspaceCandidate }) {
  const { candidate } = item
  return (
    <div className="ws-pending" data-card-id={candidate.id}>
      <span className="ws-slim__who">
        <strong>{candidate.name}</strong>
        <span>{[candidate.title, candidate.company !== 'Not specified' ? candidate.company : null].filter(Boolean).join(' · ')}</span>
      </span>
      <span className="ws-pending__status">
        <span className="ws-pending__pulse" aria-hidden="true" />
        Reading profile…
      </span>
    </div>
  )
}

export function FunnelHeader({
  funnel,
  running,
  warnings,
}: {
  funnel: FunnelCopy | null
  running: { read: number; total: number } | null
  warnings: string[]
}) {
  return (
    <section className="ws-funnel" aria-label="How this list was made">
      <h3 className="ws-funnel__headline">{running ? `Reading profiles: ${running.read} of ${running.total}` : (funnel?.headline ?? '')}</h3>
      {!running && funnel?.scope ? <p className="ws-funnel__scope">{funnel.scope}</p> : null}
      {!running ? (
        <details className="ws-funnel__how">
          <summary>How this list was made</summary>
          <ul>
            <li>Each profile was read and each core requirement was checked against what it says. A requirement counts as shown only with a quote from the profile.</li>
            <li>The list is in the order the profiles were read. It is not a ranking, and nothing here says one person is better than another. It shows how much of the brief each profile shows.</li>
            {funnel?.notRead ? <li>{funnel.notRead}</li> : null}
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  )
}

export function CandidateWorkspace({
  flatItems,
  decisions,
  selectedId,
  onOpen,
  onDecide,
  feedback = {},
  onFeedback,
  compact = false,
  orderNote,
}: Props) {
  const [filter, setFilter] = useState<FilterKey>('all')
  // Cards whose decision no longer matches the filter stay in place as a slim row (with Undo) until the filter
  // changes, so nothing moves under the cursor. Maps to the decision they had before, for Undo.
  const [lingering, setLingering] = useState<Record<string, Decision | undefined>>({})
  const [focusId, setFocusId] = useState<string | null>(null)
  const cards = useRef(new Map<string, HTMLElement>())
  // Prompts the recruiter answered or skipped, and the reason they just chose (shown before the server confirms it).
  const [resolved, setResolved] = useState<Set<string>>(new Set())
  const [localReasons, setLocalReasons] = useState<Record<string, string>>({})

  const items = flatItems
  const ids = useMemo(() => items.map((item) => item.candidate.id), [items])
  const counts = useMemo(() => filterCounts(ids, decisions), [ids, decisions])

  // A Maybe or Reject asks for its reason until the recruiter gives one, adds a note, or skips. Never for a Shortlist.
  const promptOpen = (id: string): boolean => {
    const decision = decisions[id]
    if (!onFeedback || (decision !== 'maybe' && decision !== 'reject')) return false
    if (resolved.has(id) || feedback[id]?.reason || feedback[id]?.note) return false
    return true
  }

  const visibleItems = items.filter((item) => item.facts.section === 'preparing' || matchesFilter(filter, decisions[item.candidate.id]) || item.candidate.id in lingering)

  // What each visible entry renders as.
  const modeOf = (item: WorkspaceCandidate): 'pending' | 'slim' | 'card' => {
    const id = item.candidate.id
    if (item.facts.section === 'preparing') return 'pending'
    if (id in lingering) return 'slim'
    if (filter === 'all' && decisions[id] === 'reject' && !promptOpen(id)) return 'slim'
    return 'card'
  }

  const navIds = visibleItems.map((item) => item.candidate.id).filter((id) => {
    const item = items.find((entry) => entry.candidate.id === id)
    return item ? modeOf(item) === 'card' : false
  })

  useEffect(() => {
    if (!focusId) return
    cards.current.get(focusId)?.focus({ preventScroll: false })
    setFocusId(null)
  }, [focusId])

  const register = useCallback(
    (id: string) => (element: HTMLElement | null) => {
      if (element) cards.current.set(id, element)
      else cards.current.delete(id)
    },
    [],
  )

  const changeFilter = (next: FilterKey) => {
    setFilter(next)
    setLingering({})
    if (selectedId && !matchesFilter(next, decisions[selectedId])) onOpen(null)
  }

  const decide = (id: string, choice: Decision) => {
    const previous = decisions[id]
    const next = previous === choice ? undefined : choice
    // Where focus should go if this card collapses.
    const position = navIds.indexOf(id)
    const after = position >= 0 ? (navIds[position + 1] ?? navIds[position - 1] ?? null) : null
    const leavesFilter = !matchesFilter(filter, next)
    // A reject collapses straight away unless it is about to ask why; then it collapses once that is answered.
    const asksWhy = Boolean(onFeedback) && (next === 'maybe' || next === 'reject')
    const collapsesInAll = filter === 'all' && next === 'reject' && !asksWhy
    setResolved((current) => {
      const rest = new Set(current)
      rest.delete(id)
      return rest
    })
    setLocalReasons((current) => {
      const { [id]: _gone, ...rest } = current
      return rest
    })
    if (leavesFilter) setLingering((current) => ({ ...current, [id]: previous }))
    onDecide(id, next)
    if (leavesFilter || collapsesInAll) setFocusId(after)
  }

  // The recruiter answered (a reason or a note) or skipped. The card stays where it is; a reject then collapses.
  const closePrompt = (id: string) => {
    const position = navIds.indexOf(id)
    const after = position >= 0 ? (navIds[position + 1] ?? navIds[position - 1] ?? null) : null
    setResolved((current) => new Set(current).add(id))
    if (filter === 'all' && decisions[id] === 'reject') setFocusId(after)
  }

  const giveReason = (id: string, reason: string) => {
    setLocalReasons((current) => ({ ...current, [id]: reason }))
    onFeedback?.(id, { reason })
    closePrompt(id)
  }

  const giveNote = (id: string, note: string) => {
    onFeedback?.(id, { note })
    closePrompt(id)
  }

  const undo = (id: string) => {
    const restore = id in lingering ? lingering[id] : undefined
    setLingering((current) => {
      const { [id]: _removed, ...rest } = current
      return rest
    })
    onDecide(id, restore)
  }

  const currentCardId = (): string | null => {
    const active = document.activeElement as HTMLElement | null
    return active?.closest<HTMLElement>('[data-card-id]')?.dataset.cardId ?? null
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement
    if (target.closest('input, textarea, select, [contenteditable="true"]')) return
    if (event.metaKey || event.ctrlKey || event.altKey) return
    const key = event.key.toLowerCase()
    const id = currentCardId()

    if (key === 'j' || key === 'k') {
      event.preventDefault()
      const position = id ? navIds.indexOf(id) : -1
      const next = key === 'j' ? navIds[Math.min(position + 1, navIds.length - 1)] : navIds[Math.max(position - 1, 0)]
      if (next) setFocusId(next)
      return
    }
    if (!id) return
    if (key === 's' || key === 'm' || key === 'r') {
      if (!navIds.includes(id)) return
      event.preventDefault()
      decide(id, key === 's' ? 'shortlist' : key === 'm' ? 'maybe' : 'reject')
      return
    }
    if (key === 'enter' && target.hasAttribute('data-card-id')) {
      event.preventDefault()
      onOpen(id)
      return
    }
    if (key === 'escape' && selectedId) {
      onOpen(null)
    }
  }

  const renderEntry = (item: WorkspaceCandidate) => {
    const id = item.candidate.id
    const mode = modeOf(item)
    if (mode === 'pending') return <PendingRow key={id} item={item} />
    if (mode === 'slim') {
      return <SlimRow key={id} item={item} decision={decisions[id]} onUndo={() => undo(id)} onOpen={() => onOpen(id)} register={register(id)} />
    }
    const decision = decisions[id]
    const open = promptOpen(id)
    const recorded = reasonLabel(decision, localReasons[id] ?? feedback[id]?.reason)
    return (
      <CandidateCard
        key={id}
        item={item}
        decision={decision}
        prompt={
          open && (decision === 'maybe' || decision === 'reject') ? (
            <FeedbackPrompt decision={decision} onReason={(reason) => giveReason(id, reason)} onNote={(note) => giveNote(id, note)} onSkip={() => closePrompt(id)} />
          ) : undefined
        }
        reason={recorded ? `Reason: ${recorded}` : undefined}
        selected={selectedId === id}
        onOpen={() => onOpen(id)}
        onDecide={(choice) => decide(id, choice)}
        register={register(id)}
      />
    )
  }

  return (
    <div className={`ws${compact ? ' ws--compact' : ''}`}>
      {compact ? null : (
      <div className="ws-filter" role="group" aria-label="Filter by decision">
        {FILTERS.map((option) => (
          <button
            key={option.key}
            type="button"
            className={`ws-filter__option${filter === option.key ? ' is-active' : ''}`}
            aria-pressed={filter === option.key}
            onClick={() => changeFilter(option.key)}
          >
            {option.label} <span className="ws-filter__count">{counts[option.key]}</span>
          </button>
        ))}
      </div>
      )}

      <div className="ws-list" onKeyDown={onKeyDown}>
        {visibleItems.length === 0 ? (
          <div className="ws-empty">
            <p className="ws-empty__title">{EMPTY_STATE[filter].title}</p>
            {EMPTY_STATE[filter].body ? <p className="ws-empty__body">{EMPTY_STATE[filter].body}</p> : null}
          </div>
        ) : null}

        {visibleItems.length > 0 ? <p className="ws-note">{orderNote ?? 'In the order they were read.'}</p> : null}
        <div className="ws-section__items">{visibleItems.map(renderEntry)}</div>
      </div>
    </div>
  )
}
