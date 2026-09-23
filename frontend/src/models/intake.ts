// Mirrors backend/models/intake.py's JSON shape exactly. This is a type-only
// file — no reasoning lives here. The backend IntakeReasoner (Task A / Task
// B / contradiction backstop) is the sole authority; this UI only renders
// and forwards its output. Do not add heuristics here.

export type FieldValue = {
  value: string | null
  evidence: string | null
  source: 'explicit' | 'inferred' | null
}

export type CapabilityItem = {
  value: string
  tier_signal: string | null
  evidence: string | null
}

// A purely factual inventory entry — every technology named anywhere in the
// JD, grouped by category, with no required/preferred classification. Kept
// deliberately separate from CapabilityItem/tier_signal (the interpretive,
// search-oriented view of the same JD).
export type TechnologyGroup = {
  category: string
  items: string[]
}

export type LocationEntry = {
  city: string | null
  state: string | null
  country: string | null
}

export type ExplicitConstraints = {
  // Structured, possibly multiple — mirrors backend/models/intake.py's
  // LocationEntry list exactly. This is Task A's OWN best-effort JD
  // extraction; it is never authoritative once a recruiter-submitted
  // SearchBoundary exists (see models/searchBoundary.ts) — see
  // apply_search_boundary server-side for how the two are reconciled.
  locations: LocationEntry[]
  work_mode: string | null
  experience_minimum_years: number | null
  experience_maximum_years: number | null
  employment_type: string | null
  exclusions: string[]
}

export type RoleUnderstanding = {
  // The literal title line as written in the input — a plain fact, never an
  // interpretation. May legitimately differ from primary_candidate_identity.
  posted_title: string | null
  primary_candidate_identity: FieldValue
  // The employer actually doing the hiring, when genuinely identifiable —
  // never the candidate's own current employer. Drives a default
  // exclude-current-employees-of-this-company filter (see
  // backend/services/search_translator.py).
  hiring_company: FieldValue
  candidate_archetype: FieldValue
  // The 2-3 sentence, evidence-grounded, teaching-grade explanation of what
  // the role actually is — the main educational content of the brief.
  role_interpretation: FieldValue
  seniority_scope: FieldValue
  leadership_type: FieldValue
  core_capabilities: CapabilityItem[]
  supporting_capabilities: CapabilityItem[]
  differentiators: CapabilityItem[]
  technologies_mentioned: TechnologyGroup[]
  domain: string[]
  explicit_constraints: ExplicitConstraints
  open_questions: string[]
}

export type IntakeIssueOption = { value: string; label: string }

export type IntakeIssue = {
  issue: string
  decision: 'ask' | 'tell' | 'ignore'
  id: string | null
  reasoning: string | null
  question: string | null
  options: IntakeIssueOption[]
  consequence_if_answer_a: string | null
  consequence_if_answer_b: string | null
  insight_text: string | null
  injected_by_backstop: boolean
  backstop_category: string | null
}

export type FinalSearchIntentDraft = {
  hard_requirements: string[]
  strong_signals: string[]
  preferred_differentiators: string[]
  natural_language_search_query: string | null
  location: string | null
  experience_minimum_years: number | null
  experience_maximum_years: number | null
  exclusions: string[]
}

export type IntakeDecision = {
  issues: IntakeIssue[]
  recommended_ask_count: number
  stop_reasoning: string | null
  warnings: string[]
  // One or two sentences bridging interpretation -> search: how the role
  // understanding actually changed what gets searched. Always populated.
  search_consequence_summary: string | null
  final_search_intent: FinalSearchIntentDraft
}

export type IntakeResult = {
  raw_input: string
  role_understanding: RoleUnderstanding
  decision: IntakeDecision
  status: 'understanding' | 'needs_clarification' | 'ready'
}

export type IntakeStartResponse = { session_id: string; result: IntakeResult }

export function pendingAskIssues(result: IntakeResult): IntakeIssue[] {
  return result.decision.issues.filter((issue) => issue.decision === 'ask')
}

export function tellInsights(result: IntakeResult): IntakeIssue[] {
  return result.decision.issues.filter((issue) => issue.decision === 'tell' && issue.insight_text)
}
