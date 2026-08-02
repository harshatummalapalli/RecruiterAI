from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from backend.models.candidate import Candidate
from backend.models.search_intent import SearchIntent
from backend.models.search_plan import SearchPlan


class BaseProvider(ABC):
    """Abstract interface for search providers that retrieve candidates from a source."""

    @abstractmethod
    def search(self, plan: SearchPlan) -> List[Candidate]:
        """Execute a search plan and return normalized candidates."""
        raise NotImplementedError

    def search_with_options(self, plan: SearchPlan, options: Optional[Dict[str, Any]] = None) -> List[Candidate]:
        """Execute a search plan with optional provider-specific execution controls."""
        return self.search(plan)


class BaseLLMProvider(BaseProvider, ABC):
    """Abstract interface for LLM-backed providers that convert a job description into a SearchIntent."""

    @abstractmethod
    def parse_job_description(self, job_description: str) -> SearchIntent:
        """Convert a job description into a structured SearchIntent."""
        raise NotImplementedError

    def search(self, plan: SearchPlan) -> List[Candidate]:
        """Search-based providers should override this when they support candidate retrieval."""
        raise NotImplementedError
