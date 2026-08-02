from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Candidate(BaseModel):
    """Normalized candidate returned by a provider adapter."""

    model_config = ConfigDict(validate_assignment=True)

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

    @field_validator("candidate_id", "name", "title", "company", "location", "email", "phone", "profile_url", "source", mode="before")
    @classmethod
    def _clean_optional_strings(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("raw_data", mode="before")
    @classmethod
    def _normalize_raw_data(cls, value: Any) -> Dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        return {}
