import { API_BASE_URL } from './recruiterWorkflow'

export type OutreachChannel = 'linkedin' | 'email'

/** An AI draft the recruiter reviews/edits before sending. `char_limit` is set
 * for a LinkedIn connection note (the ~200-char cap), null otherwise. */
export type OutreachDraft = {
  channel: string
  subject: string
  body: string
  inmail: boolean
  char_limit: number | null
}

/** Per-channel outreach state persisted on the search record. */
export type OutreachState = {
  channel: string
  state: string // "invited" | "messaged" | "inmailed" | "emailed" | "replied" | "connected"
  kind?: string
  subject?: string
  at?: string
}

/** Rolling-24h send caps, keyed by action category
 * ("linkedin_invite" | "linkedin_message" | "email"). */
export type OutreachLimits = Record<string, { used: number; limit: number; remaining: number }>

/** One row in the replies & outreach view — a candidate this recruiter contacted. */
export type OutreachInboxRow = {
  search_id: string
  candidate_id: string
  name: string
  profile_url: string | null
  role_title: string
  channels: Record<string, OutreachState>
  sequence?: { flow: string; status: string; current_step?: number } | null
  last_activity: string | null
  replied: boolean
}

export async function getOutreachInbox(): Promise<{ inbox: OutreachInboxRow[]; counts: { total: number; replied: number } }> {
  const res = await fetch(`${API_BASE_URL}/integrations/outreach/inbox`, { credentials: 'include' })
  if (!res.ok) throw new Error('Could not load your outreach.')
  return (await res.json()) as { inbox: OutreachInboxRow[]; counts: { total: number; replied: number } }
}

export async function getOutreachLimits(): Promise<OutreachLimits> {
  const res = await fetch(`${API_BASE_URL}/integrations/outreach/limits`, { credentials: 'include' })
  if (!res.ok) throw new Error('Could not load your sending limits.')
  const data = (await res.json()) as { limits?: OutreachLimits }
  return data.limits ?? {}
}

async function detail(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => null)
  return (body && body.detail) || fallback
}

export type OutreachTone = 'warm' | 'direct'

export async function draftOutreach(
  searchId: string,
  candidateId: string,
  channel: OutreachChannel,
  inmail = false,
  tone?: OutreachTone,
): Promise<OutreachDraft> {
  const res = await fetch(`${API_BASE_URL}/search/${encodeURIComponent(searchId)}/outreach/draft`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidate_id: candidateId, channel, inmail, tone }),
  })
  if (!res.ok) throw new Error(await detail(res, 'Could not draft a message.'))
  return (await res.json()) as OutreachDraft
}

export async function sendOutreach(
  searchId: string,
  args: { candidateId: string; channel: OutreachChannel; body: string; subject?: string; inmail?: boolean },
): Promise<{ candidate_id: string; channel: string; outreach: OutreachState; limits?: OutreachLimits }> {
  const res = await fetch(`${API_BASE_URL}/search/${encodeURIComponent(searchId)}/outreach/send`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      candidate_id: args.candidateId,
      channel: args.channel,
      body: args.body,
      subject: args.subject,
      inmail: args.inmail ?? false,
    }),
  })
  if (!res.ok) throw new Error(await detail(res, 'Could not send that message.'))
  return (await res.json()) as { candidate_id: string; channel: string; outreach: OutreachState; limits?: OutreachLimits }
}
