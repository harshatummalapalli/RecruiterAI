"""Live-wiring: the capability proposer's parsing, and that the real pipeline
assembles offline (no network, no credits)."""

from recruiter.agents.intake.capability_memory import LearnedCapability
from recruiter.agents.intake.llm_proposer import _parse_proposal, make_proposer
from recruiter.pipeline import Pipeline


def test_parse_proposal_specialised():
    cap = _parse_proposal({"broad": False, "label": "Salesforce", "qualifier": "Salesforce",
                           "terms": ["Salesforce", "Apex", "SOQL", "Apex"]})
    assert isinstance(cap, LearnedCapability)
    assert cap.label == "Salesforce" and cap.terms == ("Salesforce", "Apex", "SOQL")  # deduped


def test_sanitizer_drops_the_junk_the_live_run_produced():
    # The exact bad output gpt-4o-mini returned: requirement/language/SWE terms.
    cap = _parse_proposal(
        {"broad": False, "label": "AI Architect",
         "terms": ["AI Architecture", "Java Development", "Agentic Systems", "Python", "Software Engineering"]},
        identity="AI Architect",
    )
    assert cap is not None
    kept = {t.lower() for t in cap.terms}
    assert "java development" not in kept and "python" not in kept and "software engineering" not in kept
    assert "agentic systems" in kept   # real capability signal survives


def test_sanitizer_keeps_short_capability_acronyms():
    cap = _parse_proposal({"broad": False, "label": "Agentic AI",
                           "terms": ["AI", "ML", "LLM", "RAG", "agentic", "Java"]}, identity="AI Engineer")
    kept = {t.lower() for t in cap.terms}
    assert {"ai", "ml", "llm", "rag", "agentic"} <= kept
    assert "java" not in kept          # language dropped


def test_parse_proposal_broad_or_empty_is_none():
    assert _parse_proposal({"broad": True, "label": "Engineer", "terms": ["x"]}) is None
    assert _parse_proposal({"broad": False, "label": "X", "terms": []}) is None
    assert _parse_proposal("nonsense") is None


def test_proposer_with_injected_call_returns_capability():
    def fake_call(system, user, model):
        return {"broad": False, "label": "Agentic AI", "qualifier": "AI", "terms": ["agentic", "LLM", "RAG"]}

    cap = make_proposer(model="any", call=fake_call)("AI Architect", "AI Architect", ["Agentic Systems"])
    assert cap and cap.label == "Agentic AI" and "RAG" in cap.terms


def test_proposer_fails_safe_to_none():
    def boom(system, user, model):
        raise RuntimeError("boom")

    assert make_proposer(model="any", call=boom)("AI Architect", None, []) is None


def test_build_live_pipeline_assembles_offline(tmp_path):
    from recruiter.config import JUDGE_MODEL
    from recruiter.live import build_live_pipeline

    pipe = build_live_pipeline(org="epiq", memory_root=tmp_path, page_size=50, admit_n=25, show=5)
    assert isinstance(pipe, Pipeline)
    assert pipe.search._page_size == 50
    assert pipe.ranking._admit_n == 25 and pipe.ranking._show == 5
    assert pipe.ranking._judge._model == JUDGE_MODEL   # Judge wired to the configured model
