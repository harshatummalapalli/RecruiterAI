import { Plus } from 'lucide-react'
import type { SearchListItem } from '../types'
import { isActive, sidebarBadge, sidebarSubtitle, type ActiveSearch } from '../models/roleWorkspace'
import './SearchSidebar.css'

/** The mark: a restrained teal tile. Purely the product's own identity, no external asset. */
export function BrandMark({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="8" fill="#0f766e" />
      <path d="M9 22V10h7a4 4 0 0 1 0 8h-7m6 0 5 4" fill="none" stroke="#f7f5f0" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** Every role and every unsearched brief, newest activity first. Choosing one restores it exactly as it was left. */
export function SearchSidebar({
  items,
  active,
  onSelect,
  onNew,
  isNewActive,
}: {
  items: SearchListItem[]
  active: ActiveSearch | null
  onSelect: (item: SearchListItem) => void
  onNew: () => void
  isNewActive: boolean
}) {
  return (
    <nav className="app-sidebar" aria-label="Searches">
      <div className="app-sidebar__brand">
        <BrandMark />
        <span className="app-sidebar__name">RECRUITERAI</span>
      </div>

      <button type="button" className={`app-sidebar__new${isNewActive ? ' is-active' : ''}`} onClick={onNew}>
        <Plus size={15} aria-hidden="true" />
        New search
      </button>

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
    </nav>
  )
}
