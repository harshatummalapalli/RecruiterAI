import { Home as HomeIcon, Plus, Send as SendIcon, Settings as SettingsIcon } from 'lucide-react'
import { BrandMark } from './SearchSidebar'
import { AccountControl } from './AccountControl'
import { displayTitle, roleStatus } from '../models/roleLifecycle'
import { sidebarSubtitle } from '../models/roleWorkspace'
import type { SearchListItem } from '../types'
import './GlobalShell.css'

export type GlobalDestination = 'home' | 'settings' | 'outreach' | 'role'

/** The single persistent rail — the only sidebar in the product. Brand, the two
 * global destinations (Home / Settings), New search, a short "recents" list of
 * the most recent ACTIVE roles for one-click return, and the account footer.
 * There is no second column: the workspace renders directly in its body. */
export function GlobalShell({
  active,
  onHome,
  onSettings,
  onOutreach,
  recruiterName,
  onSignOut,
  recents,
  activeId,
  newActive,
  onNew,
  onOpenRole,
  children,
}: {
  active: GlobalDestination
  onHome: () => void
  onSettings: () => void
  onOutreach: () => void
  recruiterName: string
  onSignOut: () => void
  recents: SearchListItem[]
  activeId: string | null
  newActive: boolean
  onNew: () => void
  onOpenRole: (item: Pick<SearchListItem, 'kind' | 'id'>) => void
  children: React.ReactNode
}) {
  return (
    <div className="global-shell">
      <nav className="global-nav" aria-label="RecruiterAI">
        <div className="global-nav__brand">
          <BrandMark size={22} />
          <span className="global-nav__wordmark">RecruiterAI</span>
        </div>

        <button type="button" className={`global-nav__item${active === 'home' ? ' is-active' : ''}`} onClick={onHome} aria-current={active === 'home' ? 'page' : undefined}>
          <HomeIcon size={16} aria-hidden="true" />
          <span>Home</span>
        </button>
        <button type="button" className={`global-nav__item${active === 'outreach' ? ' is-active' : ''}`} onClick={onOutreach} aria-current={active === 'outreach' ? 'page' : undefined}>
          <SendIcon size={16} aria-hidden="true" />
          <span>Outreach</span>
        </button>
        <button type="button" className={`global-nav__item${active === 'settings' ? ' is-active' : ''}`} onClick={onSettings} aria-current={active === 'settings' ? 'page' : undefined}>
          <SettingsIcon size={16} aria-hidden="true" />
          <span>Settings</span>
        </button>

        <button type="button" className={`global-nav__new${newActive ? ' is-active' : ''}`} onClick={onNew}>
          <Plus size={15} aria-hidden="true" />
          <span>New search</span>
        </button>

        {recents.length ? (
          <div className="global-nav__recents">
            <p className="global-nav__label">Recent</p>
            <ul className="global-nav__list">
              {recents.map((item) => {
                const subtitle = sidebarSubtitle(item)
                const selected = item.id === activeId
                const status = roleStatus(item)
                return (
                  <li key={`${item.kind}:${item.id}`}>
                    <button
                      type="button"
                      className={`global-nav__role${selected ? ' is-active' : ''}`}
                      aria-current={selected ? 'page' : undefined}
                      onClick={() => onOpenRole({ kind: item.kind, id: item.id })}
                    >
                      <span className="global-nav__role-top">
                        <span className="global-nav__role-title">{displayTitle(item.title)}</span>
                        {status === 'paused' ? <span className="global-nav__role-dot is-paused" aria-hidden="true" /> : status === 'searching' ? <span className="global-nav__role-dot is-live" aria-hidden="true" /> : null}
                      </span>
                      {subtitle ? <span className="global-nav__role-sub">{subtitle}</span> : null}
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
        ) : null}

        <div className="global-nav__spacer" />
        <AccountControl recruiterName={recruiterName} onSignOut={onSignOut} />
      </nav>
      <div className="global-shell__body">{children}</div>
    </div>
  )
}
