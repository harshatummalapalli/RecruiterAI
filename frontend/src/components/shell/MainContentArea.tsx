import type { ReactNode } from 'react'

type MainContentAreaProps = {
  children: ReactNode
}

export function MainContentArea({ children }: MainContentAreaProps) {
  return <main className="app-main">{children}</main>
}
