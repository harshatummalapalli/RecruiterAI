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

function campaignTimeLeft(endsAt: string | null | undefined, now: number): string | null {
  if (!endsAt) return null
  const remaining = new Date(endsAt).getTime() - now
  if (!Number.isFinite(remaining) || remaining <= 0) return 'Campaign window ended'
  const hours = Math.ceil(remaining / 3_600_000)
  if (hours < 24) return `${hours}h left in campaign`
  const days = Math.floor(hours / 24)
  const extraHours = hours % 24
  return extraHours ? `${days}d ${extraHours}h left in campaign` : `${days}d left in campaign`
}

type MenuAction = { label: string; onClick: () => void; confirm?: string }

function RowMenu({ actions, onClose }: { actions: MenuAction[]; onClose: () => void }) {
  const ref = useRef<HTMLDivElement | null>(null)
  // A destructive-ish action (Close) arms on the first click and only fires on the
  // second, so it can never move a role to Completed on a single mis-click.
  const [armed, setArmed] = useState<string | null>(null)
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
      {actions.map((action) => {
        const isArmed = armed === action.label
        return (
          <button
            key={action.label}
            type="button"
            role="menuitem"
            className={`home-row-menu__item${isArmed ? ' home-row-menu__item--armed' : ''}`}
            onClick={() => {
              if (action.confirm && !isArmed) {
                setArmed(action.label)
                return
              }
              action.onClick()
              onClose()
            }}
          >
            {isArmed ? action.confirm : action.label}
          </button>
        )
      })}
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
  now,
}: {
  item: SearchListItem
  completed: boolean
  actions: CardActions
  openMenu: boolean
  setOpenMenu: (open: boolean) => void
  now: number
}) {
  const status = roleStatus(item)
  const company = sidebarSubtitle(item) || (item.kind === 'draft' ? 'Not yet searched' : 'Company not specified')
  const foot = completed
    ? { text: 'Closed', emphasis: false }
    : status === 'complete'
      ? { text: item.found_count ? `${item.found_count} profiles found` : 'Search complete', emphasis: false }
      : activitySummary(item)

  const menuActions: MenuAction[] = completed
    ? [{ label: 'View', onClick: () => actions.onOpen(item) }, { label: 'Reopen (move to Active)', onClick: () => actions.onReopen(item.id) }]
    : item.kind === 'draft'
      ? [{ label: 'Continue', onClick: () => actions.onOpen(item) }, { label: 'Close', onClick: () => actions.onClose(item.id), confirm: 'Confirm close' }]
      : status === 'paused'
        ? [
            { label: 'Open', onClick: () => actions.onOpen(item) },
            { label: 'Resume', onClick: () => actions.onResume(item.id) },
            { label: 'Close', onClick: () => actions.onClose(item.id), confirm: 'Confirm close' },
          ]
        : [
            { label: 'Open', onClick: () => actions.onOpen(item) },
            { label: 'Pause', onClick: () => actions.onPause(item.id) },
            { label: 'Close', onClick: () => actions.onClose(item.id), confirm: 'Confirm close' },
          ]

  const badgeClass = completed ? 'complete' : status
  const badgeText = completed ? 'Closed' : status === 'searching' ? 'Searching' : status === 'paused' ? 'Paused' : status === 'complete' ? 'Complete' : 'Draft'

  return (
    <div className="home__row" role="button" tabIndex={0} onClick={() => actions.onOpen(item)}>
      <div className="home__rc-top">
        <span className="home__rc-name">{displayTitle(item.title)}</span>
        <span className={`home__status home__status--${badgeClass}`}>
          {!completed && status === 'searching' ? <span className="home__status-dot" aria-hidden="true" /> : null}
          {badgeText}
        </span>
      </div>
      <p className="home__rc-meta">{company}</p>
      <div className="home__rc-stats" aria-label="Candidate progress">
        {item.kind === 'search' ? <span><strong>{item.found_count ?? 0}</strong> found</span> : <span>Not yet searched</span>}
        {item.kind === 'search' && item.to_review_count != null ? <span><strong>{item.to_review_count}</strong> to review</span> : null}
        {(item.shortlisted_count ?? 0) > 0 ? <span><strong>{item.shortlisted_count}</strong> shortlisted</span> : null}
        {(item.rejected_count ?? 0) > 0 ? <span><strong>{item.rejected_count}</strong> rejected</span> : null}
        {(item.maybe_count ?? 0) > 0 ? <span><strong>{item.maybe_count}</strong> maybe</span> : null}
      </div>
      <p className={`home__rc-foot${foot.emphasis ? ' is-green' : ''}`}>
        {!completed && status === 'searching' ? campaignTimeLeft(item.campaign_ends_at, now) || foot.text : foot.text}
        <span className="home__rc-updated">Updated {timeAgo(item.updated_at)}</span>
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
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000)
    return () => window.clearInterval(timer)
  }, [])

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
      now={now}
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
