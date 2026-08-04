import { FileText, MoreHorizontal, Sparkles, UploadCloud } from 'lucide-react'
import type { Candidate } from '../types'
import { getCandidateKey } from '../services/recruiterWorkflow'
import { StatusPill } from './StatusPill'

type CandidateTableProps = {
  candidates: Candidate[]
  selectedKey: string | null
  onSelect: (key: string) => void
  isLoading?: boolean
  candidateCount?: number
}

function formatValue(value: unknown): string {
  if (value == null || value === '') {
    return '—'
  }

  return String(value)
}

export function CandidateTable({ candidates, selectedKey, onSelect, isLoading = false, candidateCount }: CandidateTableProps) {
  if (isLoading) {
    return (
      <div className="candidate-table" role="status" aria-label="Loading candidates">
        <div className="candidate-table__header" role="row">
          <span role="columnheader">Match</span>
          <span role="columnheader">Name</span>
          <span role="columnheader">Current Title</span>
          <span role="columnheader">Company</span>
          <span role="columnheader">Experience</span>
          <span role="columnheader">Location</span>
          <span role="columnheader">Resume</span>
          <span role="columnheader">Actions</span>
        </div>
        {Array.from({ length: 3 }).map((_, index) => (
          <div key={index} className="candidate-row candidate-row--skeleton">
            <span className="candidate-row__score"><div className="skeleton-bar" /></span>
            <span><div className="skeleton-bar" /></span>
            <span><div className="skeleton-bar" /></span>
            <span><div className="skeleton-bar" /></span>
            <span><div className="skeleton-bar" /></span>
            <span><div className="skeleton-bar" /></span>
            <span><div className="skeleton-bar" /></span>
            <span><div className="skeleton-bar" /></span>
          </div>
        ))}
      </div>
    )
  }

  if (!candidates.length) {
    return (
      <div className="empty-state">
        <h3>Find matching talent</h3>
        <p className="muted">Once the search brief is ready, matching candidates will appear here for review, scoring, and follow-up.</p>
      </div>
    )
  }

  return (
    <div className="candidate-table" role="table" aria-label="Candidate results">
      <div className="candidate-table__summary">
        <span>{candidateCount ?? candidates.length} candidates in workspace</span>
      </div>
      <div className="candidate-table__header" role="row">
        <span role="columnheader">Match</span>
        <span role="columnheader">Name</span>
        <span role="columnheader">Current Title</span>
        <span role="columnheader">Company</span>
        <span role="columnheader">Experience</span>
        <span role="columnheader">Location</span>
        <span role="columnheader">Resume</span>
        <span role="columnheader">Actions</span>
      </div>
      {candidates.map((candidate) => {
        const key = getCandidateKey(candidate)
        const isSelected = selectedKey === key
        return (
          <button key={key} className={`candidate-row ${isSelected ? 'is-selected' : ''}`} onClick={() => onSelect(key)}>
            <span className="candidate-row__score"><Sparkles size={14} /> {candidate.final_score ?? candidate.provider_score ?? '—'}</span>
            <span>{formatValue(candidate.name ?? 'Candidate')}</span>
            <span>{formatValue(candidate.title)}</span>
            <span>{formatValue(candidate.company)}</span>
            <span>{formatValue(candidate.experience_years ?? candidate.years_of_experience)}</span>
            <span>{formatValue(candidate.location)}</span>
            <span><StatusPill tone="neutral">{formatValue(candidate.resume_status ?? 'Pending')}</StatusPill></span>
            <span className="candidate-row__actions">
              <UploadCloud size={14} />
              <FileText size={14} />
              <MoreHorizontal size={14} />
            </span>
          </button>
        )
      })}
    </div>
  )
}
