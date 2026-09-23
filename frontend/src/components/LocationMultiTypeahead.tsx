import { useId, useRef, useState } from 'react'
import { X } from 'lucide-react'

// Multi-select variant of LocationTypeahead — used for "specific states" /
// "specific cities" remote scopes, where the recruiter may pick more than
// one canonical place name. Every added tag came from `search`'s canonical
// results; free-typed text is never added directly.
type LocationMultiTypeaheadProps = {
  label: string
  values: string[]
  onChange: (values: string[]) => void
  search: (query: string) => string[]
  placeholder?: string
}

export function LocationMultiTypeahead({ label, values, onChange, search, placeholder }: LocationMultiTypeaheadProps) {
  const [draft, setDraft] = useState('')
  const [options, setOptions] = useState<string[]>([])
  const [isOpen, setIsOpen] = useState(false)
  const listId = useId()
  const containerRef = useRef<HTMLDivElement | null>(null)

  const addValue = (option: string) => {
    if (!values.includes(option)) {
      onChange([...values, option])
    }
    setDraft('')
    setOptions([])
    setIsOpen(false)
  }

  const removeAt = (index: number) => {
    onChange(values.filter((_, i) => i !== index))
  }

  return (
    <div className="location-typeahead" ref={containerRef}>
      <label className="brief-field__label" htmlFor={listId}>
        {label}
      </label>
      <div className="brief-tag-field">
        {values.map((value, index) => (
          <span key={`${value}-${index}`} className="brief-tag">
            {value}
            <button type="button" className="brief-tag__remove" onClick={() => removeAt(index)} aria-label={`Remove ${value}`}>
              <X size={12} />
            </button>
          </span>
        ))}
        <input
          id={listId}
          type="text"
          className="brief-tag-field__input"
          autoComplete="off"
          value={draft}
          onChange={(event) => {
            const next = event.target.value
            setDraft(next)
            setOptions(next.trim().length >= 1 ? search(next) : [])
            setIsOpen(true)
          }}
          placeholder={values.length ? '' : placeholder}
          aria-label={label}
        />
      </div>
      {isOpen && options.length > 0 ? (
        <ul className="location-typeahead__list" role="listbox">
          {options.map((option) => (
            <li key={option}>
              <button type="button" className="location-typeahead__option" onClick={() => addValue(option)}>
                {option}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
