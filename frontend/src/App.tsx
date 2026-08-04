import { useRecruiterWorkbench } from './hooks/useRecruiterWorkbench'
import { Button } from './components/Button'
import { CandidateComparisonPanel } from './components/CandidateComparisonPanel'
import { CandidateDetailDrawer } from './components/CandidateDetailDrawer'
import { CandidateTable } from './components/CandidateTable'
import { Panel } from './components/Panel'
import { ProgressSummary } from './components/ProgressSummary'
import { SearchBriefEditor } from './components/SearchBriefEditor'
import { SearchHistoryPanel } from './components/SearchHistoryPanel'
import { SearchInsightsPanel } from './components/SearchInsightsPanel'
import { StatusBanner } from './components/StatusBanner'
import { TextAreaField } from './components/TextField'
import { WorkflowHeader } from './components/WorkflowHeader'
import { getCandidateKey } from './services/recruiterWorkflow'
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
    analytics,
    selectedCandidateState,
    comparisonCandidates,
    history,
    demoMode,
    applyCandidateAction,
    addResume,
    addNote,
    editNote,
    deleteNote,
    togglePin,
    viewCandidate,
    reopenHistoryEntry,
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
            {demoMode ? <span className="pill pill--accent">Demo Mode</span> : null}
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
                <Button tone="secondary" onClick={runSearch} disabled={busyState === 'searching'}>{busyState === 'searching' ? 'Searching…' : 'Search candidates'}</Button>
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
                  {searchSummary.demo ? <p className="muted">No sourcing providers are configured. Showing representative candidates.</p> : null}
                </div>
                <div className="search-summary-card__metrics">
                  <span>Average: {searchSummary.averageMatch}</span>
                  <span>Highest: {searchSummary.highestMatch}</span>
                  <span>Top locations: {searchSummary.topLocations.join(', ')}</span>
                  <span>Top companies: {searchSummary.topCompanies.join(', ')}</span>
                  <span>Duration: {searchSummary.searchDuration}</span>
                  <span>Confidence: {searchSummary.searchConfidence}</span>
                </div>
              </div>
            ) : null}
            <CandidateTable candidates={searchResponse?.candidates ?? []} selectedKey={selectedCandidateKey} onSelect={(key) => { handleCandidateSelect(key); const candidate = searchResponse?.candidates.find((item) => getCandidateKey(item) === key); if (candidate) { viewCandidate(candidate) } }} isLoading={busyState === 'searching'} candidateCount={searchResponse?.candidates.length ?? 0} />
            <SearchInsightsPanel summary={searchSummary} analytics={analytics} />
            <CandidateComparisonPanel candidates={comparisonCandidates} />
            <SearchHistoryPanel history={history} onReopen={reopenHistoryEntry} />
            <CandidateDetailDrawer candidate={selectedCandidate} selectedCandidateState={selectedCandidateState} onAction={(action, payload) => {
              if (!selectedCandidate) {
                return
              }
              if (action === 'note') {
                addNote(selectedCandidate, payload ?? '')
                return
              }
              applyCandidateAction(selectedCandidate, action, payload)
            }} onUploadResume={(candidate, fileName) => addResume(candidate, fileName)} onEditNote={(candidate, noteId, noteText, pinned) => editNote(candidate, noteId, noteText, pinned)} onDeleteNote={(candidate, noteId) => deleteNote(candidate, noteId)} onTogglePin={(candidate, noteId) => togglePin(candidate, noteId)} />
          </div>
        </Panel>
      </main>
    </div>
  )
}

export default App
