from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class Candidate(BaseModel):
    """Normalized candidate returned by a provider adapter."""

    candidate_id: Optional[str] = None
    name: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    provider_score: Optional[float] = None
    final_score: float | None = None
    profile_url: Optional[str] = None
    source: Optional[str] = None
    raw_data: Dict[str, Any] = Field(default_factory=dict)
