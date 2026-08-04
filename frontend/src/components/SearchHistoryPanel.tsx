import type { SearchHistoryEntry } from '../types'

type SearchHistoryPanelProps = {
  history: SearchHistoryEntry[]
  onReopen: (entry: SearchHistoryEntry) => void
}

export function SearchHistoryPanel({ history, onReopen }: SearchHistoryPanelProps) {
  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Search history</p>
          <h3>Reopen prior searches</h3>
        </div>
      </div>
      <div className="history-list">
        {history.length ? history.map((entry) => (
          <button key={entry.id} className="history-item" type="button" onClick={() => onReopen(entry)}>
            <div>
              <strong>{entry.brief || entry.jd}</strong>
              <p className="muted">{entry.createdAt} • {entry.candidateCount} candidates</p>
            </div>
            <span className="button secondary">Open</span>
          </button>
        )) : <p className="muted">Previous searches will appear here for quick reopening.</p>}
      </div>
    </div>
  )
}
