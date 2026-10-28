from backend.services.role_defining_capability import derive_capability_group


def test_ai_data_engineer_yields_ai_group():
    prop = derive_capability_group("AI Data Engineer")
    assert prop is not None
    assert prop.label == "AI / ML"
    assert "AI" in prop.terms and "machine learning" in prop.terms and "LLM" in prop.terms
    assert prop.source_qualifier == "ai"
    assert "AI / ML" in prop.rationale


def test_plain_data_engineer_yields_nothing():
    # Guardrail: no role-defining specialization -> no proposal (stay broad).
    assert derive_capability_group("Data Engineer") is None
    assert derive_capability_group("Full Stack Developer") is None
    assert derive_capability_group("Senior Backend Engineer") is None


def test_does_not_fire_on_substring_false_positive():
    # "ai" must be a whole word, never a substring of "maintainability" etc.
    assert derive_capability_group("Maintainability Engineer") is None


def test_capability_texts_fold_in_specific_evidence_terms():
    prop = derive_capability_group(
        "AI Software Engineer",
        capability_texts=["Build RAG and agentic pipelines", "fine-tuning LLMs"],
    )
    assert prop is not None
    assert "RAG" in prop.terms          # folded in from capability text
    assert "fine-tuning" in prop.terms
    # A specific term NOT present in the text is not added.
    assert "diffusion" not in prop.terms


def test_capability_texts_never_trigger_on_their_own():
    # RAG in the capabilities but a non-AI identity -> still no proposal.
    assert derive_capability_group("Backend Engineer", capability_texts=["uses RAG"]) is None


def test_posted_title_is_a_fallback_signal():
    prop = derive_capability_group(primary_candidate_identity="", posted_title="ML Engineer")
    assert prop is not None
    assert prop.label == "AI / ML"


def test_terms_are_unique_and_order_preserving():
    prop = derive_capability_group("GenAI Engineer", capability_texts=["AI AI machine learning"])
    assert prop is not None
    assert len(prop.terms) == len(set(t.lower() for t in prop.terms))
    assert prop.terms[0] == "AI"
