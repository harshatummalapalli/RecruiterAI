import { Link2, Link2Off } from 'lucide-react'
import type { SearchListItem } from '../types'
import { isActive, sidebarBadge, sidebarSubtitle, type ActiveSearch } from '../models/roleWorkspace'
import './SearchSidebar.css'

/** The mark: a restrained green tile. Purely the product's own identity, no external asset. Used by the global
 * shell (GlobalShell) as the one persistent brand element — not repeated here anymore (see below). */
export function BrandMark({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="8" fill="#2f7d5b" />
      <path d="M9 22V10h7a4 4 0 0 1 0 8h-7m6 0 5 4" fill="none" stroke="#f5f5f7" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** The search rail. Answers "which of my searches am I in" — distinct from the global shell (GlobalShell),
 * which owns brand/Home/Settings/account. One flat cross-search list, grouped into Active and Drafts (the
 * mockup's rail), the one place to jump straight into another search without going through Home first.
 *
 * Collapses to 0 width (unmounted, not a narrow icon rail) when a candidate record opens, unless "Glue" is on;
 * when collapsed, the workspace header's hamburger reopens it (equivalent to turning Glue on). */
export function SearchSidebar({
  items,
  active,
  onSelect,
  onNew,
  isNewActive,
  collapsed,
  glued,
  onToggleGlue,
}: {
  items: SearchListItem[]
  active: ActiveSearch | null
  onSelect: (item: SearchListItem) => void
  onNew: () => void
  isNewActive: boolean
  collapsed: boolean
  glued: boolean
  onToggleGlue: () => void
}) {
  if (collapsed) return null

  const searches = items.filter((item) => item.kind === 'search')
  const drafts = items.filter((item) => item.kind === 'draft')

  const renderItem = (item: SearchListItem) => {
    const badge = sidebarBadge(item)
    const subtitle = sidebarSubtitle(item)
    const selected = isActive(item, active)
    return (
      <li key={`${item.kind}:${item.id}`}>
        <button type="button" className={`app-sidebar__item${selected ? ' is-active' : ''}`} aria-current={selected ? 'page' : undefined} onClick={() => onSelect(item)}>
          <span className="app-sidebar__title">{item.title}</span>
          {subtitle ? <span className="app-sidebar__subtitle">{subtitle}</span> : null}
          {badge ? <span className={`app-sidebar__badge is-${badge.tone}`}>{badge.text}</span> : null}
        </button>
      </li>
    )
  }

  return (
    <nav className="app-sidebar" aria-label="Searches">
      <div className="app-sidebar__top">
        <button type="button" className={`app-sidebar__new${isNewActive ? ' is-active' : ''}`} onClick={onNew}>
          New search
        </button>
        <button
          type="button"
          className={`app-sidebar__glue${glued ? ' is-active' : ''}`}
          onClick={onToggleGlue}
          aria-pressed={glued}
          title={glued ? 'Unglue sidebar' : 'Glue sidebar open'}
        >
          {glued ? <Link2 size={14} aria-hidden="true" /> : <Link2Off size={14} aria-hidden="true" />}
        </button>
      </div>

      <div className="app-sidebar__scroll">
        {items.length === 0 ? <p className="app-sidebar__empty">Your searches will appear here.</p> : null}
        {searches.length ? (
          <>
            <p className="app-sidebar__label">Active</p>
            <ul className="app-sidebar__list">{searches.map(renderItem)}</ul>
          </>
        ) : null}
        {drafts.length ? (
          <>
            <p className="app-sidebar__label">Drafts</p>
            <ul className="app-sidebar__list">{drafts.map(renderItem)}</ul>
          </>
        ) : null}
      </div>
    </nav>
  )
}
