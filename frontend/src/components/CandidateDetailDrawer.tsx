import { useMemo, useRef, useState } from 'react'
import { MessageSquareText, Sparkles, UploadCloud } from 'lucide-react'
import type { Candidate } from '../types'
import { ResumeUploadCard } from './ResumeUploadCard'
import { Tabs } from './Tabs'

type CandidateDetailDrawerProps = {
  candidate: Candidate | null
  selectedCandidateState: { shortlist: boolean; rejected: boolean; notes: Array<{ id: string; text: string; createdAt: string }>; resumes: Array<{ name: string; uploadedAt: string }>; activity: Array<{ id: string; type: string; label: string; detail: string; timestamp: string }>; exported: boolean; status: string } | null
  onAction?: (action: 'shortlist' | 'reject' | 'note' | 'export', payload?: string) => void
  onUploadResume?: (candidate: Candidate, fileName: string) => void
  onEditNote?: (candidate: Candidate, noteId: string, noteText: string) => void
  onDeleteNote?: (candidate: Candidate, noteId: string) => void
}

const tabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'resume', label: 'Resume' },
  { id: 'match', label: 'Match' },
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

export function CandidateDetailDrawer({ candidate, selectedCandidateState, onAction, onUploadResume, onEditNote, onDeleteNote }: CandidateDetailDrawerProps) {
  const [activeTab, setActiveTab] = useState('overview')
  const [noteDraft, setNoteDraft] = useState('')
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null)
  const [editingText, setEditingText] = useState('')
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const candidateState = useMemo(() => selectedCandidateState ?? { shortlist: false, rejected: false, notes: [], resumes: [], activity: [], exported: false, status: 'New' }, [selectedCandidateState])
  const aiSkills = (candidate?.ai_skills ?? (Array.isArray(candidate?.raw_data?.ai_skills) ? candidate?.raw_data?.ai_skills : [])) as unknown[]

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
        <span>{candidateState.status}</span>
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
        <button className="button secondary" type="button" onClick={() => onAction?.('note', noteDraft.trim() || 'Note added')}>
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

      <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab}>
        {activeTab === 'overview' ? (
          <div className="detail-panel">
            <div className="detail-panel__grid">
              <div>
                <h4>Overview</h4>
                <p className="muted">Current company: {formatValue(candidate.company)}</p>
                <p className="muted">Current title: {formatValue(candidate.title)}</p>
                <p className="muted">Location: {formatValue(candidate.location)}</p>
                <p className="muted">Experience: {formatValue(candidate.experience_years ?? candidate.years_of_experience)} years</p>
                <p className="muted">Profile URL: {formatValue(candidate.profile_url ?? 'Not provided')}</p>
              </div>
              <div>
                <h4>AI skills</h4>
                <div className="chip-row">
                  {aiSkills.slice(0, 6).map((skill: unknown) => <span className="chip" key={String(skill)}>{String(skill)}</span>)}
                </div>
                <p className="muted">{formatValue(candidate.summary ?? 'Representative profile summary prepared for recruiter review.')}</p>
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
            <p className="muted">Match score: {formatValue(candidate.final_score ?? candidate.provider_score)}</p>
            <p className="muted">The match explanation is displayed in the recruiting workspace and can be expanded with future enrichment signals.</p>
          </div>
        ) : null}
        {activeTab === 'notes' ? (
          <div className="detail-panel">
            <div className="detail-actions">
              <textarea rows={3} value={noteDraft} onChange={(event) => setNoteDraft(event.target.value)} placeholder="Add a recruiter note for this candidate" />
              <button className="button secondary" type="button" onClick={() => { onAction?.('note', noteDraft.trim()); setNoteDraft('') }}>Save note</button>
            </div>
            {candidateState.notes.length ? (
              <ul className="note-list">
                {candidateState.notes.map((note) => (
                  <li key={note.id}>
                    <div className="note-item">
                      <div>{note.text}</div>
                      <div className="note-item__meta">{note.createdAt}</div>
                      <div className="note-item__actions">
                        <button className="button secondary" type="button" onClick={() => { setEditingNoteId(note.id); setEditingText(note.text) }}>Edit</button>
                        <button className="button secondary" type="button" onClick={() => onDeleteNote?.(candidate, note.id)}>Delete</button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">Notes shared between recruiting stakeholders will appear here.</p>
            )}
            {editingNoteId ? (
              <div className="detail-actions">
                <textarea rows={2} value={editingText} onChange={(event) => setEditingText(event.target.value)} />
                <button className="button secondary" type="button" onClick={() => { onEditNote?.(candidate, editingNoteId, editingText); setEditingNoteId(null); setEditingText('') }}>Update note</button>
              </div>
            ) : null}
          </div>
        ) : null}
        {activeTab === 'activity' ? (
          <div className="detail-panel">
            <div className="activity-list">
              {(candidateState.activity.length ? candidateState.activity : [
                { id: 'jd', type: 'jd', label: 'JD parsed', detail: 'The job description was parsed into a recruiter-ready brief.', timestamp: 'Now' },
                { id: 'search', type: 'search', label: 'Search executed', detail: 'The search workflow was launched from the workbench.', timestamp: 'Now' },
                { id: 'view', type: 'view', label: 'Candidate viewed', detail: 'The recruiter opened the candidate workspace.', timestamp: 'Now' },
                { id: 'resume', type: 'resume', label: 'Resume uploaded', detail: 'A resume attachment was added locally.', timestamp: 'Now' },
                { id: 'shortlist', type: 'shortlist', label: 'Shortlisted', detail: 'Recruiter flagged the candidate for follow-up.', timestamp: 'Now' },
                { id: 'reject', type: 'reject', label: 'Rejected', detail: 'Recruiter moved the candidate out of the active slate.', timestamp: 'Now' },
                { id: 'export', type: 'export', label: 'Exported', detail: 'Local export prepared for next-step handoff.', timestamp: 'Now' },
              ]).map((item) => (
                <div key={item.id} className="activity-item">
                  <strong>{item.label}</strong>
                  <p className="muted">{item.detail}</p>
                  <p className="muted">{item.timestamp}</p>
                </div>
              ))}
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
