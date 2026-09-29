import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type ThemePreference = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'recruiterai:theme'

type ThemeContextValue = {
  preference: ThemePreference
  setPreference: (value: ThemePreference) => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

function readStored(): ThemePreference {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (raw === 'light' || raw === 'dark' || raw === 'system') return raw
  } catch {
    // Best-effort only: falls back to system, which is a safe default.
  }
  return 'system'
}

// The only place data-theme is ever written. "system" means "no opinion" — CSS's own
// prefers-color-scheme media query decides, so the attribute is removed rather than set.
function applyTheme(preference: ThemePreference): void {
  const root = document.documentElement
  if (preference === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', preference)
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(readStored)

  useEffect(() => {
    applyTheme(preference)
  }, [preference])

  // While "System" is selected, the CSS media query already repaints the moment the OS setting changes —
  // no reload, no flash. This listener exists only so anything that reads the attribute (not just CSS)
  // stays consistent; it deliberately re-applies the same "system" state rather than resolving to
  // light/dark itself, so there is exactly one source of truth for what data-theme means.
  useEffect(() => {
    if (preference !== 'system' || !window.matchMedia) return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => applyTheme('system')
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [preference])

  const setPreference = (value: ThemePreference) => {
    setPreferenceState(value)
    try {
      window.localStorage.setItem(STORAGE_KEY, value)
    } catch {
      // Best-effort only: the choice still applies for this session.
    }
  }

  const value = useMemo(() => ({ preference, setPreference }), [preference])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider')
  return ctx
}
