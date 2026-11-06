// Home — live work only. A short welcome, a New-search call, then the Active
// roles grouped by where attention is owed (review → searching → paused →
// drafts). Completed work lives behind its own tab, never the main grid.
// Status is the role lifecycle (roleLifecycle.ts), never the pipeline flag.
import { useEffect, useMemo, useRef, useState } from 'react'
import { MoreHorizontal } from 'lucide-react'
import type { SearchListItem } from '../types'
import {
  activitySummary,
  displayTitle,
  groupActive,
  partitionRoles,
  roleStatus,
  timeAgo,
  type Overrides,
} from '../models/roleLifecycle'
import { sidebarSubtitle } from '../models/roleWorkspace'
import './HomeScreen.css'

function getGreeting(hour: number): string {
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
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

type CardActions = {
  onOpen: (item: Pick<SearchListItem, 'kind' | 'id'>) => void
  onPause: (id: string) => void
  onResume: (id: string) => void
  onClose: (id: string) => void
  onReopen: (id: string) => void
}

function RoleCard({
  item,
  completed,
  actions,
  openMenu,
  setOpenMenu,
}: {
  item: SearchListItem
  completed: boolean
  actions: CardActions
  openMenu: boolean
  setOpenMenu: (open: boolean) => void
}) {
  const status = roleStatus(item)
  const meta = sidebarSubtitle(item) || (item.kind === 'draft' ? 'Not yet searched' : '—')
  const foot = completed ? { text: `Closed · last active ${timeAgo(item.updated_at)}`, emphasis: false } : activitySummary(item)

  const menuActions = completed
    ? [{ label: 'View', onClick: () => actions.onOpen(item) }, { label: 'Reopen (move to Active)', onClick: () => actions.onReopen(item.id) }]
    : item.kind === 'draft'
      ? [{ label: 'Continue', onClick: () => actions.onOpen(item) }, { label: 'Close', onClick: () => actions.onClose(item.id) }]
      : status === 'paused'
        ? [
            { label: 'Open', onClick: () => actions.onOpen(item) },
            { label: 'Resume', onClick: () => actions.onResume(item.id) },
            { label: 'Close', onClick: () => actions.onClose(item.id) },
          ]
        : [
            { label: 'Open', onClick: () => actions.onOpen(item) },
            { label: 'Pause', onClick: () => actions.onPause(item.id) },
            { label: 'Close', onClick: () => actions.onClose(item.id) },
          ]

  const badgeClass = completed ? 'complete' : status
  const badgeText = completed ? 'Closed' : status === 'searching' ? 'Searching' : status === 'paused' ? 'Paused' : 'Draft'

  return (
    <div className="home__row" role="button" tabIndex={0} onClick={() => actions.onOpen(item)}>
      <div className="home__rc-top">
        <span className="home__rc-name">{displayTitle(item.title)}</span>
        <span className={`home__status home__status--${badgeClass}`}>
          {!completed && status === 'searching' ? <span className="home__status-dot" aria-hidden="true" /> : null}
          {badgeText}
        </span>
      </div>
      <p className="home__rc-meta">{meta}</p>
      <p className={`home__rc-foot${foot.emphasis ? ' is-green' : ''}`}>{foot.text}</p>

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
            <RowMenu onClose={() => setOpenMenu(false)} actions={menuActions} />
          </div>
        ) : null}
      </div>
    </div>
  )
}

export function HomeScreen({
  items,
  overrides,
  loading,
  recruiterName,
  onOpen,
  onNew,
  onPause,
  onResume,
  onClose,
  onReopen,
}: {
  items: SearchListItem[]
  overrides: Overrides
  loading: boolean
  recruiterName: string
  onOpen: (item: Pick<SearchListItem, 'kind' | 'id'>) => void
  onNew: () => void
  onPause: (id: string) => void
  onResume: (id: string) => void
  onClose: (id: string) => void
  onReopen: (id: string) => void
}) {
  const [view, setView] = useState<'active' | 'completed'>('active')
  const [openMenuKey, setOpenMenuKey] = useState<string | null>(null)

  const { active, completed } = useMemo(() => partitionRoles(items, overrides), [items, overrides])
  const groups = useMemo(() => groupActive(active), [active])
  const actions: CardActions = { onOpen, onPause, onResume, onClose, onReopen }

  const keyOf = (item: SearchListItem) => `${item.kind}:${item.id}`

  const renderCard = (item: SearchListItem, inCompleted: boolean) => (
    <RoleCard
      key={keyOf(item)}
      item={item}
      completed={inCompleted}
      actions={actions}
      openMenu={openMenuKey === keyOf(item)}
      setOpenMenu={(open) => setOpenMenuKey(open ? keyOf(item) : null)}
    />
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

      <div className="home__tabs" role="tablist" aria-label="Searches">
        <button type="button" role="tab" aria-selected={view === 'active'} className={`home__tab${view === 'active' ? ' is-active' : ''}`} onClick={() => setView('active')}>
          Active <span className="home__tab-count">{active.length}</span>
        </button>
        <button type="button" role="tab" aria-selected={view === 'completed'} className={`home__tab${view === 'completed' ? ' is-active' : ''}`} onClick={() => setView('completed')}>
          Completed <span className="home__tab-count">{completed.length}</span>
        </button>
      </div>

      {loading && items.length === 0 ? (
        <div className="home__grid">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="home__row home__row--skeleton" aria-hidden="true">
              <span className="home__sk home__sk--title" />
              <span className="home__sk home__sk--meta" />
              <span className="home__sk home__sk--foot" />
            </div>
          ))}
        </div>
      ) : view === 'active' ? (
        active.length === 0 ? (
          <div className="home__empty">
            <p className="home__empty-title">No active searches</p>
            <p className="home__empty-body">Start a new search to find candidates. Completed work moves to the Completed tab.</p>
          </div>
        ) : (
          groups.map((group) => (
            <section key={group.key} className="home__group" aria-label={group.label}>
              <h2 className="home__group-title">
                {group.label} <span className="home__group-count">{group.items.length}</span>
              </h2>
              <div className="home__grid">{group.items.map((item) => renderCard(item, false))}</div>
            </section>
          ))
        )
      ) : completed.length === 0 ? (
        <div className="home__empty">
          <p className="home__empty-title">Nothing completed yet</p>
          <p className="home__empty-body">Roles you Close — or that stay idle for 14 days — land here, ready to reopen anytime.</p>
        </div>
      ) : (
        <div className="home__grid">{completed.map((item) => renderCard(item, true))}</div>
      )}
    </div>
  )
}
