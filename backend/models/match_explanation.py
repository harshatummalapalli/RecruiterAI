from typing import List, Optional

from pydantic import BaseModel


class MatchExplanation(BaseModel):
    final_score: Optional[float] = None
    matched_required_skills: List[str] = []
    missing_required_skills: List[str] = []
    matched_preferred_skills: List[str] = []
    missing_preferred_skills: List[str] = []
    title_match: Optional[bool] = None
    location_match: Optional[bool] = None
    company_match: Optional[bool] = None
    experience_match: Optional[bool] = None
    summary: Optional[str] = None
