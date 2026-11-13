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

export type OutreachSequence = { flow: string; status: string; enrolled_at?: string; steps?: Array<{ step: string; at: string }> }
/** What the recruiter should do next for an enrolled candidate (approve-each). */
export type SequenceDue =
  | { status: 'ready'; step: string; channel: string; inmail: boolean; label: string }
  | { status: 'waiting'; label: string }
  | { status: 'done' }
  | null

/** One row in the replies & outreach view — a candidate this recruiter contacted. */
export type OutreachInboxRow = {
  search_id: string
  candidate_id: string
  name: string
  profile_url: string | null
  role_title: string
  channels: Record<string, OutreachState>
  sequence?: OutreachSequence | null
  sequence_due?: SequenceDue
  last_activity: string | null
  replied: boolean
}

export async function enrollSequence(searchId: string, candidateId: string): Promise<{ sequence: OutreachSequence; due: SequenceDue }> {
  const res = await fetch(`${API_BASE_URL}/search/${encodeURIComponent(searchId)}/outreach/sequence/enroll`, {
    method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidate_id: candidateId }),
  })
  if (!res.ok) throw new Error(await detail(res, 'Could not start the sequence.'))
  return (await res.json()) as { sequence: OutreachSequence; due: SequenceDue }
}

export async function stopSequence(searchId: string, candidateId: string): Promise<{ sequence: OutreachSequence }> {
  const res = await fetch(`${API_BASE_URL}/search/${encodeURIComponent(searchId)}/outreach/sequence/stop`, {
    method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidate_id: candidateId }),
  })
  if (!res.ok) throw new Error(await detail(res, 'Could not stop the sequence.'))
  return (await res.json()) as { sequence: OutreachSequence }
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
): Promise<{ candidate_id: string; channel: string; outreach: OutreachState; sequence?: OutreachSequence | null; limits?: OutreachLimits }> {
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
  return (await res.json()) as { candidate_id: string; channel: string; outreach: OutreachState; sequence?: OutreachSequence | null; limits?: OutreachLimits }
}
