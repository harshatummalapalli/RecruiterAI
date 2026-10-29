"""Live-wiring: the capability proposer's parsing, and that the real pipeline
assembles offline (no network, no credits)."""

from recruiter.agents.intake.capability_memory import LearnedCapability
from recruiter.agents.intake.llm_proposer import _parse_proposal, make_openai_proposer
from recruiter.pipeline import Pipeline


def test_parse_proposal_specialised():
    cap = _parse_proposal({"broad": False, "label": "Salesforce", "qualifier": "Salesforce",
                           "terms": ["Salesforce", "Apex", "SOQL", "Apex"]})
    assert isinstance(cap, LearnedCapability)
    assert cap.label == "Salesforce" and cap.terms == ("Salesforce", "Apex", "SOQL")  # deduped


def test_parse_proposal_broad_or_empty_is_none():
    assert _parse_proposal({"broad": True, "label": "Engineer", "terms": ["x"]}) is None
    assert _parse_proposal({"broad": False, "label": "X", "terms": []}) is None
    assert _parse_proposal("nonsense") is None


def test_proposer_with_fake_client_returns_capability():
    class _Resp:
        output_text = '{"broad": false, "label": "Agentic AI", "qualifier": "AI", "terms": ["agentic", "LLM", "RAG"]}'

    class _Client:
        class responses:
            @staticmethod
            def create(**kwargs):
                return _Resp()

    propose = make_openai_proposer(client=_Client())
    cap = propose("AI Architect", "AI Architect", ["Agentic Systems"])
    assert cap and cap.label == "Agentic AI" and "RAG" in cap.terms


def test_proposer_fails_safe_to_none():
    class _BadClient:
        class responses:
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("boom")

    assert make_openai_proposer(client=_BadClient())("AI Architect", None, []) is None


def test_build_live_pipeline_assembles_offline(tmp_path):
    from recruiter.live import build_live_pipeline

    pipe = build_live_pipeline(org="epiq", memory_root=tmp_path, page_size=50, admit_n=25, show=5)
    assert isinstance(pipe, Pipeline)
    assert pipe.search._page_size == 50
    assert pipe.ranking._admit_n == 25 and pipe.ranking._show == 5
