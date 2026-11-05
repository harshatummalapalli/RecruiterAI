// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RefinePanel } from './RefinePanel'
import type { IntakeResult } from '../models/intake'
import { createEmptySearchBoundary, type SearchBoundary } from '../models/searchBoundary'
import type { RefineDeltas } from '../services/recruiterWorkflow'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let root: Root
let container: HTMLElement

const $ = (selector: string) => container.querySelector(selector) as HTMLElement | null
const $$ = (selector: string) => Array.from(container.querySelectorAll(selector)) as HTMLElement[]
const click = (element: Element | null | undefined) =>
  act(() => {
    element!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
const button = (label: RegExp, within: ParentNode = container) =>
  Array.from(within.querySelectorAll('button')).find((b) => label.test(b.textContent ?? '')) as HTMLElement

function cap(value: string) {
  return { value, tier_signal: null, evidence: null }
}

function intake(): IntakeResult {
  return {
    raw_input: '',
    status: 'ready',
    role_understanding: {
      posted_title: 'AI Architect',
      posted_title_source: 'recruiter',
      primary_candidate_identity: { value: 'AI Architect', evidence: null, source: 'inferred' },
      hiring_company: { value: null, evidence: null, source: null },
      candidate_archetype: { value: null, evidence: null, source: null },
      role_interpretation: { value: 'Builds agentic systems.', evidence: null, source: 'inferred' },
      seniority_scope: { value: null, evidence: null, source: null },
      leadership_type: { value: null, evidence: null, source: null },
      core_capabilities: [cap('Agentic Systems')],
      supporting_capabilities: [cap('Python')],
      differentiators: [cap('MCP')],
      technologies_mentioned: [{ category: 'Frameworks', items: ['LangChain', 'Agentic Systems'] }],
      domain: [],
      explicit_constraints: {
        locations: [],
        work_mode: null,
        experience_minimum_years: 12,
        experience_maximum_years: null,
        employment_type: null,
        exclusions: [],
      },
      open_questions: [],
    },
    decision: {
      issues: [],
      recommended_ask_count: 0,
      stop_reasoning: null,
      warnings: [],
      search_consequence_summary: null,
      final_search_intent: {
        hard_requirements: [],
        strong_signals: [],
        preferred_differentiators: [],
        natural_language_search_query: null,
        exclusions: [],
      },
    },
  }
}

function boundary(): SearchBoundary {
  return { ...createEmptySearchBoundary(), country: 'India', work_mode: 'onsite', min_years: 12, city: 'Hyderabad' }
}

function mount(props: Partial<React.ComponentProps<typeof RefinePanel>> = {}) {
  const onApply = vi.fn()
  act(() => {
    root.render(
      <RefinePanel
        onClose={() => undefined}
        intakeResult={intake()}
        boundary={boundary()}
        outcome={null}
        busy={false}
        onApply={onApply}
        {...props}
      />,
    )
  })
  return { onApply }
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  vi.clearAllMocks()
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
})

describe('RefinePanel', () => {
  it('is a modal dialog with the pool-first promise and no vendor or mechanics wording', () => {
    mount()
    const dialog = $('[role="dialog"]')!
    expect(dialog).toBeTruthy()
    expect(container.textContent).toMatch(/free — no new search, no credits/i)
    expect(container.textContent).not.toMatch(/crustdata|harvest|pool|judge|page_size/i)
  })

  it('Apply stays disabled until something changes', () => {
    mount()
    expect(button(/Apply to profiles/)!.hasAttribute('disabled')).toBe(true)
  })

  it('sends only the structured deltas the recruiter changed', () => {
    const { onApply } = mount()
    // Promote the "Python" requirement from Supporting to Core.
    const row = $$('.refine-retier__row').find((r) => r.textContent?.includes('Python'))!
    click(button(/^Core$/, row))
    const apply = button(/Apply to profiles/)!
    expect(apply.hasAttribute('disabled')).toBe(false)
    click(apply)
    expect(onApply).toHaveBeenCalledTimes(1)
    const deltas = onApply.mock.calls[0][0] as RefineDeltas
    expect(deltas.retier).toEqual({ Python: 'core' })
    // Untouched fields are not sent.
    expect(deltas.min_years).toBeUndefined()
    expect(deltas.exclude_titles).toBeUndefined()
    // Bug #7: once applied, Apply re-disables until something changes again.
    expect(button(/Apply to profiles/)!.hasAttribute('disabled')).toBe(true)
  })

  it('add-a-must-have offers suggestions only — no free-text box — and emits a hard core requirement', () => {
    const { onApply } = mount()
    // The only way to add a requirement is a suggestion chip; the panel exposes no textarea.
    expect(container.querySelector('textarea')).toBeNull()
    const suggestion = button(/LangChain/)!
    expect(suggestion).toBeTruthy()
    click(suggestion)
    click(button(/Apply to profiles/)!)
    const deltas = onApply.mock.calls[0][0] as RefineDeltas
    expect(deltas.add_requirements).toEqual([{ text: 'LangChain', tier: 'core', hard: true }])
  })

  it('names reaching wider honestly (credits) when the read profiles are exhausted', () => {
    mount({ outcome: { refined: true, matched: 0, dropped: 3, shown: 5, exhausted: true } })
    expect($('.refine-outcome--exhausted')?.textContent).toMatch(/fresh\s+search, which uses credits/i)
  })
})
