"""Thread B detection: ask which specialization only when a broad super-type
title isn't already pinned by the role's own evidence; then, once pinned, ask the
stack only when one isn't already named."""

from recruiter.agents.intake.specialization import (
    disambiguate,
    is_any_stack,
    stack_question,
    stack_terms,
)


def _options(question):
    return set(question.options)


def test_bare_super_type_with_no_signals_asks():
    q = disambiguate("Software Engineer", ["Strong communication", "5 years experience"])
    assert q is not None and q.id == "specialization" and q.kind == "choice"
    assert {"Backend", "Frontend", "Full-stack"} <= _options(q)


def test_evidence_pins_one_specialization_does_not_ask():
    q = disambiguate("Software Engineer",
                     ["Design REST APIs", "microservice architecture", "Postgres database"])
    assert q is None  # clearly backend -> no need to ask


def test_ai_engineer_is_a_super_type_and_disambiguates():
    assert disambiguate("Senior AI Engineer", ["Team player"]) is not None
    # RAG/LLM evidence pins the applied/GenAI kind -> silent.
    assert disambiguate("AI Engineer", ["Build RAG retrieval over docs", "prompt an LLM agent"]) is None


def test_non_tech_super_type_covered():
    q = disambiguate("Analyst", ["Stakeholder management"])
    assert q is not None and "Financial / FP&A" in q.options


def test_already_specific_title_is_left_alone():
    # Not a super-type at all -> never asks (seniority is stripped first).
    assert disambiguate("Senior Backend Engineer", ["anything"]) is None
    assert disambiguate("Salesforce Developer", ["Apex", "SOQL"]) is None


def test_tie_between_two_kinds_asks():
    # Matches backend AND frontend equally -> ambiguous (likely full-stack) -> ask.
    q = disambiguate("Software Engineer", ["backend api work", "frontend react work"])
    assert q is not None


# --- B-depth2: the stack axis ---

def test_backend_pinned_but_no_language_asks_the_stack():
    # The exact example: evidence pins backend, but no language -> ask, with "any" offered.
    q = stack_question("Software Engineer", ["Design REST APIs", "microservices", "Postgres"])
    assert q is not None and q.id == "stack" and q.routing == "filter"
    assert {"Java", ".NET / C#", "Python"} <= set(q.options)
    assert "Any stack is fine" in q.options


def test_named_language_is_not_re_asked():
    assert stack_question("Software Engineer", ["Spring Boot microservices", "REST APIs"]) is None


def test_stack_only_asked_once_a_specialization_is_pinned():
    # Still ambiguous between kinds -> that question comes first, not the stack.
    assert stack_question("Software Engineer", ["general coding", "teamwork"]) is None


def test_no_stack_axis_defined_means_no_stack_question():
    # ML is pinned but has no seeded stack axis yet -> nothing asked.
    assert stack_question("Software Engineer", ["machine learning model training inference"]) is None


def test_any_stack_sentinel_and_terms_lookup():
    assert is_any_stack("Any stack is fine") is True
    assert is_any_stack("Java") is False
    assert "java" in stack_terms("Java")
    assert stack_terms("Nonexistent") == ()


# --- regressions from the live end-to-end run (2026-11-05): word-start matching ---

def test_word_start_matching_does_not_false_pin_on_substrings():
    # Live bug: "ui" ⊂ "built" false-pinned Frontend on a genuinely vague JD. These
    # are the REAL requirement texts the reader produced; the role must ask WHICH kind.
    reqs = ["Has built and shipped customer-facing product features", "Writes clean, well-tested code"]
    assert stack_question("Software Engineer", reqs) is None          # nothing pinned -> no stack
    q = disambiguate("Software Engineer", reqs)
    assert q is not None and q.id == "specialization"                 # asks which kind


def test_stack_reachable_when_identity_itself_names_the_specialization():
    # CoWork round 2: the reader rewrites the title to "Backend Software Engineer" /
    # "Backend Engineer", which isn't a super-type key — the stack card must still appear.
    for identity in ("Backend Engineer", "Senior Backend Software Engineer"):
        q = stack_question(identity, ["REST APIs", "microservices", "Postgres"])
        assert q is not None and q.id == "stack" and "Java" in q.options, identity


def test_backend_real_reader_output_pins_and_asks_stack():
    # The REAL backend-JD requirement texts: must pin Backend and ask its stack.
    reqs = [
        "Designs and builds REST APIs",
        "Builds and owns microservices end to end",
        "Works with PostgreSQL relational databases at scale",
        "Experience with distributed systems and high-throughput backends",
    ]
    assert disambiguate("Software Engineer", reqs) is None            # backend is pinned
    q = stack_question("Software Engineer", reqs)
    assert q is not None and q.id == "stack" and "Java" in q.options
