import { useMemo, useRef, useState } from 'react'
import { MessageSquareText, Sparkles, UploadCloud } from 'lucide-react'
import type { Candidate } from '../types'
import { ResumeUploadCard } from './ResumeUploadCard'
import { Tabs } from './Tabs'

type CandidateDetailDrawerProps = {
  candidate: Candidate | null
  selectedCandidateState: { shortlist: boolean; rejected: boolean; notes: string[]; resumes: Array<{ name: string; uploadedAt: string }> } | null
  onAction?: (action: 'shortlist' | 'reject' | 'note' | 'export', payload?: string) => void
  onUploadResume?: (candidate: Candidate, fileName: string) => void
}

const tabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'resume', label: 'Resume' },
  { id: 'match', label: 'Match Explanation' },
  { id: 'enrichment', label: 'Enrichment' },
  { id: 'notes', label: 'Notes' },
  { id: 'activity', label: 'Activity' },
  { id: 'raw', label: 'Raw Data' },
]

function formatValue(value: unknown): string {
  if (value == null || value === '') {
    return '—'
  }

  return String(value)
}

export function CandidateDetailDrawer({ candidate, selectedCandidateState, onAction, onUploadResume }: CandidateDetailDrawerProps) {
  const [activeTab, setActiveTab] = useState('overview')
  const [noteDraft, setNoteDraft] = useState('')
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const candidateState = useMemo(() => selectedCandidateState ?? { shortlist: false, rejected: false, notes: [], resumes: [] }, [selectedCandidateState])

  if (!candidate) {
    return (
      <div className="empty-state empty-state--compact">
        <h3>Candidate preview</h3>
        <p className="muted">Select a candidate to review their profile, resume status, match explanations, and next actions.</p>
      </div>
    )
  }

  return (
    <div className="candidate-details">
      <div className="candidate-details__header">
        <div>
          <h3>{formatValue(candidate.name ?? 'Candidate')}</h3>
          <p className="panel-description">{formatValue(candidate.title)} • {formatValue(candidate.company)}</p>
        </div>
        <div className="candidate-details__score">
          <Sparkles size={14} />
          <span>{formatValue(candidate.final_score ?? candidate.provider_score)}</span>
        </div>
      </div>

      <div className="meta-row">
        <span>{formatValue(candidate.location)}</span>
        <span>{formatValue(candidate.experience_years ?? candidate.years_of_experience)} years</span>
        <span>{formatValue(candidate.resume_status ?? 'Resume pending')}</span>
      </div>

      <div className="detail-actions">
        <button className="button" type="button" onClick={() => fileInputRef.current?.click()}>
          <UploadCloud size={14} />
          Upload resume
        </button>
        <button className="button secondary" type="button" onClick={() => onAction?.('shortlist')}>
          Shortlist
        </button>
        <button className="button secondary" type="button" onClick={() => onAction?.('reject')}>
          Reject
        </button>
        <button className="button secondary" type="button" onClick={() => onAction?.('note', noteDraft.trim() || 'Note added') }>
          <MessageSquareText size={14} />
          Add note
        </button>
        <button className="button secondary" type="button" onClick={() => onAction?.('export')}>
          Export candidate
        </button>
        <input ref={fileInputRef} type="file" accept=".pdf,.doc,.docx" style={{ display: 'none' }} onChange={(event) => {
          const selectedFile = event.target.files?.[0]
          if (selectedFile && candidate) {
            onUploadResume?.(candidate, selectedFile.name)
            event.target.value = ''
          }
        }} />
      </div>

      <div className="detail-actions">
        <textarea rows={3} value={noteDraft} onChange={(event) => setNoteDraft(event.target.value)} placeholder="Add a recruiter note for this candidate" />
      </div>

      <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab}>
        {activeTab === 'overview' ? (
          <div className="detail-panel">
            <div className="detail-panel__grid">
              <div>
                <h4>Current fit</h4>
                <p className="muted">The current match summary is ready for recruiter review.</p>
                <p className="muted">Shortlisted: {candidateState.shortlist ? 'Yes' : 'No'} • Rejected: {candidateState.rejected ? 'Yes' : 'No'}</p>
              </div>
              <div>
                <h4>Suggested next step</h4>
                <p className="muted">Review the resume, enrich the profile, and decide whether to move to outreach.</p>
              </div>
            </div>
          </div>
        ) : null}
        {activeTab === 'resume' ? (
          <div className="detail-panel">
            {candidateState.resumes.length ? candidateState.resumes.map((resume) => (
              <ResumeUploadCard key={resume.name} name={candidate.name ?? 'Candidate'} filename={resume.name} uploadTimestamp={resume.uploadedAt} status="Ready for review" parseStatus="Parsed" />
            )) : <ResumeUploadCard name={candidate.name ?? 'Candidate'} filename="No resume uploaded yet" uploadTimestamp="Awaiting upload" status="Pending upload" parseStatus="Not parsed" />}
          </div>
        ) : null}
        {activeTab === 'match' ? (
          <div className="detail-panel">
            <p className="muted">Match explanation and recruiter guidance will appear here as the enrichment pipeline expands.</p>
          </div>
        ) : null}
        {activeTab === 'enrichment' ? (
          <div className="detail-panel">
            <p className="muted">Profile enrichment, project context, and role-specific insights will appear here.</p>
          </div>
        ) : null}
        {activeTab === 'notes' ? (
          <div className="detail-panel">
            {candidateState.notes.length ? (
              <ul className="note-list">
                {candidateState.notes.map((note, index) => <li key={`${note}-${index}`}>{note}</li>)}
              </ul>
            ) : (
              <p className="muted">Notes shared between recruiting stakeholders will appear here.</p>
            )}
          </div>
        ) : null}
        {activeTab === 'activity' ? (
          <div className="detail-panel">
            <div className="activity-list">
              <div className="activity-item">
                <strong>Resume reviewed</strong>
                <p className="muted">Candidate workspace updated locally for recruiter follow-up.</p>
              </div>
              <div className="activity-item">
                <strong>Note captured</strong>
                <p className="muted">Recruiter notes stay in the workspace until export.</p>
              </div>
            </div>
          </div>
        ) : null}
        {activeTab === 'raw' ? (
          <div className="detail-panel">
            <pre>{JSON.stringify(candidate.raw_data ?? {}, null, 2)}</pre>
          </div>
        ) : null}
      </Tabs>
    </div>
  )
}
