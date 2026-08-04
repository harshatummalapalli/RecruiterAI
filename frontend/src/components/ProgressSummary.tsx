import { ArrowRight, Sparkles } from 'lucide-react'
import { WorkflowProgress } from './WorkflowProgress'

type ProgressSummaryProps = {
  busyState: 'parsing' | 'searching' | 'exporting' | null
}

const copyByState: Record<NonNullable<ProgressSummaryProps['busyState']>, string> = {
  parsing: 'Parsing job description...',
  searching: 'Searching professional networks...',
  exporting: 'Generating match insights...',
}

export function ProgressSummary({ busyState }: ProgressSummaryProps) {
  if (!busyState) {
    return <WorkflowProgress busyState={null} />
  }

  return (
    <div className="stack">
      <div className="progress-summary" role="status">
        <div className="progress-summary__icon">
          <Sparkles size={16} />
        </div>
        <div>
          <strong>{copyByState[busyState]}</strong>
          <p className="muted">RecruiterAI is preparing the next step in the workflow.</p>
        </div>
        <ArrowRight size={16} />
      </div>
      <WorkflowProgress busyState={busyState} />
    </div>
  )
}
