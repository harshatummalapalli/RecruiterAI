import { useTheme, type ThemePreference } from '../theme/ThemeProvider'
import './AppearanceControl.css'

const OPTIONS: Array<{ value: ThemePreference; label: string }> = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
  { value: 'system', label: 'System' },
]

// Deliberately small and quiet: a preference, not a feature. Lives in the sidebar footer rather than the
// workspace header — this product has no dedicated Settings screen yet.
export function AppearanceControl() {
  const { preference, setPreference } = useTheme()
  return (
    <label className="appearance-control">
      <span className="appearance-control__label">Appearance</span>
      <select
        className="appearance-control__select"
        value={preference}
        onChange={(event) => setPreference(event.target.value as ThemePreference)}
        aria-label="Appearance"
      >
        {OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )
}
