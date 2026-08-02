from types import SimpleNamespace

from backend.config import get_openai_api_key
from backend.providers.openai import OpenAIProvider


class FakeResponses:
    def create(self, **kwargs):
        assert "response_format" not in kwargs
        assert kwargs["text"]["format"]["type"] == "json_object"
        return SimpleNamespace(output_text='{"role": {}, "location": {}, "experience": {}, "titles": {}, "skills": {}, "previous_background": {}, "ai_focus": {}, "company_preferences": {}, "ranking": {}}')


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


def test_openai_provider_uses_sdk_2_responses_text_config(monkeypatch) -> None:
    monkeypatch.setattr("backend.providers.openai.get_openai_api_key", lambda: "test-key")

    provider = OpenAIProvider(client=FakeClient())
    intent = provider.parse_job_description("Need a Python engineer")

    assert intent.role.title is None
