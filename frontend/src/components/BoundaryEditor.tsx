import { useState } from 'react'
import { Pencil } from 'lucide-react'
import { SearchBoundaryForm } from '../screens/SearchBoundaryForm'
import { formatBoundaryLocation, workModeLabel } from '../models/livingBrief'
import { isSearchBoundaryComplete, type SearchBoundary } from '../models/searchBoundary'
import './LivingBrief.css'

type BoundaryEditorProps = {
  boundary: SearchBoundary
  /** Validates and applies on the server. Deterministic: no model call. Rejects with readable messages on refusal. */
  onApply: (boundary: SearchBoundary) => Promise<void>
  /** Plain sentence shown under the summary, e.g. that work mode cannot be enforced. */
  limitation?: string | null
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

/**
 * The Search Boundary as it appears once the brief exists: a read-only summary with an explicit Edit. It is the single
 * source for hiring company, where and work mode. Editing it never re-reads the role; the server re-applies it to the
 * reading it already has.
 */
export function BoundaryEditor({ boundary, onApply, limitation, open, onOpenChange }: BoundaryEditorProps) {
  const [localOpen, setLocalOpen] = useState(false)
  const editing = open ?? localOpen
  const setEditing = (next: boolean) => {
    setLocalOpen(next)
    onOpenChange?.(next)
  }
  const [draft, setDraft] = useState<SearchBoundary>(boundary)
  const [errors, setErrors] = useState<string[]>([])
  const [applying, setApplying] = useState(false)

  const begin = () => {
    setDraft(boundary)
    setErrors([])
    setEditing(true)
  }

  const apply = async () => {
    setApplying(true)
    setErrors([])
    try {
      await onApply(draft)
      setEditing(false)
    } catch (error) {
      const messages = (error as { messages?: string[] }).messages
      setErrors(messages?.length ? messages : ['The search boundary could not be updated.'])
    } finally {
      setApplying(false)
    }
  }

  return (
    <div className="lb-boundary">
      {editing ? (
        <>
          <SearchBoundaryForm boundary={draft} onChange={(updater) => setDraft(updater)} disabled={applying} />
          {errors.length ? (
            <ul className="lb-errors" role="alert">
              {errors.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          ) : null}
          <div className="lb-boundary__actions">
            <button type="button" className="lb-button lb-button--primary" onClick={apply} disabled={applying || !isSearchBoundaryComplete(draft)}>
              {applying ? 'Applying…' : 'Apply'}
            </button>
            <button type="button" className="lb-button" onClick={() => setEditing(false)} disabled={applying}>
              Cancel
            </button>
          </div>
        </>
      ) : (
        <>
          <dl className="lb-facts">
            <dt>Hiring company</dt>
            <dd>{boundary.hiring_company}</dd>
            <dt>Where</dt>
            <dd>{formatBoundaryLocation(boundary)}</dd>
            <dt>Work mode</dt>
            <dd>{workModeLabel(boundary)}</dd>
          </dl>
          <button type="button" className="lb-link" onClick={begin}>
            <Pencil size={13} aria-hidden="true" /> Edit boundary
          </button>
        </>
      )}
      {limitation && !editing ? (
        <p className="lb-limitation">
          <span className="lb-tag lb-tag--limitation">System limitation</span> {limitation}
        </p>
      ) : null}
    </div>
  )
}
