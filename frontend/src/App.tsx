import { useRecruiterWorkbench } from './hooks/useRecruiterWorkbench'
import { Button } from './components/Button'
import { CandidateDetailDrawer } from './components/CandidateDetailDrawer'
import { CandidateTable } from './components/CandidateTable'
import { Panel } from './components/Panel'
import { ProgressSummary } from './components/ProgressSummary'
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
    providerAvailable,
    searchSummary,
    selectedCandidateState,
    applyCandidateAction,
    addResume,
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
        title="Recruiter workbench"
        description="Shape the search brief, review matching talent, and prepare the next recruiting step without leaving the workflow."
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
                <Button tone="secondary" onClick={runSearch} disabled={busyState === 'searching' || !providerAvailable}>{busyState === 'searching' ? 'Searching…' : 'Search candidates'}</Button>
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
              <ProgressSummary busyState={busyState} />
              {!providerAvailable ? <StatusBanner tone="info" message="Sourcing has not yet been configured. Parsing and editing the search brief continue to work normally." /> : null}
              {notice ? <StatusBanner tone={notice.type} message={notice.message} /> : null}
            </div>
          </Panel>

          <Panel
            title="Search brief"
            description="Adjust hire criteria quickly."
          >
            <SearchBriefEditor intent={intent} onChange={updateIntent} validationErrors={validationErrors} />
          </Panel>
        </div>

        <Panel
          title="Candidate workspace"
          description="Review ranked candidates, upload resumes, and prepare the next recruiting step."
          className="workspace-grid__right"
        >
          <div className="stack">
            {searchSummary ? (
              <div className="search-summary-card">
                <div>
                  <p className="eyebrow">Search summary</p>
                  <h3>{searchSummary.candidateCount} candidates found</h3>
                </div>
                <div className="search-summary-card__metrics">
                  <span>Duration: {searchSummary.searchDuration}</span>
                  <span>Confidence: {searchSummary.searchConfidence}</span>
                  <span>Updated: {searchSummary.lastUpdated}</span>
                </div>
              </div>
            ) : null}
            <CandidateTable candidates={searchResponse?.candidates ?? []} selectedKey={selectedCandidateKey} onSelect={handleCandidateSelect} isLoading={busyState === 'searching'} candidateCount={searchResponse?.candidates.length ?? 0} />
            <CandidateDetailDrawer candidate={selectedCandidate} selectedCandidateState={selectedCandidateState} onAction={(action, payload) => selectedCandidate ? applyCandidateAction(selectedCandidate, action, payload) : undefined} onUploadResume={(candidate, fileName) => addResume(candidate, fileName)} />
          </div>
        </Panel>
      </main>
    </div>
  )
}

export default App
