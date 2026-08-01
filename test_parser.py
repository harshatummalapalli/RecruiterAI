import json
import os
from pprint import pprint

from backend.providers.openai import OpenAIProvider
from backend.services.jd_parser import JDParser

job_description = """
We are hiring a Senior AI Software Engineer with 5+ years of experience building LLM applications using Python, FastAPI, Azure OpenAI, LangGraph, Docker and PostgreSQL. Hybrid role based in Bangalore.
"""

if not os.getenv("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = "test-key"


class FakeResponse:
    def __init__(self, payload):
        self.output_text = json.dumps(payload)


class FakeResponses:
    def create(self, **kwargs):
        payload = {
            "role": {
                "title": "Senior AI Software Engineer",
                "seniority": "Senior",
                "employment_type": "Full-time",
                "confidence_score": 92,
            },
            "location": {
                "countries": ["India"],
                "cities": ["Bangalore"],
                "work_mode": "Hybrid",
                "confidence_score": 90,
            },
            "experience": {
                "minimum_years": 5,
                "maximum_years": 10,
                "confidence_score": 91,
            },
            "titles": {
                "include_titles": ["AI Software Engineer", "Machine Learning Engineer"],
                "exclude_titles": ["Data Analyst"],
                "confidence_score": 88,
            },
            "skills": {
                "required_skills": ["Python", "FastAPI", "PostgreSQL"],
                "preferred_skills": ["Azure OpenAI", "LangGraph", "Docker"],
                "required_weight": 1.0,
                "preferred_weight": 0.8,
                "confidence_score": 95,
            },
            "previous_background": {
                "preferred_technologies": ["Python", "FastAPI", "LLM"],
                "preferred_companies": ["AI Product Companies"],
                "confidence_score": 84,
            },
            "ai_focus": {
                "llm": True,
                "rag": False,
                "agentic_ai": True,
                "mcp": False,
                "semantic_kernel": False,
                "confidence_score": 90,
            },
            "company_preferences": {
                "exclude_current_companies": [],
                "preferred_company_types": ["Product", "Startup"],
                "confidence_score": 80,
            },
            "ranking": {
                "must_have": ["Python", "FastAPI", "LLM"],
                "nice_to_have": ["Azure OpenAI", "LangGraph"],
                "bonus": ["Docker", "PostgreSQL"],
                "confidence_score": 87,
            },
            "confidence_score": 90,
        }
        return FakeResponse(payload)


class FakeClient:
    def __init__(self):
        self.responses = FakeResponses()


provider = OpenAIProvider(client=FakeClient())
parser = JDParser(provider)
result = parser.parse(job_description)

pprint(result.__dict__)
