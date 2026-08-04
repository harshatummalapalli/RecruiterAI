import { useRecruiterWorkbench } from './hooks/useRecruiterWorkbench'
import { Button } from './components/Button'
import { CandidateDetailDrawer } from './components/CandidateDetailDrawer'
import { CandidateTable } from './components/CandidateTable'
import { Panel } from './components/Panel'
import { getCandidateKey } from './services/recruiterWorkflow'
import { SearchBriefEditor } from './components/SearchBriefEditor'
import { StatusBanner } from './components/StatusBanner'
import { TextAreaField } from './components/TextField'
import { WorkflowHeader } from './components/WorkflowHeader'
import './App.css'

function App() {
  const {
    jdText,
    setJdText,
    intent,
    updateIntent,
    busyState,
    notice,
    searchResponse,
    selectedCandidate,
    setSelectedCandidateKey,
    hasPendingParse,
    validationErrors,
    parsedIntentSummary,
    parseIntent,
    runSearch,
    exportResults,
  } = useRecruiterWorkbench()

  const handleCandidateSelect = (key: string) => {
    setSelectedCandidateKey(key)
  }

  const selectedCandidateKey = selectedCandidate ? getCandidateKey(selectedCandidate) : null

  return (
    <div className="app-shell">
      <WorkflowHeader
        title="Refine the search brief before you source candidates."
        description="Paste a job description, review and edit the parsed search brief, then run a CrustData search from the refined brief."
        actions={
          <div className="workflow-pill-row">
            {hasPendingParse ? <span className="pill">Needs refresh</span> : null}
            <span className="pill pill--muted">{parsedIntentSummary}</span>
          </div>
        }
      />

      <main className="workspace-grid">
        <div className="workspace-grid__left">
          <Panel
            title="Job description"
            description="Turn the JD into a recruiter-ready search brief."
            actions={
              <div className="button-stack">
                <Button onClick={parseIntent} disabled={busyState === 'parsing'}>{busyState === 'parsing' ? 'Parsing…' : 'Parse JD'}</Button>
                <Button tone="secondary" onClick={runSearch} disabled={busyState === 'searching'}>{busyState === 'searching' ? 'Searching…' : 'Search Candidates'}</Button>
                <Button tone="secondary" onClick={exportResults} disabled={busyState === 'exporting'}>{busyState === 'exporting' ? 'Exporting…' : 'Export'}</Button>
              </div>
            }
          >
            <div className="stack">
              <TextAreaField
                label="Job description"
                value={jdText}
                onChange={(event) => {
                  setJdText(event.target.value)
                }}
                rows={10}
                placeholder="Paste the job description here…"
              />
              {busyState ? <div className="progress-bar" aria-hidden="true"><span /></div> : null}
              {notice ? <StatusBanner tone={notice.type} message={notice.message} /> : null}
              {busyState ? <p className="muted">Working on your request…</p> : null}
            </div>
          </Panel>

          <Panel
            title="Search brief"
            description="The recruiter remains in control of every decision."
          >
            <SearchBriefEditor intent={intent} onChange={updateIntent} validationErrors={validationErrors} />
          </Panel>
        </div>

        <Panel
          title="Candidate workspace"
          description="Review ranked candidates and keep the workbench focused on sourcing and decision-making."
          className="workspace-grid__right"
        >
          <div className="stack">
            <CandidateTable candidates={searchResponse?.candidates ?? []} selectedKey={selectedCandidateKey} onSelect={handleCandidateSelect} />
            <CandidateDetailDrawer candidate={selectedCandidate} />
          </div>
        </Panel>
      </main>
    </div>
  )
}

export default App
