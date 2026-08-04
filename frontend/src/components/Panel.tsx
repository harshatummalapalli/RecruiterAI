import type { ReactNode } from 'react'

type PanelProps = {
  title: string
  description?: string
  children: ReactNode
  actions?: ReactNode
  className?: string
}

export function Panel({ title, description, children, actions, className }: PanelProps) {
  return (
    <section className={['panel', className].filter(Boolean).join(' ')}>
      <div className="panel-header">
        <div>
          <h2>{title}</h2>
          {description ? <p className="panel-description">{description}</p> : null}
        </div>
        {actions ? <div className="panel-actions">{actions}</div> : null}
      </div>
      {children}
    </section>
  )
}
