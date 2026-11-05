// Home — the landing screen, decluttered to the mockup: a short welcome, one
// "Start a new search" call, then a card grid of recent searches (active first,
// then drafts). No tabs / filter pills / table header anymore. Only the row
// actions actually wired to a backend call (Open, Pause, Resume, Continue) —
// no faked Archive/Rename/Delete. Account access lives in the global shell.
import { useEffect, useMemo, useRef, useState } from 'react'
import { MoreHorizontal } from 'lucide-react'
import type { SearchListItem } from '../types'
import './HomeScreen.css'

function getGreeting(hour: number): string {
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

// A few legacy searches carry a JD's own heading line (literally "Job
// Description") as their title — a real fallback, never a role name. Recognized
// narrowly, by exact generic phrasing only; never fabricates a title.
const GENERIC_TITLES = new Set(['job description', 'jd', 'untitled', ''])

function displayTitle(title: string): string {
  return GENERIC_TITLES.has(title.trim().toLowerCase()) ? 'Untitled search' : title
}

// Honest, count-derived activity text — the API carries no per-role activity
// log, so this only shows what SearchListItem actually provides.
function activeActivity(item: SearchListItem): { text: string; green: boolean } {
  if (item.role_status === 'paused') return { text: 'Paused', green: false }
  if (item.to_review_count !== null) return { text: `${item.to_review_count} to review`, green: item.role_status === 'searching' }
  if (item.new_count > 0) return { text: `${item.new_count} new`, green: item.role_status === 'searching' }
  return { text: item.status === 'complete' ? 'Complete' : '—', green: false }
}

function draftActivity(status: string | null): string {
  if (status === 'ready') return 'Brief ready to confirm'
  if (status === 'needs_clarification') return 'Clarifying the role'
  return 'Finish the brief'
}

function RowMenu({ actions, onClose }: { actions: Array<{ label: string; onClick: () => void }>; onClose: () => void }) {
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

function SearchCard({
  item,
  onOpen,
  onPause,
  onResume,
  openMenu,
  setOpenMenu,
}: {
  item: SearchListItem
  onOpen: (item: Pick<SearchListItem, 'kind' | 'id'>) => void
  onPause: (id: string) => void
  onResume: (id: string) => void
  openMenu: boolean
  setOpenMenu: (open: boolean) => void
}) {
  const isDraft = item.kind === 'draft'
  const paused = item.role_status === 'paused'
  const meta = [item.company, item.place].filter(Boolean).join(' · ') || (isDraft ? 'Not yet searched' : '—')
  const activity = isDraft ? draftActivity(item.status) : activeActivity(item)
  const actions = isDraft
    ? [{ label: 'Continue', onClick: () => onOpen(item) }]
    : paused
      ? [{ label: 'Open', onClick: () => onOpen(item) }, { label: 'Resume', onClick: () => onResume(item.id) }]
      : [{ label: 'Open', onClick: () => onOpen(item) }, { label: 'Pause', onClick: () => onPause(item.id) }]

  return (
    <div className="home__row" role="button" tabIndex={0} onClick={() => onOpen(item)}>
      <div className="home__rc-top">
        <span className="home__rc-name">{displayTitle(item.title)}</span>
        {isDraft ? (
          <span className="home__status home__status--draft">Draft</span>
        ) : paused ? (
          <span className="home__status home__status--paused">Paused</span>
        ) : (
          <span className="home__status home__status--searching">
            <span className="home__status-dot" aria-hidden="true" />
            Searching
          </span>
        )}
      </div>
      <p className="home__rc-meta">{meta}</p>
      <p className={`home__rc-foot${!isDraft && typeof activity === 'object' && activity.green ? ' is-green' : ''}`}>
        {typeof activity === 'string' ? activity : activity.text}
      </p>

      <div className="home__cell--menu">
        <button
          type="button"
          className="home__menu-trigger"
          aria-label="More actions"
          onClick={(event) => {
            event.stopPropagation()
            setOpenMenu(!openMenu)
          }}
        >
          <MoreHorizontal size={16} aria-hidden="true" />
        </button>
        {openMenu ? (
          <div onClick={(event) => event.stopPropagation()}>
            <RowMenu onClose={() => setOpenMenu(false)} actions={actions} />
          </div>
        ) : null}
      </div>
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
  const [openMenuId, setOpenMenuId] = useState<string | null>(null)

  // Active searches first, then drafts — the order the cards read in.
  const ordered = useMemo(
    () => [...items.filter((i) => i.kind === 'search'), ...items.filter((i) => i.kind === 'draft')],
    [items],
  )

  return (
    <div className="home">
      <div className="home__hero">
        <p className="home__eyebrow">Welcome back</p>
        <h1 className="home__title">{getGreeting(new Date().getHours())}, {recruiterName}.</h1>
      </div>

      <div className="home__newsearch">
        <button type="button" className="home__new" onClick={onNew}>
          Start a new search
        </button>
        <span className="home__np">
          Give me a role and the lines I must not cross. I read the description, plan the search, and bring back the
          strongest people — you decide.
        </span>
      </div>

      {ordered.length === 0 ? (
        <div className="home__empty">
          <p className="home__empty-title">No searches yet</p>
          <p className="home__empty-body">Start a new search to find your first candidates.</p>
        </div>
      ) : (
        <>
          <h2 className="home__recent">Recent searches</h2>
          <div className="home__grid">
            {ordered.map((item) => (
              <SearchCard
                key={`${item.kind}:${item.id}`}
                item={item}
                onOpen={onOpen}
                onPause={onPause}
                onResume={onResume}
                openMenu={openMenuId === `${item.kind}:${item.id}`}
                setOpenMenu={(open) => setOpenMenuId(open ? `${item.kind}:${item.id}` : null)}
              />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
