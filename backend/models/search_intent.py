from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Role:
    title: Optional[str] = None
    seniority: Optional[str] = None
    employment_type: Optional[str] = None
    confidence_score: Optional[int] = None


@dataclass
class Location:
    countries: List[str] = field(default_factory=list)
    cities: List[str] = field(default_factory=list)
    work_mode: Optional[str] = None
    confidence_score: Optional[int] = None


@dataclass
class Experience:
    minimum_years: Optional[int] = None
    maximum_years: Optional[int] = None
    confidence_score: Optional[int] = None


@dataclass
class Titles:
    include_titles: List[str] = field(default_factory=list)
    exclude_titles: List[str] = field(default_factory=list)
    confidence_score: Optional[int] = None


@dataclass
class Skills:
    required_skills: List[str] = field(default_factory=list)
    preferred_skills: List[str] = field(default_factory=list)
    required_weight: Optional[float] = None
    preferred_weight: Optional[float] = None
    confidence_score: Optional[int] = None


@dataclass
class PreviousBackground:
    preferred_technologies: List[str] = field(default_factory=list)
    preferred_companies: List[str] = field(default_factory=list)
    confidence_score: Optional[int] = None


@dataclass
class AIFocus:
    llm: bool = False
    rag: bool = False
    agentic_ai: bool = False
    mcp: bool = False
    semantic_kernel: bool = False
    confidence_score: Optional[int] = None


@dataclass
class CompanyPreferences:
    exclude_current_companies: List[str] = field(default_factory=list)
    preferred_company_types: List[str] = field(default_factory=list)
    confidence_score: Optional[int] = None


@dataclass
class Ranking:
    must_have: List[str] = field(default_factory=list)
    nice_to_have: List[str] = field(default_factory=list)
    bonus: List[str] = field(default_factory=list)
    confidence_score: Optional[int] = None


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
    confidence_score: Optional[int] = None
