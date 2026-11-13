// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../services/integrations', () => ({
  listIntegrations: vi.fn(),
  connectIntegration: vi.fn(),
  disconnectIntegration: vi.fn(),
}))

import { connectIntegration, disconnectIntegration, listIntegrations } from '../services/integrations'
import { IntegrationsSection } from './IntegrationsSection'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let root: Root
let container: HTMLElement

const $$ = (sel: string) => Array.from(container.querySelectorAll(sel)) as HTMLElement[]
const rowFor = (label: string) =>
  $$('.integration-row').find((r) => r.querySelector('.integration-row__name')?.textContent?.includes(label))!
const btn = (within: ParentNode) => within.querySelector('.integration-btn') as HTMLButtonElement

const flush = () => act(async () => { await Promise.resolve(); await Promise.resolve() })

async function render() {
  await act(async () => { root.render(<IntegrationsSection />) })
  await flush()
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  vi.mocked(listIntegrations).mockResolvedValue([
    { channel: 'linkedin', connected: false },
    { channel: 'email', connected: false },
    { channel: 'whatsapp', connected: false },
  ])
  vi.mocked(connectIntegration).mockResolvedValue('https://connect.dayzero.partners/hosted/abc')
  vi.mocked(disconnectIntegration).mockResolvedValue()
  vi.stubGlobal('open', vi.fn(() => ({}) as Window))
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe('IntegrationsSection', () => {
  it('lists the three channels; WhatsApp is coming soon and disabled', async () => {
    await render()
    const names = $$('.integration-row__name').map((n) => n.textContent)
    expect(names.some((n) => n?.includes('LinkedIn'))).toBe(true)
    expect(names.some((n) => n?.includes('Email'))).toBe(true)
    const wa = rowFor('WhatsApp')
    expect(wa.querySelector('.integration-row__soon')?.textContent).toMatch(/coming soon/i)
    expect(btn(wa).disabled).toBe(true)
  })

  it('Connect starts the flow and opens the (white-label) link', async () => {
    await render()
    await act(async () => { btn(rowFor('LinkedIn')).dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await flush()
    expect(connectIntegration).toHaveBeenCalledWith('linkedin')
    expect(window.open).toHaveBeenCalledWith('https://connect.dayzero.partners/hosted/abc', '_blank', expect.any(String))
  })

  it('a connected channel shows Disconnect and calls it', async () => {
    vi.mocked(listIntegrations).mockResolvedValue([
      { channel: 'linkedin', connected: true, display_name: 'Alice R', status: 'running' },
      { channel: 'email', connected: false },
      { channel: 'whatsapp', connected: false },
    ])
    await render()
    const li = rowFor('LinkedIn')
    expect(li.querySelector('.integration-row__meta')?.textContent).toMatch(/Connected.*Alice R/)
    expect(btn(li).textContent).toMatch(/Disconnect/)
    await act(async () => { btn(li).dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await flush()
    expect(disconnectIntegration).toHaveBeenCalledWith('linkedin')
  })
})
