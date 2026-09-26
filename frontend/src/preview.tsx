// Local-only preview of the candidate workspace (Release 3) and record (Release 2). Not part of the app or the
// production build (vite builds index.html only). It renders the REAL review screen on saved data: run
// `python -m backend.experiments.record_preview <saved search>` first. No login, backend or network needed.
import { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './screens/RecruiterWorkspaceScreen.css'
import { CandidateReviewScreen } from './screens/CandidateReviewScreen'
import { createEmptySearchBrief } from './models/searchBrief'
import type { SearchResponse } from './types'

type Mode = 'reading' | 'ready' | 'grouped'

const MODES: Array<{ value: Mode; label: string }> = [
  { value: 'reading', label: 'While reading (12 of 25)' },
  { value: 'ready', label: 'All read, not grouped yet' },
  { value: 'grouped', label: 'Grouped' },
]

const READ_SO_FAR = 12

function shapeForMode(base: SearchResponse, mode: Mode): SearchResponse {
  if (mode === 'grouped') return { ...base, workspace_arranged: true }
  if (mode === 'ready') return { ...base, workspace_arranged: false }
  // Mid-read: only the first few have finished; the rest are still being prepared, and the search is still running.
  const states: Record<string, 'surfaced' | 'building_context' | 'review_ready'> = {}
  base.candidates.forEach((candidate, index) => {
    const id = candidate.candidate_id ?? `${index}`
    states[id] = index < READ_SO_FAR ? 'review_ready' : index < READ_SO_FAR + 3 ? 'building_context' : 'surfaced'
  })
  return {
    ...base,
    status: 'running',
    workspace_arranged: false,
    candidate_states: states,
    progress: { admitted: base.candidates.length, surfaced: base.candidates.length - READ_SO_FAR - 3, building_context: 3, review_ready: READ_SO_FAR },
  }
}

function Preview() {
  const [base, setBase] = useState<SearchResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<Mode>(() => {
    const requested = new URLSearchParams(window.location.search).get('mode')
    return MODES.some((option) => option.value === requested) ? (requested as Mode) : 'grouped'
  })
  const brief = useMemo(() => createEmptySearchBrief(), [])

  useEffect(() => {
    // Loaded with a glob so the page still works (and the build still passes) when no data file exists yet.
    const loaders = import.meta.glob('./preview-data/response.json')
    const load = loaders['./preview-data/response.json']
    if (!load) {
      setError('No preview data yet. Run: python -m backend.experiments.record_preview <saved search .json>')
      return
    }
    load()
      .then((module) => setBase((module as { default: SearchResponse }).default))
      .catch(() => setError('Could not read the preview data. Re-run the record_preview command.'))
  }, [])

  const response = useMemo(() => (base ? shapeForMode(base, mode) : null), [base, mode])

  return (
    <main className="workspace" style={{ minHeight: '100vh' }}>
      <div className="workspace__content">
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 16 }}>
          <strong style={{ marginRight: 8 }}>Local preview</strong>
          {MODES.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`brief-segmented__option${mode === option.value ? ' is-active' : ''}`}
              onClick={() => setMode(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
        {error ? <p>{error}</p> : null}
        {response ? (
          <CandidateReviewScreen
            key={mode}
            brief={brief}
            onChangeBrief={() => undefined}
            searchResponse={response}
            searchState={mode === 'reading' ? 'searching' : 'done'}
            onRunSearch={() => undefined}
            searchId={null}
            searchGeneration={1}
          />
        ) : null}
      </div>
    </main>
  )
}

createRoot(document.getElementById('root')!).render(<Preview />)
