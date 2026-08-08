export interface SearchIntent {
  role: {
    title?: string
    seniority?: string
    employment_type?: string
    confidence_score?: number | null
  }
  location: {
    countries: string[]
    cities: string[]
    work_mode?: string
    confidence_score?: number | null
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

export interface SearchResponse {
  provider: string
  demo?: boolean
  search_id: string
  candidate_count: number
  candidates: Candidate[]
  explanations: Array<Record<string, unknown>>
  diagnostics: Record<string, unknown>
  warnings?: string[]
  debug?: Record<string, unknown> | null
}
