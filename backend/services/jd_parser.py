from backend.models.search_intent import SearchIntent
from backend.providers.base import BaseLLMProvider


class JDParser:
    """Orchestrates job description parsing through an LLM provider."""

    def __init__(self, provider: BaseLLMProvider) -> None:
        self._provider = provider

    def parse(self, job_description: str) -> SearchIntent:
        """Parse a job description string and return a populated SearchIntent."""
        return self._provider.parse_job_description(job_description)
