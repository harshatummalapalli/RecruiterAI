import { useState } from 'react'
import { X } from 'lucide-react'

type TagFieldProps = {
  label: string
  values: string[]
  onChange: (next: string[]) => void
  placeholder?: string
}

export function TagField({ label, values, onChange, placeholder }: TagFieldProps) {
  const [draft, setDraft] = useState('')

  const commitDraft = () => {
    const trimmed = draft.trim()
    if (trimmed && !values.includes(trimmed)) {
      onChange([...values, trimmed])
    }
    setDraft('')
  }

  const removeAt = (index: number) => {
    onChange(values.filter((_, i) => i !== index))
  }

  return (
    <div className="brief-field">
      <span className="brief-field__label">{label}</span>
      <div className="brief-tag-field">
        {values.map((value, index) => (
          <span key={`${value}-${index}`} className="brief-tag">
            {value}
            <button
              type="button"
              className="brief-tag__remove"
              onClick={() => removeAt(index)}
              aria-label={`Remove ${value}`}
            >
              <X size={12} />
            </button>
          </span>
        ))}
        <input
          className="brief-tag-field__input"
          type="text"
          value={draft}
          onChange={(event) => {
            const value = event.target.value
            if (value.endsWith(',')) {
              setDraft(value.slice(0, -1))
              commitDraft()
              return
            }
            setDraft(value)
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              commitDraft()
            } else if (event.key === 'Backspace' && draft === '' && values.length > 0) {
              removeAt(values.length - 1)
            }
          }}
          onBlur={commitDraft}
          placeholder={values.length ? '' : placeholder}
          aria-label={label}
        />
      </div>
    </div>
  )
}
