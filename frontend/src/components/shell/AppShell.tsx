import { Outlet } from 'react-router-dom'
import { RightSidebarContainer } from './RightSidebarContainer'
import { Sidebar } from './Sidebar'
import { TopSearchBar } from './TopSearchBar'

type AppShellProps = {
  children?: React.ReactNode
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="app-shell__main">
        <TopSearchBar />
        <main className="app-shell__content">
          {children ?? <Outlet />}
        </main>
      </div>
      <RightSidebarContainer />
    </div>
  )
}
