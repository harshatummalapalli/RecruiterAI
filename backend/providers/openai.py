import json
from pathlib import Path
from typing import Any, Dict, Optional

from openai import OpenAI

from backend.config import get_openai_api_key
from backend.errors import ConfigurationError, ParsingError
from backend.models.search_intent import (
    AIFocus,
    CompanyPreferences,
    Experience,
    Location,
    PreviousBackground,
    Ranking,
    Role,
    SearchIntent,
    Skills,
    Titles,
)
from backend.providers.base import BaseLLMProvider


class OpenAIProvider(BaseLLMProvider):
    """Concrete LLM provider that calls the OpenAI Responses API and returns a SearchIntent."""

    def __init__(self, client: Optional[OpenAI] = None) -> None:
        self._client = client

    def parse_job_description(self, job_description: str) -> SearchIntent:
        """Convert a raw job description into a SearchIntent using the OpenAI API."""
        api_key = get_openai_api_key()
        if not api_key:
            raise ConfigurationError("OPENAI_API_KEY is not configured. Set it in your environment or .env file.")

        client = self._client or OpenAI(api_key=api_key)
        system_prompt = self._load_prompt("system.txt")
        user_prompt = self._load_prompt("jd_parser.txt").format(job_description=job_description)

        response = client.responses.create(
            model="gpt-4o-mini",
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )

        content = self._extract_response_text(response)
        try:
            raw_response = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ParsingError("OpenAI response was not valid JSON") from exc
        return self._build_search_intent(raw_response)

    def _load_prompt(self, filename: str) -> str:
        """Load a prompt file from the prompts directory."""
        prompt_path = Path(__file__).resolve().parents[2] / "prompts" / filename
        return prompt_path.read_text(encoding="utf-8")

    def _extract_response_text(self, response: Any) -> str:
        """Extract JSON text from the OpenAI response."""
        if hasattr(response, "output_text") and response.output_text:
            return response.output_text

        output_blocks = getattr(response, "output", [])
        parts: list[str] = []
        for block in output_blocks:
            for item in getattr(block, "content", []):
                if getattr(item, "type", None) == "output_text":
                    parts.append(getattr(item, "text", ""))

        return "".join(parts)

    def _build_search_intent(self, raw_response: Dict[str, Any]) -> SearchIntent:
        """Convert provider JSON into a SearchIntent data model."""
        role_data = raw_response.get("role", {})
        location_data = raw_response.get("location", {})
        experience_data = raw_response.get("experience", {})
        titles_data = raw_response.get("titles", {})
        skills_data = raw_response.get("skills", {})
        previous_background_data = raw_response.get("previous_background", {})
        ai_focus_data = raw_response.get("ai_focus", {})
        company_preferences_data = raw_response.get("company_preferences", {})
        ranking_data = raw_response.get("ranking", {})

        return SearchIntent(
            role=Role(
                title=role_data.get("title"),
                seniority=role_data.get("seniority"),
                employment_type=role_data.get("employment_type"),
                confidence_score=role_data.get("confidence_score"),
            ),
            location=Location(
                countries=location_data.get("countries", []),
                cities=location_data.get("cities", []),
                work_mode=location_data.get("work_mode"),
                confidence_score=location_data.get("confidence_score"),
            ),
            experience=Experience(
                minimum_years=experience_data.get("minimum_years"),
                maximum_years=experience_data.get("maximum_years"),
                confidence_score=experience_data.get("confidence_score"),
            ),
            titles=Titles(
                include_titles=titles_data.get("include_titles", []),
                exclude_titles=titles_data.get("exclude_titles", []),
                confidence_score=titles_data.get("confidence_score"),
            ),
            skills=Skills(
                required_skills=skills_data.get("required_skills", []),
                preferred_skills=skills_data.get("preferred_skills", []),
                required_weight=skills_data.get("required_weight"),
                preferred_weight=skills_data.get("preferred_weight"),
                confidence_score=skills_data.get("confidence_score"),
            ),
            previous_background=PreviousBackground(
                preferred_technologies=previous_background_data.get("preferred_technologies", []),
                preferred_companies=previous_background_data.get("preferred_companies", []),
                confidence_score=previous_background_data.get("confidence_score"),
            ),
            ai_focus=AIFocus(
                llm=ai_focus_data.get("llm", False),
                rag=ai_focus_data.get("rag", False),
                agentic_ai=ai_focus_data.get("agentic_ai", False),
                mcp=ai_focus_data.get("mcp", False),
                semantic_kernel=ai_focus_data.get("semantic_kernel", False),
                confidence_score=ai_focus_data.get("confidence_score"),
            ),
            company_preferences=CompanyPreferences(
                exclude_current_companies=company_preferences_data.get("exclude_current_companies", []),
                preferred_company_types=company_preferences_data.get("preferred_company_types", []),
                confidence_score=company_preferences_data.get("confidence_score"),
            ),
            ranking=Ranking(
                must_have=ranking_data.get("must_have", []),
                nice_to_have=ranking_data.get("nice_to_have", []),
                bonus=ranking_data.get("bonus", []),
                confidence_score=ranking_data.get("confidence_score"),
            ),
            confidence_score=raw_response.get("confidence_score"),
        )
