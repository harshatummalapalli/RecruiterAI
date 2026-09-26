"""'Stated in JD' is decided by code, from the raw input, never by the model's say-so."""

from backend.models.intake import FinalSearchIntentDraft, IntakeDecision
from backend.services.requirement_provenance import _sentences, attach_requirement_evidence, stated_evidence

JD = """Senior Backend Engineer
Required: 5+ years of backend engineering, Python. Experience designing REST APIs. C++ is a plus.
You will own services end to end. Nice to have: Kafka or another event streaming system, Docker."""


def _stated(requirement: str):
    return stated_evidence(requirement, _sentences(JD))


def test_a_requirement_stated_in_one_sentence_is_stated_with_that_sentence_as_evidence() -> None:
    assert "Python" in _stated("Strong Python")
    assert "REST APIs" in _stated("Experience designing REST APIs")
    assert "Kafka" in _stated("Kafka or another event streaming system")


def test_counts_and_symbols_survive_tokenizing() -> None:
    assert _stated("5+ years of backend engineering") is not None  # "5+" is a count
    assert _stated("C++") is not None  # "C++" stays itself
    assert _stated("APIs") is not None  # a light stem: API / APIs


def test_a_requirement_the_input_does_not_say_is_inferred() -> None:
    assert _stated("Experience with Terraform") is None
    assert _stated("Leadership of a team") is None


def test_the_words_must_appear_together_not_scattered_across_the_input() -> None:
    # "Python" and "Kafka" both appear, but never in one sentence.
    assert _stated("Python and Kafka streaming pipelines") is None


def test_a_paraphrase_that_adds_something_new_is_inferred() -> None:
    assert _stated("Proficiency in Python or a comparable language with distributed tracing") is None


def test_evidence_is_attached_to_the_final_search_intent_only_for_stated_requirements() -> None:
    decision = IntakeDecision(
        final_search_intent=FinalSearchIntentDraft(
            hard_requirements=["Strong Python", "Experience with Terraform"],
            strong_signals=["Experience designing REST APIs"],
            preferred_differentiators=["Docker"],
        )
    )
    attach_requirement_evidence(decision, JD)
    evidence = decision.final_search_intent.evidence
    assert set(evidence) == {"Strong Python", "Experience designing REST APIs", "Docker"}
    assert "Experience with Terraform" not in evidence
    assert all(sentence in JD for sentence in evidence.values() if not sentence.endswith("…"))


def test_a_requirement_with_no_meaningful_words_is_never_called_stated() -> None:
    assert _stated("Strong experience with the") is None
    assert _stated("") is None
