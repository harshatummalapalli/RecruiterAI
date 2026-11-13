import { API_BASE_URL } from './recruiterWorkflow'

export type IntegrationChannel = 'linkedin' | 'email' | 'whatsapp'

export type Integration = {
  channel: IntegrationChannel
  connected: boolean
  status?: string | null
  display_name?: string | null
  raw_provider?: string | null
  connected_at?: string | null
}

export async function listIntegrations(): Promise<Integration[]> {
  const res = await fetch(`${API_BASE_URL}/integrations`, { credentials: 'include' })
  if (!res.ok) throw new Error('Could not load your connected accounts.')
  const data = (await res.json()) as { integrations?: Integration[] }
  return data.integrations ?? []
}

/** Starts a connect flow and returns the hosted-auth link to open. The link is
 * served on our own domain (white-label) — no vendor is shown to the recruiter. */
export async function connectIntegration(channel: IntegrationChannel): Promise<string> {
  const res = await fetch(`${API_BASE_URL}/integrations/connect`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ channel }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error((body && body.detail) || 'Could not start the connection. Please try again.')
  }
  const data = (await res.json()) as { link: string }
  return data.link
}

export async function disconnectIntegration(channel: IntegrationChannel): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/integrations/disconnect`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ channel }),
  })
  if (!res.ok) throw new Error('Could not disconnect that account.')
}
