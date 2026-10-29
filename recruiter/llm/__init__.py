"""Provider-agnostic LLM access. One call, any provider — pick by model name."""

from recruiter.llm.core import complete_json

__all__ = ["complete_json"]
