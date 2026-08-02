from typing import List, Optional

from pydantic import BaseModel, Field


class ProviderCapabilities(BaseModel):
    supported_filters: List[str] = Field(default_factory=list)
    unsupported_filters: Optional[List[str]] = None
