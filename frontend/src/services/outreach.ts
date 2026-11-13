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
  state: string // "invited" | "messaged" | "inmailed" | "emailed"
  kind?: string
  subject?: string
  at?: string
}

async function detail(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => null)
  return (body && body.detail) || fallback
}

export async function draftOutreach(
  searchId: string,
  candidateId: string,
  channel: OutreachChannel,
  inmail = false,
): Promise<OutreachDraft> {
  const res = await fetch(`${API_BASE_URL}/search/${encodeURIComponent(searchId)}/outreach/draft`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidate_id: candidateId, channel, inmail }),
  })
  if (!res.ok) throw new Error(await detail(res, 'Could not draft a message.'))
  return (await res.json()) as OutreachDraft
}

export async function sendOutreach(
  searchId: string,
  args: { candidateId: string; channel: OutreachChannel; body: string; subject?: string; inmail?: boolean },
): Promise<{ candidate_id: string; channel: string; outreach: OutreachState }> {
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
  return (await res.json()) as { candidate_id: string; channel: string; outreach: OutreachState }
}
