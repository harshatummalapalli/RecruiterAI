import type { ReactNode } from 'react'

type WorkflowHeaderProps = {
  title: string
  description: string
  actions?: ReactNode
}

export function WorkflowHeader({ title, description, actions }: WorkflowHeaderProps) {
  return (
    <header className="workflow-header">
      <div>
        <p className="eyebrow">RecruiterAI</p>
        <h1>{title}</h1>
        <p className="hero-copy">{description}</p>
      </div>
      {actions ? <div className="workflow-header__actions">{actions}</div> : null}
    </header>
  )
}
