import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react'
import { ChevronDown, ChevronUp, RotateCcw } from 'lucide-react'
import { initialsOf } from '../models/discovery'
import {
  FILTERS,
  SECTION_COPY,
  filterCounts,
  groupBySection,
  matchesFilter,
  type CardFacts,
  type Decision,
  type FilterKey,
  type FunnelCopy,
  type SectionKey,
  type WorkspaceCandidate,
} from '../models/workspace'
import './CandidateWorkspace.css'

const DECISIONS: Array<{ value: Decision; label: string; key: string }> = [
  { value: 'shortlist', label: 'Shortlist', key: 'S' },
  { value: 'maybe', label: 'Maybe', key: 'M' },
  { value: 'reject', label: 'Reject', key: 'R' },
]

const DECISION_LABEL: Record<Decision, string> = { shortlist: 'Shortlisted', maybe: 'Maybe', reject: 'Rejected' }

// The thin group is collapsed until asked for; its count stays visible.
const COLLAPSED_BY_DEFAULT: SectionKey[] = ['thin']

type Decisions = Record<string, Decision | undefined>

type Props = {
  /** Every candidate in the order they arrived (stable while the search fills in). */
  flatItems: WorkspaceCandidate[]
  /** The same candidates in the order the search returned them, used inside each group once arranged. */
  arrangedItems: WorkspaceCandidate[]
  decisions: Decisions
  selectedId: string | null
  onOpen: (id: string | null) => void
  onDecide: (id: string, decision: Decision | undefined) => void

  arranged: boolean
  canArrange: boolean
  onArrange: () => void

  running: { read: number; total: number } | null
  funnel: FunnelCopy | null
  warnings: string[]
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

function EvidenceDots({ facts }: { facts: CardFacts }) {
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
  expanded: boolean
  onToggleExpand: () => void
  onOpen: () => void
  onDecide: (decision: Decision) => void
  register: (element: HTMLElement | null) => void
}

function CandidateCard({ item, decision, selected, expanded, onToggleExpand, onOpen, onDecide, register }: CardProps) {
  const { candidate, facts } = item
  const place = [candidate.title, candidate.company !== 'Not specified' ? candidate.company : null, candidate.location !== 'Not specified' ? candidate.location : null]
    .filter(Boolean)
    .join(' · ')
  const showHeadline = candidate.headline && candidate.headline.trim().toLowerCase() !== candidate.title.trim().toLowerCase()
  const hasProof = facts.chips.length > 0 || facts.notProven.length > 0 || facts.concerns.length > 0

  const onCardClick = (event: MouseEvent<HTMLElement>) => {
    if ((event.target as HTMLElement).closest('button, a')) return
    if (hasProof) onToggleExpand()
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
          <div className="ws-card__nameline">
            <h3 className="ws-card__name">{candidate.name}</h3>
            {candidate.openToWork === true ? (
              <span className="ws-chip ws-chip--neutral" title="Stated on the candidate's own profile. Shown for information only.">
                Open to work
              </span>
            ) : null}
          </div>
          <p className="ws-card__role">{place}</p>
          {showHeadline ? <p className="ws-card__headline">{candidate.headline}</p> : null}
        </div>
      </div>

      {facts.why ? (
        <div className="ws-card__why">
          <EvidenceDots facts={facts} />
          <span>{facts.why}</span>
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
        <button type="button" className="ws-link" onClick={onOpen}>
          Full record
        </button>
        {hasProof ? (
          <button type="button" className="ws-link ws-link--quiet" aria-expanded={expanded} onClick={onToggleExpand}>
            Proof {expanded ? <ChevronUp size={13} aria-hidden="true" /> : <ChevronDown size={13} aria-hidden="true" />}
          </button>
        ) : null}
      </div>

      {expanded ? (
        <div className="ws-card__proof">
          {facts.chips.length > 0 ? (
            <ul className="ws-quotes">
              {facts.chips.map((chip) => (
                <li key={chip.label}>
                  <p className="ws-quotes__req">{chip.requirement.replace(/[.\s]+$/, '')}</p>
                  <p className="ws-quotes__quote">“{chip.quote}”</p>
                  {chip.source ? <p className="ws-quotes__source">{chip.source}</p> : null}
                </li>
              ))}
            </ul>
          ) : null}
          {facts.notProven.length > 0 ? (
            <p className="ws-notproven">
              <strong>Not proven on the profile:</strong> {facts.notProven.join(' · ')}
            </p>
          ) : null}
          {facts.concerns.length > 0 ? (
            <ul className="ws-concerns">
              {facts.concerns.map((concern) => (
                <li key={concern}>{concern}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
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
  sectionCounts,
  warnings,
}: {
  funnel: FunnelCopy | null
  running: { read: number; total: number } | null
  sectionCounts: Array<{ key: SectionKey; count: number }> | null
  warnings: string[]
}) {
  return (
    <section className="ws-funnel" aria-label="How this list was made">
      <h3 className="ws-funnel__headline">{running ? `Reading profiles: ${running.read} of ${running.total}` : (funnel?.headline ?? '')}</h3>
      {!running && funnel?.scope ? <p className="ws-funnel__scope">{funnel.scope}</p> : null}
      {sectionCounts && sectionCounts.length > 0 ? (
        <p className="ws-funnel__counts">
          {sectionCounts.map((entry, index) => (
            <span key={entry.key}>
              {index > 0 ? ' · ' : ''}
              <strong>{entry.count}</strong> {SECTION_COPY[entry.key].title.toLowerCase()}
            </span>
          ))}
        </p>
      ) : null}
      {!running ? (
        <details className="ws-funnel__how">
          <summary>How this list was made</summary>
          <ul>
            <li>Each profile was read and each core requirement was checked against what it says. A requirement counts as shown only with a quote from the profile.</li>
            <li>
              Start here: at least 60% of the core requirements (not counting total years) are shown. Worth a look: at least one is. Not much shown yet: none is.
            </li>
            <li>The order inside a group is not a ranking, and no group says one person is better than another. It says how much of the brief their profile shows.</li>
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
  arrangedItems,
  decisions,
  selectedId,
  onOpen,
  onDecide,
  arranged,
  canArrange,
  onArrange,
  running,
  funnel,
  warnings,
}: Props) {
  const [filter, setFilter] = useState<FilterKey>('all')
  // Cards whose decision no longer matches the filter stay in place as a slim row (with Undo) until the filter
  // changes, so nothing moves under the cursor. Maps to the decision they had before, for Undo.
  const [lingering, setLingering] = useState<Record<string, Decision | undefined>>({})
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [openSections, setOpenSections] = useState<Set<SectionKey>>(new Set())
  const [closedSections, setClosedSections] = useState<Set<SectionKey>>(new Set())
  const [focusId, setFocusId] = useState<string | null>(null)
  const cards = useRef(new Map<string, HTMLElement>())

  const items = arranged ? arrangedItems : flatItems
  const ids = useMemo(() => items.map((item) => item.candidate.id), [items])
  const counts = useMemo(() => filterCounts(ids, decisions), [ids, decisions])

  const isCollapsed = (key: SectionKey) => (COLLAPSED_BY_DEFAULT.includes(key) ? !openSections.has(key) : closedSections.has(key))
  const toggleSection = (key: SectionKey) => {
    if (COLLAPSED_BY_DEFAULT.includes(key)) {
      setOpenSections((current) => {
        const next = new Set(current)
        if (next.has(key)) next.delete(key)
        else next.add(key)
        return next
      })
    } else {
      setClosedSections((current) => {
        const next = new Set(current)
        if (next.has(key)) next.delete(key)
        else next.add(key)
        return next
      })
    }
  }

  const visibleItems = items.filter((item) => item.facts.section === 'preparing' || matchesFilter(filter, decisions[item.candidate.id]) || item.candidate.id in lingering)

  // What each visible entry renders as.
  const modeOf = (item: WorkspaceCandidate): 'pending' | 'slim' | 'card' => {
    const id = item.candidate.id
    if (item.facts.section === 'preparing') return 'pending'
    if (id in lingering) return 'slim'
    if (filter === 'all' && decisions[id] === 'reject') return 'slim'
    return 'card'
  }

  const groups = arranged ? groupBySection(visibleItems) : null
  const shownIds = groups
    ? groups.flatMap((group) => (isCollapsed(group.key) ? [] : group.items.map((item) => item.candidate.id)))
    : visibleItems.map((item) => item.candidate.id)
  const navIds = shownIds.filter((id) => {
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
    const collapsesInAll = filter === 'all' && next === 'reject'
    if (leavesFilter) setLingering((current) => ({ ...current, [id]: previous }))
    onDecide(id, next)
    if (leavesFilter || collapsesInAll) setFocusId(after)
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
    if (key === 'escape') {
      if (expanded.has(id)) {
        setExpanded((current) => {
          const next = new Set(current)
          next.delete(id)
          return next
        })
      } else if (selectedId) {
        onOpen(null)
      }
    }
  }

  const toggleExpand = (id: string) =>
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const renderEntry = (item: WorkspaceCandidate) => {
    const id = item.candidate.id
    const mode = modeOf(item)
    if (mode === 'pending') return <PendingRow key={id} item={item} />
    if (mode === 'slim') {
      return <SlimRow key={id} item={item} decision={decisions[id]} onUndo={() => undo(id)} onOpen={() => onOpen(id)} register={register(id)} />
    }
    return (
      <CandidateCard
        key={id}
        item={item}
        decision={decisions[id]}
        selected={selectedId === id}
        expanded={expanded.has(id)}
        onToggleExpand={() => toggleExpand(id)}
        onOpen={() => onOpen(id)}
        onDecide={(choice) => decide(id, choice)}
        register={register(id)}
      />
    )
  }

  const sectionCounts = arranged ? groupBySection(items).map((group) => ({ key: group.key, count: group.items.length })) : null

  return (
    <div className="ws">
      <FunnelHeader funnel={funnel} running={running} sectionCounts={sectionCounts} warnings={warnings} />

      {canArrange ? (
        <div className="ws-banner" role="status">
          <p>All {items.length} profiles are read. Group them by how much of the brief each one shows?</p>
          <button type="button" className="ws-banner__button" onClick={onArrange}>
            Group them
          </button>
        </div>
      ) : null}

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

      <div className="ws-list" onKeyDown={onKeyDown}>
        {visibleItems.length === 0 ? (
          <p className="ws-empty">
            {filter === 'to_review' ? 'Everything has a decision.' : `No candidates are ${FILTERS.find((entry) => entry.key === filter)?.label.toLowerCase()} yet.`}
          </p>
        ) : null}

        {groups ? (
          <>
            <p className="ws-note">Grouped by how much of the brief each profile shows. The order inside a group is not a ranking.</p>
            {groups.map((group) => {
              const key = group.key
              const total = items.filter((item) => item.facts.section === key).length
              const collapsed = isCollapsed(key)
              return (
                <section key={key} className="ws-section" aria-label={SECTION_COPY[key].title}>
                  <header className="ws-section__head">
                    <button type="button" className="ws-section__toggle" aria-expanded={!collapsed} onClick={() => toggleSection(key)}>
                      {collapsed ? <ChevronDown size={15} aria-hidden="true" /> : <ChevronUp size={15} aria-hidden="true" />}
                      <span className="ws-section__title">{SECTION_COPY[key].title}</span>
                      <span className="ws-section__count">{filter === 'all' || group.items.length === total ? total : `${group.items.length} of ${total}`}</span>
                    </button>
                    <p className="ws-section__basis">{SECTION_COPY[key].basis}</p>
                  </header>
                  {collapsed ? null : <div className="ws-section__items">{group.items.map(renderEntry)}</div>}
                </section>
              )
            })}
          </>
        ) : (
          <>
            {visibleItems.length > 0 ? <p className="ws-note">In the order they were read.</p> : null}
            <div className="ws-section__items">{visibleItems.map(renderEntry)}</div>
          </>
        )}
      </div>
    </div>
  )
}
