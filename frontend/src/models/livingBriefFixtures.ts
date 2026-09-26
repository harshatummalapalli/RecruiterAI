// Realistic intake results for tests and the local preview. The role is the worked example from the Release 4 spec:
// posted title "AI Engineer", backend-dominant work, an experience range that conflicts inside the JD.
import type { IntakeIssue, IntakeResult } from './intake'
import type { SearchBoundary } from './searchBoundary'
import { createEmptySearchBrief, type SearchBrief } from './searchBrief'

export const RAW_INPUT = `AI Engineer
Northwind Payments builds fraud detection and dispute resolution for card issuers.
About 70% of your time is backend engineering (Python, FastAPI, Kafka, PostgreSQL) and about 30% is applying ML and LLMs to fraud detection.
We are looking for an engineer with 3+ years of experience. Requirements: 8-10 years of professional software engineering experience. Strong Python. Experience with event-driven systems.
Nice to have: Snowflake, dbt.`

export const HYBRID_TORONTO: SearchBoundary = {
  hiring_company: 'Northwind Payments',
  country: 'Canada',
  work_mode: 'hybrid',
  state: 'Ontario',
  city: 'Toronto',
  radius_miles: 25,
  remote_scope: null,
  remote_states: [],
  remote_cities: [],
}

export const REMOTE_CANADA: SearchBoundary = {
  ...HYBRID_TORONTO,
  work_mode: 'remote',
  state: null,
  city: null,
  radius_miles: null,
  remote_scope: 'anywhere',
}

export const EXPERIENCE_QUESTION: IntakeIssue = {
  issue: 'Conflicting experience ranges',
  decision: 'ask',
  id: 'issue-0',
  reasoning: 'The description states two different ranges.',
  question: 'The description states 3+ years and also 8-10 years. Which range is correct?',
  options: [
    { value: '3plus', label: '3+ years' },
    { value: '8to10', label: '8-10 years' },
  ],
  consequence_if_answer_a: 'Sets the experience filter to 3+ years.',
  consequence_if_answer_b: 'Sets the experience filter to 8-10 years.',
  insight_text: null,
  injected_by_backstop: false,
  backstop_category: null,
}

export const CONTRADICTION_QUESTION: IntakeIssue = {
  issue: 'Contradiction: experience seniority',
  decision: 'ask',
  id: 'backstop-experience_seniority',
  reasoning: null,
  question: 'This role states both an entry-level/junior signal and a senior-level or high-experience requirement. Which is correct?',
  options: [
    { value: 'as_junior_senior_dropped', label: 'Treat as entry-level (drop the years requirement)' },
    { value: 'as_stated_years', label: 'Treat as senior (keep the stated years requirement)' },
  ],
  consequence_if_answer_a: 'Resolves toward entry level.',
  consequence_if_answer_b: 'Resolves toward senior.',
  insight_text: null,
  injected_by_backstop: true,
  backstop_category: 'experience_seniority',
}

export const TITLE_NOTE: IntakeIssue = {
  issue: 'Title versus work',
  decision: 'tell',
  id: 'issue-1',
  reasoning: 'The work is clear.',
  question: null,
  options: [],
  consequence_if_answer_a: null,
  consequence_if_answer_b: null,
  insight_text: "Even though the title says AI Engineer, about 70% of the work is backend engineering, so backend titles are searched too.",
  injected_by_backstop: false,
  backstop_category: null,
}

export function makeIntakeResult(overrides: Partial<{ issues: IntakeIssue[]; status: IntakeResult['status']; core: string[]; warnings: string[] }> = {}): IntakeResult {
  const issues = overrides.issues ?? [TITLE_NOTE]
  const core = overrides.core ?? ['Python backend services', 'Event-driven systems', 'PostgreSQL']
  const evidence: Record<string, string> = {
    'Python backend services': 'Strong Python.',
    'Event-driven systems': 'Experience with event-driven systems.',
    Snowflake: 'Nice to have: Snowflake, dbt.',
  }
  const asks = issues.filter((issue) => issue.decision === 'ask')
  return {
    raw_input: RAW_INPUT,
    status: overrides.status ?? (asks.length ? 'needs_clarification' : 'ready'),
    confirmed: [],
    role_understanding: {
      posted_title: 'AI Engineer',
      posted_title_source: 'recruiter',
      primary_candidate_identity: { value: 'Backend-heavy AI Engineer', evidence: 'About 70% of your time is backend engineering', source: 'inferred' },
      hiring_company: { value: 'Northwind Payments', evidence: null, source: 'explicit' },
      candidate_archetype: { value: 'An experienced backend engineer who has applied ML in production.', evidence: null, source: 'inferred' },
      role_interpretation: {
        value:
          "This is primarily a backend engineering role that applies machine learning to fraud detection. Even though the title says AI Engineer, the JD says about 70% of the work is backend engineering in Python, FastAPI and Kafka, with ML as the smaller share.",
        evidence: 'About 70% of your time is backend engineering',
        source: 'inferred',
      },
      seniority_scope: { value: 'Senior', evidence: '8-10 years of professional software engineering experience', source: 'inferred' },
      leadership_type: { value: 'none', evidence: null, source: null },
      core_capabilities: [],
      supporting_capabilities: [],
      differentiators: [],
      technologies_mentioned: [
        { category: 'Languages and frameworks', items: ['Python', 'FastAPI'] },
        { category: 'Data and messaging', items: ['Kafka', 'PostgreSQL', 'Snowflake', 'dbt'] },
      ],
      domain: ['Payments', 'Fraud detection'],
      explicit_constraints: {
        locations: [{ city: 'Toronto', state: 'Ontario', country: 'Canada' }],
        work_mode: 'hybrid',
        experience_minimum_years: 8,
        experience_maximum_years: 10,
        employment_type: null,
        exclusions: [],
      },
      open_questions: [],
    },
    decision: {
      issues,
      recommended_ask_count: asks.length,
      stop_reasoning: asks.length ? null : 'Nothing else changes what would be searched.',
      warnings: overrides.warnings ?? [],
      search_consequence_summary: 'Backend Engineer and Software Engineer titles are searched alongside AI Engineer, because most of the work is backend.',
      limitations: ['Work mode (hybrid) is recorded for context. The search cannot filter candidates by work mode.'],
      final_search_intent: {
        hard_requirements: core,
        strong_signals: ['FastAPI', 'Kafka'],
        preferred_differentiators: ['Snowflake', 'dbt'],
        natural_language_search_query: 'Senior backend engineer with Python and event-driven systems experience.',
        exclusions: [],
        evidence,
      },
    },
  }
}

export function makeBrief(overrides: Partial<SearchBrief> = {}): SearchBrief {
  const brief = createEmptySearchBrief()
  brief.role.primaryTitle = 'Backend-heavy AI Engineer'
  brief.role.seniority = 'Senior'
  brief.role.equivalentTitles = ['Backend Engineer', 'Software Engineer']
  brief.experience.minimumYears = '8'
  brief.experience.maximumYears = '10'
  brief.companies.exclude = ['Northwind Payments']
  brief.requirements = { core: ['Python backend services', 'Event-driven systems', 'PostgreSQL'], supporting: ['FastAPI', 'Kafka'], differentiators: ['Snowflake', 'dbt'] }
  return { ...brief, ...overrides }
}
