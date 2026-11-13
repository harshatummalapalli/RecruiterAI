import { useEffect, useMemo, useState } from 'react'
import { Briefcase, Clock, CornerUpLeft, ExternalLink, Mail, RefreshCw, Send, Sparkles, Workflow } from 'lucide-react'
import { draftOutreach, getOutreachInbox, sendOutreach, type OutreachInboxRow, type OutreachState } from '../services/outreach'
import { initialsOf } from '../models/discovery'
import './OutreachScreen.css'

/** The channel a candidate replied on (with its reply text), if any. */
function repliedOn(row: OutreachInboxRow): OutreachState | null {
  return Object.values(row.channels).find((c) => c.state === 'replied') ?? null
}

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
  // Inline reply composer, keyed by "searchId:candidateId".
  const [replyKey, setReplyKey] = useState<string | null>(null)
  const [replyBody, setReplyBody] = useState('')
  const [replyDrafting, setReplyDrafting] = useState(false)
  const [replySending, setReplySending] = useState(false)
  const [replyError, setReplyError] = useState<string | null>(null)
  const [replied, setReplied] = useState<Set<string>>(new Set())

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

  const openReply = async (row: OutreachInboxRow) => {
    const rc = repliedOn(row)
    const channel = (rc?.channel === 'email' ? 'email' : 'linkedin') as 'linkedin' | 'email'
    setReplyKey(`${row.search_id}:${row.candidate_id}`)
    setReplyBody('')
    setReplyError(null)
    setReplyDrafting(true)
    try {
      const draft = await draftOutreach(row.search_id, row.candidate_id, channel, false, undefined, rc?.reply_preview)
      setReplyBody(draft.body ?? '')
    } catch (e) {
      setReplyError(e instanceof Error ? e.message : 'Could not draft a reply.')
    } finally {
      setReplyDrafting(false)
    }
  }

  const sendReply = async (row: OutreachInboxRow) => {
    if (!replyBody.trim()) return
    const rc = repliedOn(row)
    const channel = (rc?.channel === 'email' ? 'email' : 'linkedin') as 'linkedin' | 'email'
    setReplySending(true)
    setReplyError(null)
    try {
      await sendOutreach(row.search_id, { candidateId: row.candidate_id, channel, body: replyBody, inmail: false })
      setReplied((prev) => new Set(prev).add(`${row.search_id}:${row.candidate_id}`))
      setReplyKey(null)
    } catch (e) {
      setReplyError(e instanceof Error ? e.message : 'Could not send the reply.')
    } finally {
      setReplySending(false)
    }
  }

  return (
    <main className="outreach-screen">
      <header className="outreach-screen__head">
        <div>
          <h1 className="outreach-screen__title">Dialogue</h1>
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
          {shown.map((row) => {
            const key = `${row.search_id}:${row.candidate_id}`
            const rc = repliedOn(row)
            const didReply = replied.has(key)
            return (
              <li key={key} className={`outreach-row${row.replied ? ' is-replied' : ''}`}>
                <div className="outreach-row__top">
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
                      {row.sequence_due && row.sequence_due.status === 'ready' ? (
                        <span className="outreach-chip outreach-chip--ready"><Workflow size={11} aria-hidden="true" /> Next: {row.sequence_due.label}</span>
                      ) : row.sequence_due && row.sequence_due.status === 'waiting' ? (
                        <span className="outreach-chip outreach-chip--seq"><Clock size={11} aria-hidden="true" /> {row.sequence_due.label}</span>
                      ) : row.sequence && row.sequence.status === 'active' ? (
                        <span className="outreach-chip outreach-chip--seq"><Workflow size={11} aria-hidden="true" /> In sequence</span>
                      ) : null}
                    </span>
                    <span className="outreach-row__when">{since(row.last_activity)}</span>
                  </button>
                  {row.profile_url ? (
                    <a className="outreach-row__link" href={row.profile_url} target="_blank" rel="noreferrer noopener" title="Open LinkedIn profile">
                      <ExternalLink size={14} aria-hidden="true" />
                    </a>
                  ) : null}
                </div>

                {rc ? (
                  <div className="outreach-reply">
                    <p className={`outreach-reply__quote${rc.reply_preview ? '' : ' is-empty'}`}>
                      {rc.reply_preview ? `“${rc.reply_preview}”` : 'They replied — open the thread to read the full message.'}
                    </p>
                    {replyKey === key ? (
                      <div className="outreach-reply__composer">
                        <textarea className="outreach-reply__body" rows={4} value={replyBody} disabled={replyDrafting}
                          placeholder={replyDrafting ? 'Drafting a reply…' : 'Write your reply…'}
                          onChange={(e) => setReplyBody(e.target.value)} />
                        <div className="outreach-reply__foot">
                          {replyDrafting ? <span className="outreach-drafting"><Sparkles size={12} aria-hidden="true" /> Drafting…</span> : <span />}
                          <div className="outreach-reply__buttons">
                            <button type="button" className="outreach-filter" onClick={() => setReplyKey(null)} disabled={replySending}>Cancel</button>
                            <button type="button" className="outreach-reply__send" onClick={() => void sendReply(row)} disabled={replySending || replyDrafting || !replyBody.trim()}>
                              <Send size={13} aria-hidden="true" /> {replySending ? 'Sending…' : 'Send reply'}
                            </button>
                          </div>
                        </div>
                        {replyError ? <p className="outreach-error" role="alert">{replyError}</p> : null}
                      </div>
                    ) : didReply ? (
                      <p className="outreach-reply__done">Reply sent ✓</p>
                    ) : (
                      <button type="button" className="outreach-reply__start" onClick={() => void openReply(row)}>
                        <CornerUpLeft size={13} aria-hidden="true" /> Reply
                      </button>
                    )}
                  </div>
                ) : null}
              </li>
            )
          })}
        </ul>
      )}
    </main>
  )
}
