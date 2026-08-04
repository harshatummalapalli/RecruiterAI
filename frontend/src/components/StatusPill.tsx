import type { ReactNode } from 'react'

type StatusPillProps = {
  tone?: 'neutral' | 'success' | 'warning' | 'danger'
  children: ReactNode
}

export function StatusPill({ tone = 'neutral', children }: StatusPillProps) {
  return <span className={`status-pill status-pill--${tone}`}>{children}</span>
}
