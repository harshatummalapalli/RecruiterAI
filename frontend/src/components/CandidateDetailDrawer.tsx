import type { Candidate } from '../types'

type CandidateDetailDrawerProps = {
  candidate: Candidate | null
}

export function CandidateDetailDrawer({ candidate }: CandidateDetailDrawerProps) {
  if (!candidate) {
    return (
      <div className="empty-state">
        <h3>Candidate preview</h3>
        <p className="muted">Select a candidate row to review profile details, enrichment, and the raw provider payload.</p>
      </div>
    )
  }

  return (
    <div className="candidate-details">
      <div className="candidate-details__header">
        <div>
          <h3>{candidate.name ?? 'Candidate'}</h3>
          <p className="panel-description">{candidate.title ?? '—'}</p>
        </div>
        <div className="pill">{candidate.final_score ?? candidate.provider_score ?? '—'}</div>
      </div>
      <div className="meta-row">
        <span>{candidate.company ?? '—'}</span>
        <span>{candidate.location ?? '—'}</span>
        <span>{candidate.source ?? 'Provider'}</span>
      </div>
      <pre>{JSON.stringify(candidate.raw_data ?? {}, null, 2)}</pre>
    </div>
  )
}
