import { useEffect, useRef, useState } from 'react'
import { initialsOf } from '../models/discovery'
import { AppearanceControl } from './AppearanceControl'
import './AccountControl.css'

/** The account identity, shared by the global shell (every screen) — a
 * small, deliberately quiet trigger that opens Appearance + Sign out.
 * Never a settings page of its own; see screens/SettingsScreen.tsx for
 * the one place that gets a full page. */
export function AccountControl({ recruiterName, onSignOut }: { recruiterName: string; onSignOut: () => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    if (!open) return
    const onDocClick = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])
  return (
    <div className="account-control" ref={ref}>
      <button type="button" className="account-control__trigger" onClick={() => setOpen((v) => !v)} aria-haspopup="menu" aria-expanded={open}>
        <span className="account-control__avatar" aria-hidden="true">
          {initialsOf(recruiterName)}
        </span>
        <span className="account-control__name">{recruiterName}</span>
      </button>
      {open ? (
        <div className="account-control__menu" role="menu">
          <div className="account-control__appearance">
            <AppearanceControl />
          </div>
          <button
            type="button"
            role="menuitem"
            className="account-control__signout"
            onClick={() => {
              setOpen(false)
              onSignOut()
            }}
          >
            Sign out
          </button>
        </div>
      ) : null}
    </div>
  )
}
