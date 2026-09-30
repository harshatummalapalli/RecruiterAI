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

/** "Where am I inside this hiring mandate" — role title, status, and the two role-level destinations
 * (Understanding / Candidates). Shortlisted/Maybe/Rejected stay exactly where they already correctly live: the
 * Candidates screen's own filter pills, not duplicated here. No "Archive role" — the backend has no
 * archived-role concept (see HomeScreen's own Archived-tab comment), so it isn't offered as if it were real. */
export type RoleNavInfo = {
  title: string
  statusLabel: string
  company: string
  section: 'understanding' | 'candidates'
  /** False until a search has actually run for this role — nothing to
   * show yet, so the destination is visible (the structure is always
   * clear) but not yet clickable. */
  candidatesEnabled: boolean
  onSelectUnderstanding: () => void
  onSelectCandidates: () => void
}

/** The role rail. Answers "where am I inside this hiring mandate" — distinct from the global shell (GlobalShell),
 * which answers "where am I in the product" and owns brand/Home/Settings/account; none of that is repeated here.
 *
 * Two content modes:
 *   - roleNav given: a specific role is open — shows its title/status and the Understanding/Candidates switch.
 *   - roleNav absent: no role is open yet (composing a new search) — shows the flat cross-role search list, the
 *     one place you can still jump directly into a different existing role without going through Home first.
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
  roleNav,
}: {
  items: SearchListItem[]
  active: ActiveSearch | null
  onSelect: (item: SearchListItem) => void
  onNew: () => void
  isNewActive: boolean
  collapsed: boolean
  glued: boolean
  onToggleGlue: () => void
  roleNav?: RoleNavInfo
}) {
  if (collapsed) return null

  return (
    <nav className="app-sidebar" aria-label={roleNav ? `${roleNav.title} navigation` : 'Searches'}>
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

      {roleNav ? (
        <div className="app-sidebar__role">
          <p className="app-sidebar__role-title">{roleNav.title}</p>
          <p className="app-sidebar__role-status">
            <span className={`app-sidebar__role-dot${roleNav.statusLabel === 'Searching' ? ' is-active' : ''}`} aria-hidden="true" />
            {[roleNav.statusLabel, roleNav.company].filter(Boolean).join(' · ')}
          </p>
          <div className="app-sidebar__role-nav">
            <button
              type="button"
              className={`app-sidebar__role-nav-item${roleNav.section === 'understanding' ? ' is-active' : ''}`}
              aria-current={roleNav.section === 'understanding' ? 'page' : undefined}
              onClick={roleNav.onSelectUnderstanding}
            >
              Understanding
            </button>
            <button
              type="button"
              className={`app-sidebar__role-nav-item${roleNav.section === 'candidates' ? ' is-active' : ''}`}
              aria-current={roleNav.section === 'candidates' ? 'page' : undefined}
              disabled={!roleNav.candidatesEnabled}
              title={roleNav.candidatesEnabled ? undefined : 'Run a search first to see candidates'}
              onClick={roleNav.onSelectCandidates}
            >
              Candidates
            </button>
          </div>
        </div>
      ) : (
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
      )}
    </nav>
  )
}
