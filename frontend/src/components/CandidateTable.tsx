import type { Candidate } from '../types'
import { getCandidateKey } from '../services/recruiterWorkflow'

type CandidateTableProps = {
  candidates: Candidate[]
  selectedKey: string | null
  onSelect: (key: string) => void
}

export function CandidateTable({ candidates, selectedKey, onSelect }: CandidateTableProps) {
  if (!candidates.length) {
    return (
      <div className="empty-state">
        <h3>No candidates matched this brief.</h3>
        <p className="muted">Try widening the location, skills, or ranking hints and search again.</p>
      </div>
    )
  }

  return (
    <div className="candidate-table" role="table" aria-label="Candidate results">
      <div className="candidate-table__header" role="row">
        <span role="columnheader">Score</span>
        <span role="columnheader">Name</span>
        <span role="columnheader">Title</span>
        <span role="columnheader">Company</span>
        <span role="columnheader">Location</span>
      </div>
      {candidates.map((candidate) => {
        const key = getCandidateKey(candidate)
        const isSelected = selectedKey === key
        return (
          <button key={key} className={`candidate-row ${isSelected ? 'is-selected' : ''}`} onClick={() => onSelect(key)}>
            <span>{candidate.final_score ?? candidate.provider_score ?? '—'}</span>
            <span>{candidate.name ?? 'Candidate'}</span>
            <span>{candidate.title ?? '—'}</span>
            <span>{candidate.company ?? '—'}</span>
            <span>{candidate.location ?? '—'}</span>
          </button>
        )
      })}
    </div>
  )
}
