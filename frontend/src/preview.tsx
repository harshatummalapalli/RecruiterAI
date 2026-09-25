// Local-only preview of the candidate record. Not part of the app or the production build (vite builds index.html
// only). Data comes from `python -m backend.experiments.record_preview <saved search>`; no login or backend needed.
import { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './screens/RecruiterWorkspaceScreen.css'
import { CandidateRecord, type RecordDecision } from './components/CandidateRecord'
import { buildDiscoveryCandidates } from './models/discovery'
import type { SearchResponse } from './types'

function Preview() {
  const [response, setResponse] = useState<SearchResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState(0)
  const [decisions, setDecisions] = useState<Record<string, RecordDecision>>({})

  useEffect(() => {
    // Loaded with a glob so the page still works (and the build still passes) when no data file exists yet.
    const loaders = import.meta.glob('./preview-data/response.json')
    const load = loaders['./preview-data/response.json']
    if (!load) {
      setError('No preview data yet. Run: python -m backend.experiments.record_preview <saved search .json>')
      return
    }
    load()
      .then((module) => setResponse((module as { default: SearchResponse }).default))
      .catch(() => setError('Could not read the preview data. Re-run the record_preview command.'))
  }, [])

  const candidates = useMemo(() => (response ? buildDiscoveryCandidates(response) : []), [response])
  const current = candidates[selected]

  return (
    <div className="workspace" style={{ display: 'flex', gap: 24, padding: 24, alignItems: 'flex-start', minHeight: '100vh' }}>
      <nav style={{ flex: '0 0 300px', maxHeight: '95vh', overflow: 'auto' }} aria-label="Candidates">
        <p style={{ margin: '0 0 8px', fontWeight: 600 }}>Local preview · {candidates.length} candidates</p>
        {error ? <p>{error}</p> : null}
        {candidates.map((candidate, index) => (
          <button
            key={candidate.id}
            type="button"
            onClick={() => setSelected(index)}
            style={{
              display: 'block',
              width: '100%',
              textAlign: 'left',
              padding: '8px 10px',
              marginBottom: 4,
              borderRadius: 8,
              cursor: 'pointer',
              border: '1px solid var(--color-border)',
              background: index === selected ? 'var(--color-preview-bg)' : 'var(--color-surface)',
            }}
          >
            <strong>
              {index + 1}. {candidate.name}
            </strong>
            <br />
            <span style={{ fontSize: 12.5 }}>{candidate.title}</span>
          </button>
        ))}
      </nav>
      {current ? (
        <CandidateRecord
          key={current.id}
          candidate={current}
          position={selected + 1}
          total={candidates.length}
          decision={decisions[current.id]}
          onDecision={(decision) => setDecisions((existing) => ({ ...existing, [current.id]: decision }))}
          onClose={() => undefined}
        />
      ) : null}
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<Preview />)
