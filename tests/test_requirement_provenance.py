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


# ---- the reading fields: code decides, the model's source flag is never trusted ---------------------------------------
import copy
import json

from backend.models.intake import FieldValue
from backend.services.intake_reasoning import IntakeReasoner
from backend.services.requirement_provenance import apply_field_provenance

RAW = """AI Engineer
Northwind Payments builds fraud detection for card issuers.
About 70% of your time is backend engineering (Python, FastAPI, Kafka) and about 30% is applying ML to fraud.
Requirements: 8-10 years of professional software engineering experience. Strong Python."""

TASK_A = {
    "posted_title": "AI Engineer",
    "primary_candidate_identity": {"value": "Backend Engineer with ML focus", "evidence": "backend engineering", "source": "stated_in_jd"},
    "hiring_company": {"value": "Northwind Payments", "source": "explicit"},
    "candidate_archetype": {"value": "A pragmatic engineer who ships production services", "source": "explicit"},
    "role_interpretation": {"value": "This is mostly a backend role that applies machine learning to fraud.", "evidence": "70% backend", "source": "explicit"},
    "seniority_scope": {"value": "mid-level", "evidence": "8-10 years", "source": "explicit"},
    "leadership_type": {"value": "none"},
    "core_capabilities": [{"value": "Strong Python", "tier_signal": "required"}],
    "supporting_capabilities": [],
    "differentiators": [],
    "technologies_mentioned": [],
    "domain": [],
    "explicit_constraints": {"locations": [], "work_mode": None, "experience_minimum_years": 8, "experience_maximum_years": 10, "employment_type": None, "exclusions": []},
}
TASK_B = {"issues": [], "recommended_ask_count": 0, "warnings": [], "final_search_intent": {"hard_requirements": ["Strong Python"], "strong_signals": [], "preferred_differentiators": [], "natural_language_search_query": "x", "exclusions": []}}


class _Canned:
    def __init__(self, payloads):
        self._payloads = [copy.deepcopy(p) for p in payloads]
        self.responses = self

    def create(self, **_):
        payload = self._payloads.pop(0)
        return type("R", (), {"output_text": json.dumps(payload)})()


def _run(task_a=TASK_A, raw=RAW):
    return IntakeReasoner(client=_Canned([task_a, TASK_B])).run(raw, posted_title="AI Engineer")


def test_a_model_claiming_explicit_cannot_make_identity_or_reading_stated_when_the_input_does_not_say_it(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    role = _run().role_understanding
    assert role.primary_candidate_identity.source == "inferred"  # the model said "stated_in_jd"
    assert role.role_interpretation.source == "inferred"  # the model said "explicit"
    assert role.candidate_archetype.source == "inferred"


def test_identity_is_stated_only_when_the_input_really_says_it(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    task_a = copy.deepcopy(TASK_A)
    task_a["primary_candidate_identity"] = {"value": "AI Engineer", "source": "inferred"}  # the model under-claims
    identity = _run(task_a).role_understanding.primary_candidate_identity
    assert identity.source == "explicit"
    assert "AI Engineer" in identity.evidence


def test_seniority_is_marked_inferred_and_stays_separate_from_experience(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    role = _run().role_understanding
    assert role.seniority_scope.value == "mid-level"  # no years-to-seniority rule: the value is left alone
    assert role.seniority_scope.source == "inferred"
    assert (role.explicit_constraints.experience_minimum_years, role.explicit_constraints.experience_maximum_years) == (8, 10)


def test_a_value_the_recruiter_set_keeps_confirmed_by_you() -> None:
    from backend.models.intake import RoleUnderstanding

    role = RoleUnderstanding(seniority_scope=FieldValue(value="Senior", source="recruiter"), primary_candidate_identity=FieldValue(value="Data Engineer", source="recruiter"))
    apply_field_provenance(role, RAW)
    assert role.seniority_scope.source == "recruiter"
    assert role.primary_candidate_identity.source == "recruiter"


def test_empty_fields_are_left_untagged() -> None:
    from backend.models.intake import RoleUnderstanding

    role = RoleUnderstanding()
    apply_field_provenance(role, RAW)
    assert role.seniority_scope.source is None and role.seniority_scope.value is None
