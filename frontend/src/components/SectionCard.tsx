import type { ReactNode } from 'react'

type SectionCardProps = {
  title: string
  description?: string
  children: ReactNode
}

export function SectionCard({ title, description, children }: SectionCardProps) {
  return (
    <div className="section-card">
      <div className="section-card__header">
        <h3>{title}</h3>
        {description ? <p>{description}</p> : null}
      </div>
      {children}
    </div>
  )
}
