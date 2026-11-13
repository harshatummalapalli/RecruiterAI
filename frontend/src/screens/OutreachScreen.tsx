import { useEffect, useMemo, useState } from 'react'
import { Briefcase, ExternalLink, Mail, MessageSquare, RefreshCw } from 'lucide-react'
import { getOutreachInbox, type OutreachInboxRow } from '../services/outreach'
import { initialsOf } from '../models/discovery'
import './OutreachScreen.css'

const STATE_LABEL: Record<string, string> = {
  invited: 'Invited', messaged: 'Messaged', inmailed: 'InMailed', emailed: 'Emailed',
  connected: 'Connected', replied: 'Replied',
}
const STRONG = new Set(['replied', 'connected'])

type Filter = 'all' | 'replied' | 'awaiting' | 'connected'
const FILTERS: Array<{ key: Filter; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'replied', label: 'Replied' },
  { key: 'connected', label: 'Connected' },
  { key: 'awaiting', label: 'Awaiting reply' },
]

function since(iso: string | null): string {
  if (!iso) return ''
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000))
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.round(hrs / 24)}d ago`
}

function rowMatches(row: OutreachInboxRow, filter: Filter): boolean {
  if (filter === 'all') return true
  if (filter === 'replied') return row.replied
  const states = Object.values(row.channels).map((c) => c.state)
  if (filter === 'connected') return states.includes('connected')
  if (filter === 'awaiting') return !row.replied
  return true
}

export function OutreachScreen({ onOpen }: { onOpen: (searchId: string, candidateId: string) => void }) {
  const [rows, setRows] = useState<OutreachInboxRow[] | null>(null)
  const [counts, setCounts] = useState<{ total: number; replied: number }>({ total: 0, replied: 0 })
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<Filter>('all')
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getOutreachInbox()
      setRows(data.inbox)
      setCounts(data.counts)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load your outreach.')
      setRows([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const shown = useMemo(() => (rows ?? []).filter((r) => rowMatches(r, filter)), [rows, filter])

  return (
    <main className="outreach-screen">
      <header className="outreach-screen__head">
        <div>
          <h1 className="outreach-screen__title">Outreach</h1>
          <p className="outreach-screen__sub">
            {counts.total} contacted{counts.replied ? ` · ${counts.replied} replied` : ''}
          </p>
        </div>
        <button type="button" className="outreach-refresh" onClick={() => void load()} disabled={loading} title="Refresh">
          <RefreshCw size={15} aria-hidden="true" /> Refresh
        </button>
      </header>

      <div className="outreach-filters" role="group" aria-label="Filter outreach">
        {FILTERS.map((f) => (
          <button key={f.key} type="button" className={`outreach-filter${filter === f.key ? ' is-active' : ''}`} onClick={() => setFilter(f.key)}>
            {f.label}
          </button>
        ))}
      </div>

      {error ? <p className="outreach-error" role="alert">{error}</p> : null}

      {rows === null ? (
        <p className="outreach-muted">Loading…</p>
      ) : shown.length === 0 ? (
        <p className="outreach-muted">
          {counts.total === 0 ? "You haven't reached out to anyone yet. Open a candidate and use Reach out." : 'No one in this view.'}
        </p>
      ) : (
        <ul className="outreach-list">
          {shown.map((row) => (
            <li key={`${row.search_id}:${row.candidate_id}`} className={`outreach-row${row.replied ? ' is-replied' : ''}`}>
              <button type="button" className="outreach-row__main" onClick={() => onOpen(row.search_id, row.candidate_id)}>
                <span className="outreach-row__avatar" aria-hidden="true">{initialsOf(row.name)}</span>
                <span className="outreach-row__body">
                  <span className="outreach-row__name">{row.name}</span>
                  <span className="outreach-row__role">{row.role_title}</span>
                </span>
                <span className="outreach-row__states">
                  {Object.values(row.channels).map((c) => (
                    <span key={c.channel} className={`outreach-chip${STRONG.has(c.state) ? ' is-strong' : ''}`}>
                      {c.channel === 'email' ? <Mail size={11} aria-hidden="true" /> : <Briefcase size={11} aria-hidden="true" />}
                      {STATE_LABEL[c.state] ?? c.state}
                    </span>
                  ))}
                  {row.sequence && row.sequence.status === 'active' ? (
                    <span className="outreach-chip outreach-chip--seq"><MessageSquare size={11} aria-hidden="true" /> In sequence</span>
                  ) : null}
                </span>
                <span className="outreach-row__when">{since(row.last_activity)}</span>
              </button>
              {row.profile_url ? (
                <a className="outreach-row__link" href={row.profile_url} target="_blank" rel="noreferrer noopener" title="Open LinkedIn profile">
                  <ExternalLink size={14} aria-hidden="true" />
                </a>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </main>
  )
}
