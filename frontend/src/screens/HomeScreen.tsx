// "Your searches" — the top-level landing screen (frozen handoff, section 5,
// restructured under the global product shell). Active / Drafts / Archived,
// a table of roles, and only the row actions that are actually wired to a
// real backend call (Open, Pause, Resume, Continue). No Archive/Rename/
// Delete/Restore here — the backend has no archived-role concept and no
// delete/rename endpoints, so those stay out rather than being faked.
// Account access (Appearance/Sign out) lives in the global shell now
// (GlobalShell/AccountControl), not here — Home is just its content.
import { useEffect, useMemo, useRef, useState } from 'react'
import { MoreHorizontal, Plus, Search } from 'lucide-react'
import type { SearchListItem } from '../types'
import './HomeScreen.css'

type Tab = 'active' | 'drafts' | 'archived'
type ActiveFilter = 'all' | 'searching' | 'paused'

function getGreeting(hour: number): string {
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

// A handful of legacy searches carry a JD's own leading heading line (e.g.
// literally "Job Description") as their title — a real fallback that
// predates role labeling, never a value worth showing as if it were a role
// name. Recognized narrowly, by exact generic phrasing only: never
// reinterprets or fabricates an actual title.
const GENERIC_TITLES = new Set(['job description', 'jd', 'untitled', ''])

function displayTitle(title: string): string {
  return GENERIC_TITLES.has(title.trim().toLowerCase()) ? 'Untitled search' : title
}

// Honest, count-derived activity text — no fabricated action history (no "You shortlisted Priya Raman"): the
// API doesn't carry a per-role activity log, so this only ever shows what SearchListItem actually provides.
function activeActivity(item: SearchListItem): { text: string; green: boolean } {
  if (item.role_status === 'paused') return { text: 'Paused', green: false }
  if (item.to_review_count !== null) {
    return { text: `${item.to_review_count} to review`, green: item.role_status === 'searching' }
  }
  if (item.new_count > 0) return { text: `${item.new_count} new`, green: item.role_status === 'searching' }
  return { text: item.status === 'complete' ? 'Complete' : '—', green: false }
}

function draftStage(status: string | null): { intake: string; activity: string } {
  if (status === 'ready') return { intake: 'Brief ready to confirm', activity: 'Brief drafted from job description' }
  if (status === 'needs_clarification') return { intake: 'Clarifying the role', activity: '2 questions left to answer' }
  return { intake: 'Just started', activity: 'Job description pasted' }
}

function timeAgo(iso: string | null): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return '—'
  const seconds = Math.max(0, (Date.now() - then) / 1000)
  if (seconds < 60) return 'Just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'} ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.floor(hours / 24)
  if (days === 1) return 'Yesterday'
  if (days < 7) return `${days} days ago`
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function RowMenu({
  actions,
  onClose,
}: {
  actions: Array<{ label: string; onClick: () => void }>
  onClose: () => void
}) {
  const ref = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const onDocClick = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose()
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [onClose])
  return (
    <div className="home-row-menu" ref={ref} role="menu">
      {actions.map((action) => (
        <button
          key={action.label}
          type="button"
          role="menuitem"
          className="home-row-menu__item"
          onClick={() => {
            action.onClick()
            onClose()
          }}
        >
          {action.label}
        </button>
      ))}
    </div>
  )
}

export function HomeScreen({
  items,
  recruiterName,
  onOpen,
  onNew,
  onPause,
  onResume,
}: {
  items: SearchListItem[]
  recruiterName: string
  onOpen: (item: Pick<SearchListItem, 'kind' | 'id'>) => void
  onNew: () => void
  onPause: (id: string) => void
  onResume: (id: string) => void
}) {
  const [tab, setTab] = useState<Tab>('active')
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>('all')
  const [query, setQuery] = useState('')
  const [openMenuId, setOpenMenuId] = useState<string | null>(null)

  const greeting = `${getGreeting(new Date().getHours())}, ${recruiterName}`

  const active = useMemo(() => items.filter((item) => item.kind === 'search'), [items])
  const drafts = useMemo(() => items.filter((item) => item.kind === 'draft'), [items])
  const archived: SearchListItem[] = [] // the backend has no archived-role concept yet — honestly empty, not faked

  const counts = { active: active.length, drafts: drafts.length, archived: archived.length }

  const visibleActive = useMemo(() => {
    let list = active
    if (activeFilter === 'searching') list = list.filter((item) => item.role_status === 'searching')
    else if (activeFilter === 'paused') list = list.filter((item) => item.role_status === 'paused')
    return list
  }, [active, activeFilter])

  const search = (list: SearchListItem[]) => {
    const q = query.trim().toLowerCase()
    if (!q) return list
    return list.filter((item) => item.title.toLowerCase().includes(q) || item.company.toLowerCase().includes(q))
  }

  const rows = tab === 'active' ? search(visibleActive) : tab === 'drafts' ? search(drafts) : search(archived)

  return (
    <div className="home">
      <header className="home__header">
        <div>
          <p className="home__greeting">{greeting}</p>
          <h1 className="home__title">Your searches</h1>
        </div>
        <button type="button" className="home__new" onClick={onNew}>
          <Plus size={15} aria-hidden="true" />
          New Search
        </button>
      </header>

      <div className="home__tabs" role="tablist">
        {(
          [
            ['active', 'Active', counts.active],
            ['drafts', 'Drafts', counts.drafts],
            ['archived', 'Archived', counts.archived],
          ] as const
        ).map(([key, label, count]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            className={`home__tab${tab === key ? ' is-active' : ''}`}
            onClick={() => setTab(key)}
          >
            {label} <span className="home__tab-count">{count}</span>
          </button>
        ))}
      </div>

      <div className="home__toolbar">
        {tab === 'active' ? (
          <div className="home__filter" role="group" aria-label="Filter active searches">
            {(
              [
                ['all', 'All'],
                ['searching', 'Searching'],
                ['paused', 'Paused'],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                className={`home__filter-option${activeFilter === key ? ' is-active' : ''}`}
                onClick={() => setActiveFilter(key)}
              >
                {label}
              </button>
            ))}
          </div>
        ) : (
          <span />
        )}
        <label className="home__search">
          <Search size={14} aria-hidden="true" />
          <input
            type="text"
            placeholder="Find a role or company"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
      </div>

      {tab !== 'archived' ? (
        <div className="home__grid home__grid--head" aria-hidden="true">
          <span>ROLE</span>
          <span>{tab === 'active' ? 'STATUS' : 'INTAKE'}</span>
          <span>ACTIVITY</span>
          <span>{tab === 'active' ? 'LAST ACTIVITY' : 'LAST EDITED'}</span>
          <span />
        </div>
      ) : (
        <div className="home__grid home__grid--head" aria-hidden="true">
          <span>ROLE</span>
          <span>STATUS</span>
          <span>ACTIVITY</span>
          <span>ARCHIVED</span>
          <span />
        </div>
      )}

      {rows.length === 0 ? (
        <div className="home__empty">
          <p className="home__empty-title">
            {query
              ? `No roles match "${query}"`
              : tab === 'active'
                ? active.length === 0
                  ? 'No active searches'
                  : 'No roles match this filter'
                : tab === 'drafts'
                  ? 'No drafts'
                  : 'No archived searches'}
          </p>
          <p className="home__empty-body">
            {query
              ? ''
              : tab === 'active'
                ? 'Create a new search to start finding candidates.'
                : tab === 'drafts'
                  ? "Drafts haven't been searched yet. Confirm the brief to start a search."
                  : 'Archived roles keep their full history. Restore one to continue searching.'}
          </p>
        </div>
      ) : (
        <div className="home__rows">
          {rows.map((item) => {
            const activity = tab === 'active' ? activeActivity(item) : tab === 'drafts' ? draftStage(item.status) : null
            return (
              <div key={`${item.kind}:${item.id}`} className="home__row" onClick={() => onOpen(item)}>
                <div className="home__cell home__cell--role">
                  <p className="home__role-title">{displayTitle(item.title)}</p>
                  <p className="home__role-sub">{[item.company, item.place].filter(Boolean).join(' · ')}</p>
                </div>

                <div className="home__cell">
                  {tab === 'active' ? (
                    <span className={`home__status home__status--${item.role_status ?? 'searching'}`}>
                      <span className="home__status-dot" aria-hidden="true" />
                      {item.role_status === 'paused' ? 'Paused' : 'Searching'}
                    </span>
                  ) : tab === 'drafts' ? (
                    <span className="home__status home__status--draft">
                      <span className="home__status-dash" aria-hidden="true" />
                      {draftStage(item.status).intake}
                    </span>
                  ) : (
                    <span className="home__status home__status--archived">Archived</span>
                  )}
                </div>

                <div className="home__cell">
                  {tab === 'active' && activity && 'green' in activity ? (
                    <span className={activity.green ? 'home__activity home__activity--green' : 'home__activity'}>{activity.text}</span>
                  ) : tab === 'drafts' && activity && 'intake' in activity ? (
                    <span className="home__activity">{activity.activity}</span>
                  ) : (
                    <span className="home__activity home__activity--faint">—</span>
                  )}
                </div>

                <div className="home__cell home__cell--time">{timeAgo(item.updated_at)}</div>

                <div className="home__cell home__cell--menu">
                  <button
                    type="button"
                    className="home__menu-trigger"
                    aria-label="More actions"
                    onClick={(event) => {
                      event.stopPropagation()
                      setOpenMenuId((current) => (current === item.id ? null : item.id))
                    }}
                  >
                    <MoreHorizontal size={16} aria-hidden="true" />
                  </button>
                  {openMenuId === item.id ? (
                    <div onClick={(event) => event.stopPropagation()}>
                      <RowMenu
                        onClose={() => setOpenMenuId(null)}
                        actions={
                          tab === 'drafts'
                            ? [{ label: 'Continue', onClick: () => onOpen(item) }]
                            : item.role_status === 'paused'
                              ? [
                                  { label: 'Open', onClick: () => onOpen(item) },
                                  { label: 'Resume', onClick: () => onResume(item.id) },
                                ]
                              : [
                                  { label: 'Open', onClick: () => onOpen(item) },
                                  { label: 'Pause', onClick: () => onPause(item.id) },
                                ]
                        }
                      />
                    </div>
                  ) : null}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
