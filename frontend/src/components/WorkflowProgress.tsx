type WorkflowProgressProps = {
  busyState: 'parsing' | 'searching' | 'exporting' | null
}

const steps = ['Parse Brief', 'Prepare Search', 'Search Candidates', 'Rank Results', 'Ready for Review']

const activeIndexByState: Record<NonNullable<WorkflowProgressProps['busyState']>, number> = {
  parsing: 0,
  searching: 2,
  exporting: 3,
}

export function WorkflowProgress({ busyState }: WorkflowProgressProps) {
  const activeIndex = busyState ? activeIndexByState[busyState] : steps.length - 1

  return (
    <div className="workflow-progress" aria-label="Workflow progress">
      {steps.map((step, index) => {
        const isActive = index <= activeIndex
        const isCurrent = index === activeIndex
        return (
          <div key={step} className={`workflow-progress__step ${isActive ? 'is-active' : ''} ${isCurrent ? 'is-current' : ''}`}>
            <span className="workflow-progress__dot" />
            <span>{step}</span>
          </div>
        )
      })}
    </div>
  )
}
