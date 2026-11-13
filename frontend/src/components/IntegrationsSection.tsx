import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Briefcase, Mail, MessageCircle } from 'lucide-react'
import {
  connectIntegration,
  disconnectIntegration,
  listIntegrations,
  type Integration,
  type IntegrationChannel,
} from '../services/integrations'

type ChannelMeta = {
  channel: IntegrationChannel
  label: string
  blurb: string
  icon: typeof Mail
  available: boolean
}

// LinkedIn + Email are live; WhatsApp is modelled end-to-end but surfaced as
// "coming soon" until we turn it on.
const CHANNELS: ChannelMeta[] = [
  { channel: 'linkedin', label: 'LinkedIn', blurb: 'Send connection requests and messages from your LinkedIn.', icon: Briefcase, available: true },
  { channel: 'email', label: 'Email', blurb: 'Send and track emails from your Gmail or Outlook.', icon: Mail, available: true },
  { channel: 'whatsapp', label: 'WhatsApp', blurb: 'Message candidates on WhatsApp.', icon: MessageCircle, available: false },
]

function statusNote(it: Integration): string {
  const name = it.display_name ? ` · ${it.display_name}` : ''
  if (it.status && it.status !== 'running') return `Needs reconnecting${name}`
  return `Connected${name}`
}

export function IntegrationsSection() {
  const [items, setItems] = useState<Integration[]>([])
  const [busy, setBusy] = useState<IntegrationChannel | null>(null)
  const [error, setError] = useState<string | null>(null)
  const popupRef = useRef<Window | null>(null)

  const byChannel = useMemo(() => {
    const map: Partial<Record<IntegrationChannel, Integration>> = {}
    for (const it of items) map[it.channel] = it
    return map
  }, [items])

  const refresh = useCallback(async () => {
    try {
      setItems(await listIntegrations())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load your connected accounts.')
    }
  }, [])

  useEffect(() => { void refresh() }, [refresh])

  // The connect page (on our own domain) posts back when it finishes, and the
  // recruiter returning focus to this tab is the fallback — both just re-fetch.
  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.data && (event.data as { type?: string }).type === 'recruiterai:integration') {
        setBusy(null)
        void refresh()
      }
    }
    const onFocus = () => { if (busy) void refresh() }
    window.addEventListener('message', onMessage)
    window.addEventListener('focus', onFocus)
    return () => {
      window.removeEventListener('message', onMessage)
      window.removeEventListener('focus', onFocus)
    }
  }, [busy, refresh])

  const connect = async (channel: IntegrationChannel) => {
    setError(null)
    setBusy(channel)
    try {
      const link = await connectIntegration(channel)
      // Open our white-label connect page. Not `noopener` — the page posts back
      // to this window when it's done so the list refreshes automatically.
      popupRef.current = window.open(link, '_blank', 'width=520,height=720')
      if (!popupRef.current) {
        setBusy(null)
        setError('Allow pop-ups for this site, then try Connect again.')
      }
    } catch (e) {
      setBusy(null)
      setError(e instanceof Error ? e.message : 'Could not start the connection.')
    }
  }

  const disconnect = async (channel: IntegrationChannel) => {
    setError(null)
    setBusy(channel)
    try {
      await disconnectIntegration(channel)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not disconnect that account.')
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="settings__section" aria-labelledby="settings-integrations">
      <h2 id="settings-integrations" className="settings__section-title">Integrations</h2>
      <p className="settings__hint">
        Connect your own accounts to reach out to candidates. These are yours alone — no one else can see or use them.
      </p>
      {error ? <p className="integration-error" role="alert">{error}</p> : null}
      <div className="integration-list">
        {CHANNELS.map((meta) => {
          const it = byChannel[meta.channel]
          const connected = Boolean(it?.connected)
          const Icon = meta.icon
          const working = busy === meta.channel
          return (
            <div key={meta.channel} className={`integration-row${connected ? ' is-connected' : ''}`}>
              <span className="integration-row__icon" aria-hidden="true"><Icon size={18} /></span>
              <div className="integration-row__body">
                <div className="integration-row__name">
                  {meta.label}
                  {!meta.available ? <span className="integration-row__soon">Coming soon</span> : null}
                </div>
                <div className="integration-row__meta">{connected && it ? statusNote(it) : meta.blurb}</div>
              </div>
              <div className="integration-row__action">
                {!meta.available ? (
                  <button type="button" className="integration-btn" disabled>Soon</button>
                ) : connected ? (
                  <button type="button" className="integration-btn integration-btn--ghost" onClick={() => void disconnect(meta.channel)} disabled={working}>
                    {working ? '…' : 'Disconnect'}
                  </button>
                ) : (
                  <button type="button" className="integration-btn" onClick={() => void connect(meta.channel)} disabled={working}>
                    {working ? 'Connecting…' : 'Connect'}
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
