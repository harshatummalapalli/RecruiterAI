import { ActivityFeed } from './ActivityFeed'
import { AssistantPanel } from './AssistantPanel'

export function RightSidebarContainer() {
  return (
    <aside className="app-right-rail" aria-label="Right sidebar">
      <AssistantPanel />
      <ActivityFeed />
    </aside>
  )
}
