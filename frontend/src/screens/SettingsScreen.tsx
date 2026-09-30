import { Check } from 'lucide-react'
import { useTheme, type ThemePreference } from '../theme/ThemeProvider'
import { initialsOf } from '../models/discovery'
import './SettingsScreen.css'

const APPEARANCE_OPTIONS: Array<{ value: ThemePreference; label: string }> = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
  { value: 'system', label: 'System' },
]

/** Intentionally minimal — per the product boundary, never an elaborate
 * settings application. Account identity + the one real preference this
 * product has (Appearance). Nothing else lives here yet. */
export function SettingsScreen({ recruiterName }: { recruiterName: string }) {
  const { preference, setPreference } = useTheme()
  return (
    <div className="settings">
      <h1 className="settings__title">Settings</h1>

      <section className="settings__section" aria-labelledby="settings-account">
        <h2 id="settings-account" className="settings__section-title">
          Account
        </h2>
        <div className="settings__account">
          <span className="settings__avatar" aria-hidden="true">
            {initialsOf(recruiterName)}
          </span>
          <span className="settings__account-name">{recruiterName}</span>
        </div>
      </section>

      <section className="settings__section" aria-labelledby="settings-appearance">
        <h2 id="settings-appearance" className="settings__section-title">
          Appearance
        </h2>
        <div className="settings__options" role="radiogroup" aria-labelledby="settings-appearance">
          {APPEARANCE_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={preference === option.value}
              className={`settings__option${preference === option.value ? ' is-active' : ''}`}
              onClick={() => setPreference(option.value)}
            >
              <span>{option.label}</span>
              {preference === option.value ? <Check size={15} aria-hidden="true" /> : null}
            </button>
          ))}
        </div>
      </section>
    </div>
  )
}
