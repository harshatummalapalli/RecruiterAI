import type { Candidate } from '../types'

type CandidateComparisonPanelProps = {
  candidates: Candidate[]
}

function formatValue(value: unknown): string {
  if (value == null || value === '') {
    return '—'
  }

  return String(value)
}

export function CandidateComparisonPanel({ candidates }: CandidateComparisonPanelProps) {
  if (!candidates.length) {
    return null
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Candidate comparison</p>
          <h3>Side-by-side recruiter review</h3>
        </div>
      </div>
      <div className="comparison-grid">
        {candidates.map((candidate) => (
          <div key={`${candidate.name}-${candidate.company}`} className="comparison-card">
            <h4>{formatValue(candidate.name ?? 'Candidate')}</h4>
            <p className="muted">{formatValue(candidate.title)} • {formatValue(candidate.company)}</p>
            <ul className="comparison-list">
              <li><strong>Experience</strong><span>{formatValue(candidate.experience_years ?? candidate.years_of_experience)} years</span></li>
              <li><strong>Skills</strong><span>{formatValue(candidate.ai_skills?.join(', ') || candidate.raw_data?.skills ? String(candidate.raw_data?.skills) : '—')}</span></li>
              <li><strong>AI technologies</strong><span>{formatValue(candidate.match_explanation?.matched_ai_technologies?.join(', ') || '—')}</span></li>
              <li><strong>Location</strong><span>{formatValue(candidate.location)}</span></li>
              <li><strong>Match score</strong><span>{formatValue(candidate.final_score ?? candidate.provider_score)}</span></li>
              <li><strong>Strengths</strong><span>{formatValue(candidate.match_explanation?.matched_skills?.join(', ') || '—')}</span></li>
              <li><strong>Gaps</strong><span>{formatValue(candidate.match_explanation?.missing_skills?.join(', ') || '—')}</span></li>
              <li><strong>Resume status</strong><span>{formatValue(candidate.resume_status ?? 'Pending')}</span></li>
              <li><strong>Notes</strong><span>{formatValue(candidate.notes?.[0]?.text || 'No notes yet')}</span></li>
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}
