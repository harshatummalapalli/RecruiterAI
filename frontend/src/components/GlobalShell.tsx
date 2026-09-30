import { Home as HomeIcon, Settings as SettingsIcon } from 'lucide-react'
import { BrandMark } from './SearchSidebar'
import { AccountControl } from './AccountControl'
import './GlobalShell.css'

export type GlobalDestination = 'home' | 'settings' | 'role'

/** The persistent, always-present outer shell: "where am I in the product."
 * Distinct from role navigation (SearchSidebar in role-nav mode, see its
 * own docstring) — that answers "where am I inside this hiring mandate."
 * Never collapses, never competes with the role title for attention: a
 * narrow, restrained rail, infrastructure rather than a destination. */
export function GlobalShell({
  active,
  onHome,
  onSettings,
  recruiterName,
  onSignOut,
  children,
}: {
  active: GlobalDestination
  onHome: () => void
  onSettings: () => void
  recruiterName: string
  onSignOut: () => void
  children: React.ReactNode
}) {
  return (
    <div className="global-shell">
      <nav className="global-nav" aria-label="RecruiterAI">
        <div className="global-nav__brand" aria-hidden="true">
          <BrandMark size={22} />
        </div>
        <button type="button" className={`global-nav__item${active === 'home' ? ' is-active' : ''}`} onClick={onHome} aria-current={active === 'home' ? 'page' : undefined}>
          <HomeIcon size={16} aria-hidden="true" />
          <span>Home</span>
        </button>
        <button type="button" className={`global-nav__item${active === 'settings' ? ' is-active' : ''}`} onClick={onSettings} aria-current={active === 'settings' ? 'page' : undefined}>
          <SettingsIcon size={16} aria-hidden="true" />
          <span>Settings</span>
        </button>
        <div className="global-nav__spacer" />
        <AccountControl recruiterName={recruiterName} onSignOut={onSignOut} />
      </nav>
      <div className="global-shell__body">{children}</div>
    </div>
  )
}
