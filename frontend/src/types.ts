export interface SearchIntent {
  role: {
    title?: string
    seniority?: string
    employment_type?: string
    confidence_score?: number | null
  }
  location: {
    countries: string[]
    states?: string[]
    cities: string[]
    work_mode?: string
    confidence_score?: number | null
    // A "City, State" anchor for the existing Radius Search option (Edit
    // brief) — populated by the backend Search Translator whenever there's
    // a single, unambiguous confirmed city. radius_miles stays unset by
    // default so exact city/state/country match remains the default search;
    // radius is an opt-in the recruiter chooses explicitly.
    radius_place?: string | null
    radius_miles?: number | null
  }
  experience: {
    minimum_years?: number | null
    maximum_years?: number | null
    confidence_score?: number | null
  }
  titles: {
    include_titles: string[]
    exclude_titles: string[]
    confidence_score?: number | null
  }
  skills: {
    required_skills: string[]
    preferred_skills: string[]
    required_weight?: number | null
    preferred_weight?: number | null
    confidence_score?: number | null
  }
  previous_background: {
    preferred_technologies: string[]
    preferred_companies: string[]
    confidence_score?: number | null
  }
  ai_focus: {
    llm?: boolean
    rag?: boolean
    agentic_ai?: boolean
    mcp?: boolean
    semantic_kernel?: boolean
    confidence_score?: number | null
  }
  company_preferences: {
    exclude_current_companies: string[]
    preferred_company_types: string[]
    confidence_score?: number | null
  }
  ranking: {
    must_have: string[]
    nice_to_have: string[]
    bonus: string[]
    confidence_score?: number | null
  }
  confidence_score?: number | null
  natural_language_search_query?: string | null
}

export interface Candidate {
  name?: string | null
  title?: string | null
  company?: string | null
  location?: string | null
  provider_score?: number | null
  final_score?: number | null
  profile_url?: string | null
  source?: string | null
  experience_years?: number | null
  years_of_experience?: number | null
  resume_status?: string | null
  ai_skills?: string[] | null
  summary?: string | null
  shortlist?: boolean
  rejected?: boolean
  exported?: boolean
  notes?: Array<{ id: string; text: string; createdAt: string }> | null
  resumes?: Array<{ name: string; uploadedAt: string }> | null
  activity?: Array<{ id: string; type: string; label: string; detail: string; timestamp: string }> | null
  raw_data?: Record<string, unknown>
  [key: string]: unknown
}

// Raw shape of a backend MatchExplanation.model_dump() — evidence-based,
// never a percentage or a generic "Good Match" label. See
// backend/models/match_explanation.py.
export interface MatchExplanationRaw {
  relevance_tier: 'direct' | 'adjacent' | 'tangential' | 'unclear'
  why_this_candidate: string
  strong_evidence: string[]
  potential_concerns: string[]
  what_we_dont_know: string[]
  matched_signals: Array<{ tier: 'core' | 'supporting' | 'differentiator'; signal_text: string; matched_term: string; source?: string }>
  seniority_alignment: boolean | null
  provider_fit: string | null
  convergence: boolean
  matched_queries: string[]
  final_score?: number | null
}

// Raw shape of a backend CandidateEvidence (dataclasses.asdict()) — career
// history, education, contact, and company context, index-aligned with
// `candidates`/`explanations`. See backend/models/candidate_evidence.py.
export interface CandidateEvidenceRaw {
  current_company: string
  current_industries: string[]
  current_function: string | null
  current_seniority: string | null
  current_headcount: string | null
  current_company_type: string | null
  past_roles: Array<{
    title: string
    company: string
    industries: string[]
    function: string | null
    seniority: string | null
    start_date: string | null
    end_date: string | null
    description: string | null
  }>
  education: Array<{
    institution: string | null
    degree: string | null
    field_of_study: string | null
    start_date: string | null
    end_date: string | null
    description: string | null
  }>
  contact: { email: string | null; phone: string | null; has_business_email: boolean | null }
  updated_at: string | null
  uncertainty: Array<{ field: string; note: string }>
}

export interface SearchResponse {
  provider: string
  search_id: string
  candidate_count: number
  candidates: Candidate[]
  explanations: MatchExplanationRaw[]
  evidence?: CandidateEvidenceRaw[]
  diagnostics: Record<string, unknown>
  warnings?: string[]
  debug?: Record<string, unknown> | null
  // Recruiter-authored state for this search, keyed by the same candidate
  // id sent to PATCH /search/{id}/candidate. Present on both the fresh
  // POST /search response and GET /search/{id} reload — see
  // CandidateReviewScreen.tsx, which hydrates its local decisions/notes
  // state from these instead of starting empty on every mount.
  recruiter_decisions?: Record<string, string>
  notes?: Record<string, Array<{ text: string; created_at: string }>>
}
