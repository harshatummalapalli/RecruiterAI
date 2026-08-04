import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/shell/AppShell'
import { CandidateDiscoveryRoute } from './routes/CandidateDiscoveryRoute'
import { CandidateWorkspaceRoute } from './routes/CandidateWorkspaceRoute'
import { EmptyRoutePage } from './routes/EmptyRoutePage'
import { HomeRoute } from './routes/HomeRoute'
import { ResumeInboxRoute } from './routes/ResumeInboxRoute'
import { RoleReviewRoute } from './routes/RoleReviewRoute'
import { SettingsRoute } from './routes/SettingsRoute'

function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Navigate to="/home" replace />} />
        <Route path="/home" element={<HomeRoute />} />
        <Route path="/role-review" element={<RoleReviewRoute />} />
        <Route path="/candidate-discovery" element={<CandidateDiscoveryRoute />} />
        <Route path="/candidate-workspace" element={<CandidateWorkspaceRoute />} />
        <Route path="/resume-inbox" element={<ResumeInboxRoute />} />
        <Route path="/settings" element={<SettingsRoute />} />
        <Route path="*" element={<EmptyRoutePage title="Page not found" />} />
      </Route>
    </Routes>
  )
}

export default App
