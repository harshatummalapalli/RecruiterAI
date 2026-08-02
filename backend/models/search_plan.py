from typing import List, Optional

from pydantic import BaseModel, Field


class SearchQuery(BaseModel):
    query_name: Optional[str] = None
    include_titles: List[str] = Field(default_factory=list)
    exclude_titles: List[str] = Field(default_factory=list)
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    countries: List[str] = Field(default_factory=list)
    cities: List[str] = Field(default_factory=list)
    work_mode: Optional[str] = None
    minimum_years: Optional[int] = None
    maximum_years: Optional[int] = None
    preferred_companies: List[str] = Field(default_factory=list)
    exclude_current_companies: List[str] = Field(default_factory=list)
    preferred_company_types: List[str] = Field(default_factory=list)
    must_have: List[str] = Field(default_factory=list)
    nice_to_have: List[str] = Field(default_factory=list)
    bonus: List[str] = Field(default_factory=list)


class SearchPlan(BaseModel):
    searches: List[SearchQuery] = Field(default_factory=list)
    strategy: Optional[str] = None
    reasoning: Optional[str] = None
    confidence_score: Optional[float] = None
