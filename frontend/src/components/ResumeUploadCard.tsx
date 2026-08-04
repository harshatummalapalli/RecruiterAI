import { UploadCloud, FileText, Clock3, CheckCircle2 } from 'lucide-react'

type ResumeUploadCardProps = {
  name?: string | null
  filename?: string | null
  uploadTimestamp?: string | null
  status?: string | null
  parseStatus?: string | null
}

export function ResumeUploadCard({ name, filename, uploadTimestamp, status, parseStatus }: ResumeUploadCardProps) {
  return (
    <div className="resume-card">
      <div className="resume-card__header">
        <div className="resume-card__icon">
          <UploadCloud size={16} />
        </div>
        <div>
          <h4>{name ?? 'Resume'}</h4>
          <p>{filename ?? 'No resume uploaded yet'}</p>
        </div>
      </div>
      <div className="resume-card__meta">
        <span><Clock3 size={14} /> {uploadTimestamp ?? 'Awaiting upload'}</span>
        <span><CheckCircle2 size={14} /> {status ?? 'Pending upload'}</span>
        <span><FileText size={14} /> {parseStatus ?? 'Not parsed'}</span>
      </div>
      <button className="button secondary" type="button">Upload resume</button>
    </div>
  )
}
