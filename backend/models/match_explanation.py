from typing import List, Optional

from pydantic import BaseModel


class MatchExplanation(BaseModel):
    final_score: Optional[float] = None
    matched_required_skills: List[str] = []
    missing_required_skills: List[str] = []
    matched_preferred_skills: List[str] = []
    missing_preferred_skills: List[str] = []
    matched_titles: List[str] = []
    matched_skills: List[str] = []
    missing_skills: List[str] = []
    matched_location: Optional[str] = None
    matched_experience: Optional[str] = None
    matched_ai_technologies: List[str] = []
    missing_experience: Optional[str] = None
    potential_risks: List[str] = []
    title_match: Optional[bool] = None
    location_match: Optional[bool] = None
    company_match: Optional[bool] = None
    experience_match: Optional[bool] = None
    summary: Optional[str] = None
