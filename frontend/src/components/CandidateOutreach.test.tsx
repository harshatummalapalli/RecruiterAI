// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../services/integrations', () => ({ listIntegrations: vi.fn() }))
vi.mock('../services/outreach', () => ({ draftOutreach: vi.fn(), sendOutreach: vi.fn() }))

import { listIntegrations } from '../services/integrations'
import { draftOutreach, sendOutreach } from '../services/outreach'
import { CandidateOutreach } from './CandidateOutreach'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let root: Root
let container: HTMLElement

const $ = (sel: string) => container.querySelector(sel) as HTMLElement | null
const $$ = (sel: string) => Array.from(container.querySelectorAll(sel)) as HTMLElement[]
const btnByText = (text: string) => $$('.co-btn').find((b) => b.textContent?.includes(text))!
const flush = () => act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve() })

async function render(props: Partial<Parameters<typeof CandidateOutreach>[0]> = {}) {
  await act(async () => {
    root.render(
      <CandidateOutreach
        searchId="s1"
        candidateId="c1"
        name="Jane Doe"
        profileUrl="https://linkedin.com/in/jane"
        email="jane@acme.com"
        initial={null}
        {...props}
      />,
    )
  })
  await flush()
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  vi.mocked(listIntegrations).mockResolvedValue([
    { channel: 'linkedin', connected: true },
    { channel: 'email', connected: false },
    { channel: 'whatsapp', connected: false },
  ])
  vi.mocked(draftOutreach).mockResolvedValue({ channel: 'linkedin', subject: '', body: 'Hi Jane, loved your work.', inmail: false, char_limit: 200 })
  vi.mocked(sendOutreach).mockResolvedValue({ candidate_id: 'c1', channel: 'linkedin', outreach: { channel: 'linkedin', state: 'invited' } })
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  vi.clearAllMocks()
})

describe('CandidateOutreach', () => {
  it('shows only the connected + reachable channels (LinkedIn here, not Email)', async () => {
    await render()
    expect(btnByText('Connect')).toBeTruthy()
    expect($$('.co-btn').some((b) => b.textContent?.includes('InMail'))).toBe(true)
    expect($$('.co-btn').some((b) => b.textContent?.includes('Email'))).toBe(false)
  })

  it('drafts then sends, and shows the resulting state chip', async () => {
    await render()
    await act(async () => { btnByText('Connect').dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await flush()
    expect(draftOutreach).toHaveBeenCalledWith('s1', 'c1', 'linkedin', false)
    expect(($('.co-body') as HTMLTextAreaElement).value).toBe('Hi Jane, loved your work.')

    await act(async () => { btnByText('Send connect').dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await flush()
    expect(sendOutreach).toHaveBeenCalledWith('s1', expect.objectContaining({ candidateId: 'c1', channel: 'linkedin', inmail: false }))
    expect($('.co-chip')?.textContent).toMatch(/Invitation sent/)
  })

  it('hints to connect an account when none are connected', async () => {
    vi.mocked(listIntegrations).mockResolvedValue([
      { channel: 'linkedin', connected: false },
      { channel: 'email', connected: false },
    ])
    await render()
    expect($('.record-muted')?.textContent).toMatch(/Settings/)
    expect($$('.co-btn').length).toBe(0)
  })

  it('rehydrates an existing outreach chip from the initial prop', async () => {
    await render({ initial: { email: { channel: 'email', state: 'emailed' } } })
    expect($('.co-chip')?.textContent).toMatch(/Email sent/)
  })
})
