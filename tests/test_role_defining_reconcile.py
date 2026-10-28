"""Deterministic role-defining-capability backstop: when the title carries an
AI/ML/GenAI qualifier, the identity keeps it and the capability is core/hard,
regardless of how the LLM tiered it. This is the systemic fix for the observed
'GenAI Full Stack Developer' -> identity 'Full Stack Developer', AI demoted to a
differentiator."""

from backend.models.intake import (
    CapabilityItem,
    FieldValue,
    FinalSearchIntentDraft,
    IntakeDecision,
    RoleUnderstanding,
)
from backend.services.intake_reasoning import reconcile_role_defining_capability


def _ru(identity, posted, core=None, supporting=None, diff=None):
    return RoleUnderstanding(
        posted_title=posted,
        primary_candidate_identity=FieldValue(value=identity, source="inferred"),
        core_capabilities=[CapabilityItem(value=v, tier_signal="required") for v in (core or [])],
        supporting_capabilities=[CapabilityItem(value=v, tier_signal="supporting") for v in (supporting or [])],
        differentiators=[CapabilityItem(value=v, tier_signal="differentiator") for v in (diff or [])],
    )


def _decision(hard=None, strong=None, pref=None):
    return IntakeDecision(
        issues=[],
        final_search_intent=FinalSearchIntentDraft(
            hard_requirements=list(hard or []),
            strong_signals=list(strong or []),
            preferred_differentiators=list(pref or []),
            natural_language_search_query="q",
        ),
    )


def _vals(items):
    return [i.value for i in items]


def test_genai_full_stack_identity_restored_and_capability_promoted():
    ai_item = "Experience with AI or Generative AI tools"
    ru = _ru(
        "Full Stack Developer", "GenAI Full Stack Developer",
        core=["Full Stack Development", "Backend Development with Python"],
        diff=[ai_item],
    )
    dec = _decision(hard=["Full Stack Development", "Backend Development with Python"], pref=[ai_item])

    reconcile_role_defining_capability(ru, dec)

    # 1. Identity keeps the title's qualifier, with the title's own casing.
    assert ru.primary_candidate_identity.value == "GenAI Full Stack Developer"
    assert ru.primary_candidate_identity.source == "inferred"  # provenance preserved
    # 2. The AI capability is now core + hard, and no longer a differentiator.
    assert ai_item in _vals(ru.core_capabilities)
    assert ai_item not in _vals(ru.differentiators)
    assert ai_item in dec.final_search_intent.hard_requirements
    assert ai_item not in dec.final_search_intent.preferred_differentiators


def test_injects_capability_when_brief_names_none():
    ru = _ru("AI Engineer", "AI Engineer", core=["Distributed backend systems"])
    dec = _decision(hard=["Distributed backend systems"])

    reconcile_role_defining_capability(ru, dec)

    # Identity already had the qualifier -> unchanged; a core AI item is injected.
    assert ru.primary_candidate_identity.value == "AI Engineer"
    assert any("AI / ML capability" == v for v in _vals(ru.core_capabilities))
    assert "AI / ML capability" in dec.final_search_intent.hard_requirements


def test_already_correct_ai_role_is_untouched():
    ru = _ru(
        "AI Data Engineer", "AI Data Engineer",
        core=["Build RAG and agentic AI pipelines", "Python and SQL"],
    )
    dec = _decision(hard=["Build RAG and agentic AI pipelines", "Python and SQL"])
    before_core = _vals(ru.core_capabilities)

    reconcile_role_defining_capability(ru, dec)

    assert ru.primary_candidate_identity.value == "AI Data Engineer"
    assert _vals(ru.core_capabilities) == before_core  # idempotent, no injection
    assert dec.final_search_intent.hard_requirements == ["Build RAG and agentic AI pipelines", "Python and SQL"]


def test_plain_role_without_qualifier_is_untouched():
    ru = _ru("Full Stack Developer", "Full Stack Developer", core=["Full Stack Development"], diff=["Nice to have Docker"])
    dec = _decision(hard=["Full Stack Development"], pref=["Nice to have Docker"])

    reconcile_role_defining_capability(ru, dec)

    assert ru.primary_candidate_identity.value == "Full Stack Developer"
    assert _vals(ru.core_capabilities) == ["Full Stack Development"]
    assert _vals(ru.differentiators) == ["Nice to have Docker"]


def test_promotes_from_supporting_tier_too():
    ml_item = "Hands-on machine learning model deployment"
    ru = _ru("ML Platform Engineer", "ML Platform Engineer", core=["Kubernetes"], supporting=[ml_item])
    dec = _decision(hard=["Kubernetes"], strong=[ml_item])

    reconcile_role_defining_capability(ru, dec)

    assert ml_item in _vals(ru.core_capabilities)
    assert ml_item not in _vals(ru.supporting_capabilities)
    assert ml_item in dec.final_search_intent.hard_requirements
    assert ml_item not in dec.final_search_intent.strong_signals
