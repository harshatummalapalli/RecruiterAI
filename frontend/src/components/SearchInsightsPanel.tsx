import type { SearchAnalytics } from '../types'
import type { SearchSummary } from '../services/recruiterWorkflow'

type SearchInsightsPanelProps = {
  summary?: SearchSummary | null
  analytics?: SearchAnalytics | null
}

export function SearchInsightsPanel({ summary, analytics }: SearchInsightsPanelProps) {
  if (!summary && !analytics) {
    return null
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Search analytics</p>
          <h3>Recruiter insights</h3>
        </div>
      </div>
      <div className="insight-grid">
        <div className="insight-card">
          <span className="insight-label">Candidate count</span>
          <strong>{summary?.candidateCount ?? analytics?.candidateCount ?? 0}</strong>
        </div>
        <div className="insight-card">
          <span className="insight-label">Average match</span>
          <strong>{summary?.averageMatch ?? analytics?.averageMatch ?? '0%'}</strong>
        </div>
        <div className="insight-card">
          <span className="insight-label">Median match</span>
          <strong>{summary?.medianMatch ?? analytics?.medianMatch ?? '0%'}</strong>
        </div>
        <div className="insight-card">
          <span className="insight-label">Highest score</span>
          <strong>{summary?.highestMatch ?? analytics?.highestScore ?? '0%'}</strong>
        </div>
        <div className="insight-card">
          <span className="insight-label">Lowest score</span>
          <strong>{summary?.lowestMatch ?? analytics?.lowestScore ?? '0%'}</strong>
        </div>
      </div>
      <div className="insight-list">
        <div><strong>Top companies</strong><p className="muted">{(summary?.topCompanies ?? analytics?.topCompanies ?? []).join(', ') || '—'}</p></div>
        <div><strong>Top locations</strong><p className="muted">{(summary?.topLocations ?? analytics?.topLocations ?? []).join(', ') || '—'}</p></div>
        <div><strong>Top skills</strong><p className="muted">{(summary?.topSkills ?? analytics?.topSkills ?? []).join(', ') || '—'}</p></div>
      </div>
    </div>
  )
}
