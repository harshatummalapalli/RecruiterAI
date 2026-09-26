// Local-only preview of the Release 4 intake experience. Not part of the app or the production build (vite builds
// index.html only). Fixtures come from `python -m backend.experiments.intake_preview`: the real intake code run on
// canned model output, so every state here is exactly what the API returns. No login, backend or network needed.
import { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './screens/RecruiterWorkspaceScreen.css'
import { LivingBrief } from './screens/LivingBrief'
import { RecruiterWorkspaceScreen } from './screens/RecruiterWorkspaceScreen'
import { createEmptySearchBrief, searchIntentToBrief, type SearchBrief } from './models/searchBrief'
import { formatBoundaryLocation } from './models/livingBrief'
import type { IntakeResult } from './models/intake'
import type { SearchBoundary } from './models/searchBoundary'
import type { SearchIntent } from './types'

type Fixture = {
  name: string
  next: string | null
  session_id: string
  result: IntakeResult
  boundary: SearchBoundary
  intent: SearchIntent | null
}

const INPUT = 'Input step (title, description, boundary)'

function Preview() {
  const [fixtures, setFixtures] = useState<Fixture[]>([])
  const [error, setError] = useState<string | null>(null)
  const [current, setCurrent] = useState<string>(() => new URLSearchParams(window.location.search).get('state') ?? '')
  const [message, setMessage] = useState<string | null>(null)
  const [brief, setBrief] = useState<SearchBrief>(createEmptySearchBrief)

  useEffect(() => {
    const loaders = import.meta.glob('./preview-data/intake-*.json')
    const paths = Object.keys(loaders).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
    if (!paths.length) {
      setError('No preview data yet. Run: python -m backend.experiments.intake_preview')
      return
    }
    Promise.all(paths.map((path) => loaders[path]().then((module) => (module as { default: Fixture }).default)))
      .then((loaded) => {
        setFixtures(loaded)
        setCurrent((existing) => existing || loaded[0].name)
      })
      .catch(() => setError('Could not read the preview data. Re-run the intake_preview command.'))
  }, [])

  const fixture = useMemo(() => fixtures.find((entry) => entry.name === current) ?? null, [fixtures, current])

  useEffect(() => {
    setMessage(null)
    setBrief(fixture?.intent ? searchIntentToBrief(fixture.intent) : createEmptySearchBrief())
  }, [fixture])

  const showInput = current === INPUT

  return (
    <main className="workspace" style={{ minHeight: '100vh' }}>
      <div className="workspace__content">
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 16 }}>
          <strong style={{ marginRight: 8 }}>Local preview</strong>
          <button type="button" className={`brief-segmented__option${showInput ? ' is-active' : ''}`} onClick={() => setCurrent(INPUT)}>
            {INPUT}
          </button>
          {fixtures.map((entry) => (
            <button key={entry.name} type="button" className={`brief-segmented__option${current === entry.name ? ' is-active' : ''}`} onClick={() => setCurrent(entry.name)}>
              {entry.name}
            </button>
          ))}
        </div>
        {error ? <p>{error}</p> : null}
        {message ? <p role="status" className="workspace__identity">{message}</p> : null}

        {showInput ? <RecruiterWorkspaceScreen /> : null}

        {!showInput && fixture ? (
          <div className="workspace__brief">
            <div className="workspace__inputs-line">
              <span>
                <strong>{fixture.result.role_understanding.posted_title || 'Untitled role'}</strong> · {fixture.boundary.hiring_company} · {formatBoundaryLocation(fixture.boundary)}
              </span>
              <button type="button" className="workspace__link" onClick={() => setCurrent(INPUT)}>
                Edit description
              </button>
            </div>
            <LivingBrief
              key={fixture.name}
              result={fixture.result}
              boundary={fixture.boundary}
              brief={brief}
              onChangeBrief={(_path, updater) => setBrief((existing) => updater(existing))}
              onAnswer={(_issue, _value, label) => {
                // In the product this is one small call to the server. Here the saved result of that answer is shown.
                const next = fixtures.find((entry) => entry.name === fixture.next)
                if (next) setCurrent(next.name)
                else setMessage(`You chose “${label}”. No saved result exists for this answer in the preview.`)
              }}
              isAnswering={false}
              onApplyBoundary={async () => {
                setMessage('Boundary applied. In the product the server validates it and re-applies it to the reading it already has, with no model call.')
              }}
              onSearch={() => setMessage('Search: the server would now store this confirmed brief as a snapshot and search from it.')}
              isSearching={false}
            />
          </div>
        ) : null}
      </div>
    </main>
  )
}

createRoot(document.getElementById('root')!).render(<Preview />)
