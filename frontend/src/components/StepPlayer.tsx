import './StepPlayer.css'

export type Stage = 'jd' | 'brief' | 'review'

// The three stages of a search, in order. The product-facing names are Define
// (write the brief) · Discover (the role read) · Decide (review candidates); the
// internal step ids stay jd/brief/review.
const STAGES: Array<{ key: Stage; n: string; label: string }> = [
  { key: 'jd', n: '1', label: 'Define' },
  { key: 'brief', n: '2', label: 'Discover' },
  { key: 'review', n: '3', label: 'Decide' },
]

type Props = {
  step: Stage
  onStep: (stage: Stage) => void
  // Discover is reachable once the role has been read; Decide once a search has run.
  canDiscover: boolean
  canDecide: boolean
}

export function StepPlayer({ step, onStep, canDiscover, canDecide }: Props) {
  const reachable: Record<Stage, boolean> = { jd: true, brief: canDiscover, review: canDecide }
  const activeIndex = STAGES.findIndex((stage) => stage.key === step)
  return (
    <nav className="stepplayer" aria-label="Search stages">
      {STAGES.map((stage, index) => {
        const isOn = stage.key === step
        const isDone = index < activeIndex
        return (
          <button
            key={stage.key}
            type="button"
            className={`stepplayer__step${isOn ? ' is-on' : ''}${isDone ? ' is-done' : ''}`}
            aria-current={isOn ? 'step' : undefined}
            disabled={!reachable[stage.key]}
            onClick={() => reachable[stage.key] && onStep(stage.key)}
          >
            <span className="stepplayer__n" aria-hidden="true">{stage.n}</span>
            {stage.label}
          </button>
        )
      })}
    </nav>
  )
}
