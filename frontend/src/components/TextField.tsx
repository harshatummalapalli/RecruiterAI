import type { TextareaHTMLAttributes, InputHTMLAttributes } from 'react'

type FieldProps = {
  label: string
  hint?: string
  error?: string
  children: React.ReactNode
}

export function Field({ label, hint, error, children }: FieldProps) {
  return (
    <label className="field">
      <span className="field__label">{label}</span>
      {hint ? <span className="field__hint">{hint}</span> : null}
      {children}
      {error ? <span className="field__error">{error}</span> : null}
    </label>
  )
}

type TextInputProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string
  hint?: string
  error?: string
}

export function TextField({ label, hint, error, ...props }: TextInputProps) {
  return (
    <Field label={label} hint={hint} error={error}>
      <input {...props} />
    </Field>
  )
}

type TextAreaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  label: string
  hint?: string
  error?: string
}

export function TextAreaField({ label, hint, error, ...props }: TextAreaProps) {
  return (
    <Field label={label} hint={hint} error={error}>
      <textarea {...props} />
    </Field>
  )
}
