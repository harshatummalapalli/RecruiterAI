from abc import ABC, abstractmethod

from backend.models.search_intent import SearchIntent


class BaseLLMProvider(ABC):
    """Abstract interface for LLM-backed providers that convert a job description into a SearchIntent."""

    @abstractmethod
    def parse_job_description(self, job_description: str) -> SearchIntent:
        """Convert a job description into a structured SearchIntent."""
        raise NotImplementedError
