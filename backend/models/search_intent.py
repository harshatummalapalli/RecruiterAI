from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Role:
    title: Optional[str] = None
    seniority: Optional[str] = None
    employment_type: Optional[str] = None
    confidence_score: Optional[float] = None


@dataclass
class Location:
    countries: List[str] = field(default_factory=list)
    states: List[str] = field(default_factory=list)
    cities: List[str] = field(default_factory=list)
    zip_codes: List[str] = field(default_factory=list)
    radius_miles: Optional[float] = None
    # A free-form place name (or, when only a ZIP was given, the ZIP string
    # itself) used as the center point for CrustData's geo_distance filter.
    # CrustData has no zip_code filter field — see backend/providers/crustdata.py.
    radius_place: Optional[str] = None
    radius_unit: str = "mi"
    work_mode: Optional[str] = None
    confidence_score: Optional[float] = None


@dataclass
class Experience:
    minimum_years: Optional[int] = None
    maximum_years: Optional[int] = None
    confidence_score: Optional[float] = None


@dataclass
class Titles:
    include_titles: List[str] = field(default_factory=list)
    exclude_titles: List[str] = field(default_factory=list)
    confidence_score: Optional[float] = None


@dataclass
class Skills:
    required_skills: List[str] = field(default_factory=list)
    preferred_skills: List[str] = field(default_factory=list)
    required_weight: Optional[float] = None
    preferred_weight: Optional[float] = None
    confidence_score: Optional[float] = None


@dataclass
class PreviousBackground:
    preferred_technologies: List[str] = field(default_factory=list)
    preferred_companies: List[str] = field(default_factory=list)
    confidence_score: Optional[float] = None


@dataclass
class AIFocus:
    llm: bool = False
    rag: bool = False
    agentic_ai: bool = False
    mcp: bool = False
    semantic_kernel: bool = False
    confidence_score: Optional[float] = None


@dataclass
class CompanyPreferences:
    exclude_current_companies: List[str] = field(default_factory=list)
    preferred_company_types: List[str] = field(default_factory=list)
    confidence_score: Optional[float] = None


@dataclass
class Ranking:
    must_have: List[str] = field(default_factory=list)
    nice_to_have: List[str] = field(default_factory=list)
    bonus: List[str] = field(default_factory=list)
    confidence_score: Optional[float] = None


@dataclass
class SearchIntent:
    role: Role = field(default_factory=Role)
    location: Location = field(default_factory=Location)
    experience: Experience = field(default_factory=Experience)
    titles: Titles = field(default_factory=Titles)
    skills: Skills = field(default_factory=Skills)
    previous_background: PreviousBackground = field(default_factory=PreviousBackground)
    ai_focus: AIFocus = field(default_factory=AIFocus)
    company_preferences: CompanyPreferences = field(default_factory=CompanyPreferences)
    ranking: Ranking = field(default_factory=Ranking)
    confidence_score: Optional[float] = None
    # A single recruiter-readable sentence describing actual work/seniority/
    # genuinely required vs. preferred skills — used to drive CrustData's
    # relevance-ranked natural-language person_search. Verified in live
    # CrustData experiments to be the strongest discovery mechanism, and the
    # only one that reliably surfaces candidates whose current title doesn't
    # match the role. Falls back to a deterministic template (see
    # SearchPlanner) when not provided, e.g. by non-LLM callers/tests.
    natural_language_search_query: Optional[str] = None
