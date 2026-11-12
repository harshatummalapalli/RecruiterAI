import './StepPlayer.css'

// The three phases of a search, product-facing. DEFINE covers everything before
// the search — the JD, the boundary, the brief and any clarifications (it is all
// still defining the role). DISCOVER is the search itself: candidates being found
// and read. DECIDE is reviewing them. The internal step ids stay jd/brief/review;
// jd AND brief both live in Define, and review is Discover while the search runs,
// Decide once it is done.
export type Phase = 'define' | 'discover' | 'decide'

const STAGES: Array<{ key: Phase; n: string; label: string }> = [
  { key: 'define', n: '1', label: 'Define' },
  { key: 'discover', n: '2', label: 'Discover' },
  { key: 'decide', n: '3', label: 'Decide' },
]

type Props = {
  phase: Phase
  onGo: (phase: Phase) => void
  // Discover is reachable once a search has started; Decide once it has results.
  canDiscover: boolean
  canDecide: boolean
}

export function StepPlayer({ phase, onGo, canDiscover, canDecide }: Props) {
  const reachable: Record<Phase, boolean> = { define: true, discover: canDiscover, decide: canDecide }
  const activeIndex = STAGES.findIndex((stage) => stage.key === phase)
  return (
    <nav className="stepplayer" aria-label="Search stages">
      {STAGES.map((stage, index) => {
        const isOn = stage.key === phase
        const isDone = index < activeIndex
        return (
          <button
            key={stage.key}
            type="button"
            className={`stepplayer__step${isOn ? ' is-on' : ''}${isDone ? ' is-done' : ''}`}
            aria-current={isOn ? 'step' : undefined}
            disabled={!reachable[stage.key]}
            onClick={() => reachable[stage.key] && onGo(stage.key)}
          >
            <span className="stepplayer__n" aria-hidden="true">{stage.n}</span>
            {stage.label}
          </button>
        )
      })}
    </nav>
  )
}
