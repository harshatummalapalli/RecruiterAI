import { useEffect, useMemo, useState } from 'react'
import { Briefcase, Mail, Send, Sparkles } from 'lucide-react'
import { listIntegrations } from '../services/integrations'
import { draftOutreach, sendOutreach, type OutreachChannel, type OutreachState } from '../services/outreach'
import './CandidateOutreach.css'

type Composer = { channel: OutreachChannel; inmail: boolean }

type Props = {
  searchId: string | null
  candidateId: string
  name: string
  profileUrl: string | null
  email: string | null
  /** Outreach already recorded for this candidate (by channel), to rehydrate the chips on open. */
  initial?: Record<string, OutreachState> | null
}

const STATE_LABEL: Record<string, string> = {
  invited: 'Invitation sent',
  messaged: 'Message sent',
  inmailed: 'InMail sent',
  emailed: 'Email sent',
}

function actionLabel(c: Composer): string {
  if (c.channel === 'email') return 'Email'
  return c.inmail ? 'InMail' : 'Connect'
}

export function CandidateOutreach({ searchId, candidateId, name, profileUrl, email, initial }: Props) {
  const [connected, setConnected] = useState<Set<string> | null>(null)
  const [sent, setSent] = useState<Record<string, OutreachState>>(initial ?? {})
  const [composer, setComposer] = useState<Composer | null>(null)
  const [drafting, setDrafting] = useState(false)
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [charLimit, setCharLimit] = useState<number | null>(null)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Fresh candidate -> reset everything (the record pane reuses this component as you page through).
  useEffect(() => {
    setSent(initial ?? {})
    setComposer(null)
    setError(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidateId])

  useEffect(() => {
    let alive = true
    listIntegrations()
      .then((items) => { if (alive) setConnected(new Set(items.filter((i) => i.connected).map((i) => i.channel))) })
      .catch(() => { if (alive) setConnected(new Set()) })
    return () => { alive = false }
  }, [])

  const hasLinkedIn = connected?.has('linkedin') && Boolean(profileUrl)
  const hasEmail = connected?.has('email') && Boolean(email)
  const overLimit = charLimit != null && body.length > charLimit

  const openComposer = async (next: Composer) => {
    setComposer(next)
    setError(null)
    setSubject('')
    setBody('')
    setCharLimit(null)
    if (!searchId) return
    setDrafting(true)
    try {
      const draft = await draftOutreach(searchId, candidateId, next.channel, next.inmail)
      setSubject(draft.subject ?? '')
      setBody(draft.body ?? '')
      setCharLimit(draft.char_limit)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not draft a message.')
    } finally {
      setDrafting(false)
    }
  }

  const send = async () => {
    if (!searchId || !composer || !body.trim() || overLimit) return
    setSending(true)
    setError(null)
    try {
      const res = await sendOutreach(searchId, {
        candidateId, channel: composer.channel, body, subject: subject || undefined, inmail: composer.inmail,
      })
      setSent((prev) => ({ ...prev, [res.channel]: res.outreach }))
      setComposer(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not send that message.')
    } finally {
      setSending(false)
    }
  }

  const chips = useMemo(() => Object.values(sent), [sent])

  if (!searchId) return null

  return (
    <section className="record-section co" aria-labelledby="record-outreach">
      <h3 id="record-outreach" className="record-section__title">Reach out</h3>

      {chips.length ? (
        <div className="co-status">
          {chips.map((s) => (
            <span key={s.channel} className="co-chip" title={s.at ? new Date(s.at).toLocaleString() : undefined}>
              {s.channel === 'email' ? <Mail size={12} aria-hidden="true" /> : <Briefcase size={12} aria-hidden="true" />}
              {STATE_LABEL[s.state] ?? s.state}
            </span>
          ))}
        </div>
      ) : null}

      {connected === null ? (
        <p className="record-muted">Loading your connected accounts…</p>
      ) : !hasLinkedIn && !hasEmail ? (
        <p className="record-muted">
          {connected.size === 0
            ? 'Connect your LinkedIn or email in Settings → Integrations to reach out.'
            : 'No reachable LinkedIn link or email address on this candidate.'}
        </p>
      ) : (
        <div className="co-actions">
          {hasLinkedIn ? (
            <>
              <button type="button" className="co-btn" onClick={() => void openComposer({ channel: 'linkedin', inmail: false })}>
                <Briefcase size={14} aria-hidden="true" /> Connect
              </button>
              <button type="button" className="co-btn co-btn--ghost" onClick={() => void openComposer({ channel: 'linkedin', inmail: true })}>
                InMail
              </button>
            </>
          ) : null}
          {hasEmail ? (
            <button type="button" className="co-btn" onClick={() => void openComposer({ channel: 'email', inmail: false })}>
              <Mail size={14} aria-hidden="true" /> Email
            </button>
          ) : null}
        </div>
      )}

      {composer ? (
        <div className="co-composer">
          <div className="co-composer__head">
            <span className="co-composer__title">
              {actionLabel(composer)} to {name.split(' ')[0] || name}
            </span>
            {drafting ? <span className="co-drafting"><Sparkles size={12} aria-hidden="true" /> Drafting…</span> : null}
          </div>

          {(composer.channel === 'email' || composer.inmail) ? (
            <input
              className="co-subject"
              placeholder="Subject"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              disabled={drafting}
            />
          ) : null}

          <textarea
            className="co-body"
            rows={composer.channel === 'linkedin' && !composer.inmail ? 3 : 6}
            placeholder={drafting ? 'Drafting from this candidate’s evidence…' : 'Write your message…'}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            disabled={drafting}
          />

          <div className="co-composer__foot">
            {charLimit != null ? (
              <span className={`co-count${overLimit ? ' is-over' : ''}`}>{body.length}/{charLimit}</span>
            ) : <span />}
            <div className="co-composer__buttons">
              <button type="button" className="co-btn co-btn--ghost" onClick={() => setComposer(null)} disabled={sending}>Cancel</button>
              <button type="button" className="co-btn" onClick={() => void send()} disabled={sending || drafting || !body.trim() || overLimit}>
                <Send size={13} aria-hidden="true" /> {sending ? 'Sending…' : `Send ${actionLabel(composer).toLowerCase()}`}
              </button>
            </div>
          </div>
          {error ? <p className="co-error" role="alert">{error}</p> : null}
        </div>
      ) : null}
    </section>
  )
}
