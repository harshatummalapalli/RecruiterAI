import { ChevronLeft, Link2, Link2Off } from 'lucide-react'
import type { SearchListItem } from '../types'
import { isActive, sidebarBadge, sidebarSubtitle, type ActiveSearch } from '../models/roleWorkspace'
import { AppearanceControl } from './AppearanceControl'
import './SearchSidebar.css'

/** The mark: a restrained green tile. Purely the product's own identity, no external asset. */
export function BrandMark({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="8" fill="#2f7d5b" />
      <path d="M9 22V10h7a4 4 0 0 1 0 8h-7m6 0 5 4" fill="none" stroke="#f5f5f7" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** The role rail: every search and every unsearched brief, newest activity first. Choosing one restores it
 * exactly as it was left. This is NOT the application's home navigation (see HomeScreen) — it's the working
 * context while inside the JD/Brief/Review flow, always reachable from Home via "‹ Your searches" at the top.
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
  onSignOut,
  onGoHome,
}: {
  items: SearchListItem[]
  active: ActiveSearch | null
  onSelect: (item: SearchListItem) => void
  onNew: () => void
  isNewActive: boolean
  collapsed: boolean
  glued: boolean
  onToggleGlue: () => void
  onSignOut: () => void
  onGoHome: () => void
}) {
  if (collapsed) return null

  return (
    <nav className="app-sidebar" aria-label="Searches">
      <button type="button" className="app-sidebar__back" onClick={onGoHome}>
        <ChevronLeft size={14} aria-hidden="true" />
        Your searches
      </button>

      <div className="app-sidebar__brand">
        <BrandMark />
        <span className="app-sidebar__name">RECRUITERAI</span>
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

      <button type="button" className={`app-sidebar__new${isNewActive ? ' is-active' : ''}`} onClick={onNew}>
        New search
      </button>

      {/* Only this middle region scrolls — the header above and the account
         footer below stay fixed, so Sign out is always reachable without
         scrolling through however many searches exist. */}
      <div className="app-sidebar__scroll">
        <p className="app-sidebar__label">SEARCHES</p>
        {items.length === 0 ? <p className="app-sidebar__empty">Your searches will appear here.</p> : null}
        <ul className="app-sidebar__list">
          {items.map((item) => {
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
          })}
        </ul>
      </div>

      <div className="app-sidebar__footer">
        <AppearanceControl />
        <button type="button" className="app-sidebar__signout" onClick={onSignOut}>
          Sign out
        </button>
      </div>
    </nav>
  )
}
