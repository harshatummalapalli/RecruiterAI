import { BriefcaseBusiness, Home, MessageCircleMore, Settings, Users, Waypoints } from 'lucide-react'
import { NavLink } from 'react-router-dom'

const navItems = [
  { to: '/home', label: 'Home', icon: Home },
  { to: '/role-review', label: 'Roles', icon: BriefcaseBusiness },
  { to: '/candidate-discovery', label: 'Candidates', icon: Users },
  { to: '/candidate-workspace', label: 'Pipeline', icon: Waypoints },
  { to: '/resume-inbox', label: 'Messages', icon: MessageCircleMore },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export function Sidebar() {
  return (
    <aside className="app-sidebar" aria-label="Primary navigation">
      <div className="app-sidebar__logo" aria-label="RecruiterAI logo">R</div>
      <nav className="app-sidebar__nav">
        {navItems.map((item) => {
          const Icon = item.icon
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `app-sidebar__link ${isActive ? 'is-active' : ''}`}
            >
              <Icon size={18} />
              <span>{item.label}</span>
            </NavLink>
          )
        })}
      </nav>
      <div className="app-sidebar__profile">
        <div className="app-sidebar__avatar">HK</div>
        <div>
          <strong>Harsha K.</strong>
          <p>Talent Partner</p>
        </div>
      </div>
    </aside>
  )
}
