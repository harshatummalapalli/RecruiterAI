import { useEffect, useId, useRef, useState } from 'react'

// Generic case-insensitive prefix-match typeahead over a caller-supplied
// canonical name list (country/state/city) — no LLM, no abbreviation
// expansion. The displayed and stored value is always the exact canonical
// name the caller's `search` function returned, never free-typed raw text.
type LocationTypeaheadProps = {
  label: string
  value: string
  onChange: (value: string) => void
  search: (query: string) => string[]
  placeholder?: string
  disabled?: boolean
  required?: boolean
}

export function LocationTypeahead({ label, value, onChange, search, placeholder, disabled, required }: LocationTypeaheadProps) {
  const [draft, setDraft] = useState(value)
  const [options, setOptions] = useState<string[]>([])
  const [isOpen, setIsOpen] = useState(false)
  const listId = useId()
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    setDraft(value)
  }, [value])

  useEffect(() => {
    const onClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  return (
    <div className="location-typeahead" ref={containerRef}>
      <label className="brief-field__label" htmlFor={listId}>
        {label}
        {required ? <span aria-hidden="true"> *</span> : null}
      </label>
      <input
        id={listId}
        type="text"
        className="brief-input"
        autoComplete="off"
        value={draft}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(event) => {
          const next = event.target.value
          setDraft(next)
          // Any manual edit invalidates a previously confirmed canonical
          // selection until the recruiter picks a new option from the list.
          onChange('')
          setOptions(next.trim().length >= 1 ? search(next) : [])
          setIsOpen(true)
        }}
        onFocus={() => {
          if (draft.trim().length >= 1) {
            setOptions(search(draft))
            setIsOpen(true)
          }
        }}
      />
      {isOpen && options.length > 0 ? (
        <ul className="location-typeahead__list" role="listbox">
          {options.map((option) => (
            <li key={option}>
              <button
                type="button"
                className="location-typeahead__option"
                onClick={() => {
                  setDraft(option)
                  onChange(option)
                  setOptions([])
                  setIsOpen(false)
                }}
              >
                {option}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
