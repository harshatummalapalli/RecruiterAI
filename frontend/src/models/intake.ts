// Mirrors backend/models/intake.py's JSON shape exactly. This is a type-only
// file — no reasoning lives here. The backend IntakeReasoner (Task A / Task
// B / contradiction backstop) is the sole authority; this UI only renders
// and forwards its output. Do not add heuristics here.

export type FieldValue = {
  value: string | null
  evidence: string | null
  // "recruiter" once the recruiter confirmed the value by answering a question.
  source: 'explicit' | 'inferred' | 'recruiter' | null
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
  // "recruiter": typed by the recruiter and kept verbatim. "jd": read from the job description and verified to
  // appear in it. null: no verified posted title.
  posted_title_source: 'recruiter' | 'jd' | null
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

// One structured field the recruiter changed by answering a question. Drives "Confirmed by you".
export type ConfirmedChange = {
  field: 'experience' | 'seniority' | 'identity' | 'requirement' | 'exclusion' | 'leadership'
  description: string
  item: string | null
  issue: string | null
  answer: string | null
}

export type FinalSearchIntentDraft = {
  hard_requirements: string[]
  strong_signals: string[]
  preferred_differentiators: string[]
  natural_language_search_query: string | null
  exclusions: string[]
  // requirement text -> the sentence of the input that states it, found by the server. A requirement with no entry
  // is inferred.
  evidence?: Record<string, string>
}

export type IntakeDecision = {
  issues: IntakeIssue[]
  recommended_ask_count: number
  stop_reasoning: string | null
  warnings: string[]
  // One or two sentences bridging interpretation -> search: how the role
  // understanding actually changed what gets searched. Always populated.
  search_consequence_summary: string | null
  // Things the product cannot enforce for this search (for example, work mode). Shown as "System limitation".
  limitations?: string[]
  final_search_intent: FinalSearchIntentDraft
}

export type IntakeResult = {
  raw_input: string
  role_understanding: RoleUnderstanding
  decision: IntakeDecision
  status: 'understanding' | 'needs_clarification' | 'ready'
  confirmed?: ConfirmedChange[]
}

// `boundary` is the boundary as the server stored it (validated and normalized), which is the one to display.
export type IntakeStartResponse = { session_id: string; result: IntakeResult; boundary?: import('./searchBoundary').SearchBoundary | null }

// GET /intake/{id}: everything needed to resume a brief after a reload.
export type IntakeSessionResponse = IntakeStartResponse & {
  boundary: import('./searchBoundary').SearchBoundary | null
  posted_title_input: string | null
}

// What the server needs to build the executable search from a confirmed brief. Only these fields can be edited.
export type ConfirmationEdits = {
  candidate_identity?: string
  seniority?: string | null
  employment_type?: string | null
  include_titles?: string[]
  exclude_titles?: string[]
  minimum_years?: number | null
  maximum_years?: number | null
  core_signals?: string[]
  supporting_signals?: string[]
  differentiator_signals?: string[]
  exclude_current_companies?: string[]
  preferred_companies?: string[]
}

export type ConfirmationResponse = {
  confirmation_id: string
  session_id: string
  posted_title: string | null
  posted_title_source: 'recruiter' | 'jd' | null
  candidate_identity: string | null
  content_hash: string
}

export function pendingAskIssues(result: IntakeResult): IntakeIssue[] {
  return result.decision.issues.filter((issue) => issue.decision === 'ask')
}

export function tellInsights(result: IntakeResult): IntakeIssue[] {
  return result.decision.issues.filter((issue) => issue.decision === 'tell' && issue.insight_text)
}
