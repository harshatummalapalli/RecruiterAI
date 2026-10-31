import { useId } from 'react'
import { X } from 'lucide-react'

// Free-text tag input (no canonical validation) — for company names, where the
// recruiter types each one and Enter/comma commits it. Reuses the brief-tag
// styles so it matches LocationMultiTypeahead. Each value is independent; the
// backend treats an "include" list as OR (ever worked at ANY of them).
type TagInputProps = {
  label: string
  values: string[]
  onChange: (values: string[]) => void
  placeholder?: string
  disabled?: boolean
  caption?: string
}

export function TagInput({ label, values, onChange, placeholder, disabled, caption }: TagInputProps) {
  const inputId = useId()

  const addValue = (raw: string) => {
    const value = raw.trim()
    if (value && !values.includes(value)) {
      onChange([...values, value])
    }
  }

  const removeAt = (index: number) => {
    onChange(values.filter((_, i) => i !== index))
  }

  return (
    <div className="brief-field">
      <label className="brief-field__label" htmlFor={inputId}>
        {label}
      </label>
      <div className="brief-tag-field">
        {values.map((value, index) => (
          <span key={`${value}-${index}`} className="brief-tag">
            {value}
            <button type="button" className="brief-tag__remove" onClick={() => removeAt(index)} aria-label={`Remove ${value}`} disabled={disabled}>
              <X size={12} />
            </button>
          </span>
        ))}
        <input
          id={inputId}
          type="text"
          className="brief-tag-field__input"
          autoComplete="off"
          disabled={disabled}
          placeholder={values.length ? '' : placeholder}
          aria-label={label}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ',') {
              event.preventDefault()
              addValue(event.currentTarget.value)
              event.currentTarget.value = ''
            }
          }}
          onBlur={(event) => {
            addValue(event.currentTarget.value)
            event.currentTarget.value = ''
          }}
        />
      </div>
      {caption ? <span className="boundary-form__caption">{caption}</span> : null}
    </div>
  )
}
