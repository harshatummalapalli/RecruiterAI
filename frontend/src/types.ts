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

export interface CandidateNote {
  id: string
  text: string
  createdAt: string
  updatedAt?: string
  pinned?: boolean
}

export interface CandidateResume {
  name: string
  uploadedAt: string
  size?: string
  version?: string
  status?: string
}

export interface CandidateActivityItem {
  id: string
  type: string
  label: string
  detail: string
  timestamp: string
}

export interface MatchExplanationSnapshot {
  final_score?: number | null
  matched_titles?: string[]
  matched_skills?: string[]
  missing_skills?: string[]
  matched_location?: string | null
  matched_experience?: string | null
  matched_ai_technologies?: string[]
  missing_experience?: string | null
  potential_risks?: string[]
  summary?: string | null
  matched_required_skills?: string[]
  missing_required_skills?: string[]
  matched_preferred_skills?: string[]
  missing_preferred_skills?: string[]
}

export type RecruiterStatus = 'New' | 'Reviewed' | 'Shortlisted' | 'Submitted' | 'Interviewing' | 'Offer' | 'Rejected'

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
  reviewed?: boolean
  rejected?: boolean
  exported?: boolean
  status?: RecruiterStatus | null
  notes?: CandidateNote[] | null
  resumes?: CandidateResume[] | null
  activity?: CandidateActivityItem[] | null
  match_explanation?: MatchExplanationSnapshot | null
  raw_data?: Record<string, unknown>
  [key: string]: unknown
}

export interface SearchAnalytics {
  candidateCount: number
  averageMatch: string
  medianMatch: string
  highestScore: string
  lowestScore: string
  topCompanies: string[]
  topLocations: string[]
  topSkills: string[]
}

export interface SearchHistoryEntry {
  id: string
  jd: string
  brief: string
  createdAt: string
  candidateCount: number
  duration: string
  intent: SearchIntent
}

export interface SearchResponse {
  provider: string
  demo?: boolean
  candidate_count: number
  candidates: Candidate[]
  explanations: Array<Record<string, unknown>>
  diagnostics: Record<string, unknown>
}
