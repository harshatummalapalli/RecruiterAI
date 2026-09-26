import { describe, expect, it } from 'vitest'
import type { ConfirmedChange } from './intake'
import { HYBRID_TORONTO, REMOTE_CANADA, CONTRADICTION_QUESTION, EXPERIENCE_QUESTION, TITLE_NOTE, makeBrief, makeIntakeResult } from './livingBriefFixtures'
import {
  confirmationSummary,
  diffBriefEdits,
  experienceView,
  fieldProvenance,
  formatBoundaryLocation,
  readyStatus,
  recruiterNotes,
  requirementGroups,
  titleView,
} from './livingBrief'
import { createEmptySearchBoundary } from './searchBoundary'

describe('requirements and their provenance', () => {
  it('lists Core, Supporting, Preferred in that order, using the same words as the workspace', () => {
    expect(requirementGroups(makeIntakeResult()).map((group) => group.label)).toEqual(['Core', 'Supporting', 'Preferred'])
  })

  it('says "stated" only where the server found the requirement in the input, and "inferred" everywhere else', () => {
    const [core, supporting, preferred] = requirementGroups(makeIntakeResult())
    expect(core.items.map((item) => [item.text, item.provenance])).toEqual([
      ['Python backend services', 'stated'],
      ['Event-driven systems', 'stated'],
      ['PostgreSQL', 'inferred'], // no matching sentence in the evidence map
    ])
    expect(supporting.items.every((item) => item.provenance === 'inferred')).toBe(true)
    expect(preferred.items.find((item) => item.text === 'Snowflake')?.provenance).toBe('stated')
    expect(core.items[0].evidence).toBe('Strong Python.')
  })

  it('marks a requirement the recruiter changed by answering as confirmed, and only that one', () => {
    const result = makeIntakeResult()
    const change: ConfirmedChange = { field: 'requirement', description: 'Kafka: now preferred', item: 'Kafka', issue: 'Kafka level', answer: 'Nice-to-have' }
    result.confirmed = [change]
    result.decision.final_search_intent.strong_signals = ['FastAPI']
    result.decision.final_search_intent.preferred_differentiators = ['Snowflake', 'Kafka']
    const [, , preferred] = requirementGroups(result)
    expect(preferred.items.map((item) => [item.text, item.provenance])).toEqual([
      ['Snowflake', 'stated'],
      ['Kafka', 'confirmed'],
    ])
  })

  it('has no evidence map on an older session and simply calls everything inferred', () => {
    const result = makeIntakeResult()
    delete result.decision.final_search_intent.evidence
    expect(requirementGroups(result)[0].items.every((item) => item.provenance === 'inferred')).toBe(true)
  })
})

describe('fields and their provenance', () => {
  it('maps the source of a value to what the recruiter needs to know', () => {
    expect(fieldProvenance({ value: 'Senior', evidence: null, source: 'explicit' })).toBe('stated')
    expect(fieldProvenance({ value: 'Senior', evidence: null, source: 'inferred' })).toBe('inferred')
    expect(fieldProvenance({ value: 'Senior', evidence: null, source: 'recruiter' })).toBe('confirmed')
    expect(fieldProvenance({ value: null, evidence: null, source: 'explicit' })).toBeNull()
  })

  it('shows experience as stated until the recruiter answers a question about it', () => {
    const result = makeIntakeResult()
    expect(experienceView(result)).toEqual({ text: '8–10 years', provenance: 'stated' })
    result.confirmed = [{ field: 'experience', description: 'Experience: 8-10 years', item: null, issue: 'x', answer: 'y' }]
    expect(experienceView(result)?.provenance).toBe('confirmed')
  })
})

describe('posted title and candidate identity stay separate', () => {
  it('keeps the posted title and shows the identity only when it materially differs', () => {
    const view = titleView(makeIntakeResult())
    expect(view.posted).toBe('AI Engineer')
    expect(view.postedNote).toBe('As you wrote it')
    expect(view.identity).toBe('Backend-heavy AI Engineer')
    expect(view.identityDiffers).toBe(true)
    expect(view.identityReason).toContain('70% of your time is backend engineering')
  })

  it('does not show a second title when the identity is the posted title in other words', () => {
    const result = makeIntakeResult()
    result.role_understanding.primary_candidate_identity.value = 'ai engineer'
    expect(titleView(result).identityDiffers).toBe(false)
  })

  it('says where a title read from the description came from, and never invents one', () => {
    const result = makeIntakeResult()
    result.role_understanding.posted_title_source = 'jd'
    expect(titleView(result).postedNote).toBe('As written in the JD')
    result.role_understanding.posted_title = null
    result.role_understanding.posted_title_source = null
    const view = titleView(result)
    expect(view.posted).toBeNull()
    expect(view.postedNote).toBeNull()
    expect(view.identity).toBe('Backend-heavy AI Engineer')
  })
})

describe('what makes a brief ready', () => {
  it('is ready with a valid boundary and nothing left to ask', () => {
    expect(readyStatus(makeIntakeResult(), HYBRID_TORONTO)).toEqual({ state: 'ready', blockers: [], questions: [] })
  })

  it('is a draft, with the reason, while a question is open', () => {
    const status = readyStatus(makeIntakeResult({ issues: [EXPERIENCE_QUESTION, TITLE_NOTE] }), HYBRID_TORONTO)
    expect(status.state).toBe('draft')
    expect(status.blockers).toEqual(['1 decision still needs your answer.'])
    expect(status.questions.map((q) => q.issue)).toEqual(['Conflicting experience ranges'])
  })

  it('counts every open question of any origin, contradictions included', () => {
    const status = readyStatus(makeIntakeResult({ issues: [CONTRADICTION_QUESTION, EXPERIENCE_QUESTION] }), HYBRID_TORONTO)
    expect(status.blockers[0]).toBe('2 decisions still need your answer.')
  })

  it('is a draft when the boundary is incomplete, with no default work mode to hide behind', () => {
    const status = readyStatus(makeIntakeResult(), createEmptySearchBoundary())
    expect(status.state).toBe('draft')
    expect(status.blockers).toContain('The search boundary is incomplete.')
    expect(createEmptySearchBoundary().work_mode).toBe('')
  })

  it('is not blocked by zero core requirements, warnings, or notes', () => {
    const result = makeIntakeResult({ core: [], warnings: ['Something to be aware of.'] })
    expect(readyStatus(result, HYBRID_TORONTO).state).toBe('ready')
  })

  it('is a draft before there is any reading at all', () => {
    expect(readyStatus(null, HYBRID_TORONTO).state).toBe('draft')
  })
})

describe('notes', () => {
  it('shows only TELLs that carry text', () => {
    const result = makeIntakeResult({ issues: [TITLE_NOTE, { ...TITLE_NOTE, id: 'x', insight_text: null }] })
    expect(recruiterNotes(result)).toEqual([TITLE_NOTE.insight_text])
  })
})

describe('edits: only real changes, never the boundary', () => {
  it('sends nothing for an unedited brief', () => {
    expect(diffBriefEdits(makeBrief(), makeBrief())).toEqual({})
  })

  it('sends just the fields that changed', () => {
    const current = makeBrief()
    current.role.seniority = 'Staff'
    current.role.excludedTitles = ['Intern']
    current.experience.minimumYears = '6'
    current.requirements = { core: ['Python backend services'], supporting: current.requirements!.supporting, differentiators: current.requirements!.differentiators }
    current.companies.exclude = []
    expect(diffBriefEdits(makeBrief(), current)).toEqual({
      seniority: 'Staff',
      exclude_titles: ['Intern'],
      minimum_years: 6,
      core_signals: ['Python backend services'],
      exclude_current_companies: [],
    })
  })

  it('clears an experience bound with null and never sends an empty identity', () => {
    const current = makeBrief()
    current.experience.maximumYears = ''
    current.role.primaryTitle = '   '
    expect(diffBriefEdits(makeBrief(), current)).toEqual({ maximum_years: null })
  })

  it('has no way to express location, work mode or hiring company', () => {
    const current = makeBrief()
    current.location.country = 'France'
    current.location.workModes = ['remote']
    expect(diffBriefEdits(makeBrief(), current)).toEqual({})
  })
})

describe('confirmation summary and boundary wording', () => {
  it('states what will be searched in the recruiter\'s terms, without any search machinery', () => {
    const lines = confirmationSummary(makeIntakeResult(), HYBRID_TORONTO, makeBrief())
    expect(lines.map((line) => line.label)).toEqual(['Looking for', 'Experience', 'Where', 'Requirements', 'Not from'])
    expect(lines.find((line) => line.label === 'Where')?.value).toBe('Toronto, Ontario, Canada · 25 mi radius · Hybrid')
    expect(lines.find((line) => line.label === 'Requirements')?.value).toBe('3 core · 2 supporting · 2 preferred')
    expect(JSON.stringify(lines)).not.toMatch(/crustdata|provider|boolean|query|filter/i)
  })

  it('formats every kind of boundary', () => {
    expect(formatBoundaryLocation(REMOTE_CANADA)).toBe('Anywhere in Canada')
    expect(formatBoundaryLocation({ ...REMOTE_CANADA, remote_scope: 'states', remote_states: ['Ontario', 'Quebec'] })).toBe('Ontario, Quebec, Canada')
    expect(formatBoundaryLocation({ ...REMOTE_CANADA, remote_scope: 'cities', remote_cities: ['Toronto'] })).toBe('Toronto, Canada')
  })
})
