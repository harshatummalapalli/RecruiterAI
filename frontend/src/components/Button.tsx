import type { ButtonHTMLAttributes, ReactNode } from 'react'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  tone?: 'primary' | 'secondary' | 'ghost'
  icon?: ReactNode
}

export function Button({ tone = 'primary', icon, className, children, ...props }: ButtonProps) {
  return (
    <button className={['button', tone, className].filter(Boolean).join(' ')} {...props}>
      {icon ? <span className="button__icon">{icon}</span> : null}
      {children}
    </button>
  )
}
