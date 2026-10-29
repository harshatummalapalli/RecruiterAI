"""Per-org learned taxonomy: the memory store and the memory-first proposer."""

from recruiter.agents.intake.capability_memory import (
    FileCapabilityMemory,
    InMemoryCapabilityMemory,
    LearnedCapability,
    normalise_key,
)
from recruiter.agents.intake.capability_proposal import CapabilityProposer


def test_normalise_key_strips_seniority():
    assert normalise_key("Senior AI Engineer") == "ai engineer"
    assert normalise_key("Lead Data Engineer") == "data engineer"
    assert normalise_key("AI Solutions Architect") == "ai solutions architect"


def test_file_memory_roundtrip(tmp_path):
    mem = FileCapabilityMemory(tmp_path)
    cap = LearnedCapability("salesforce developer", "Salesforce", ("Salesforce", "Apex", "SOQL"), "Salesforce")
    mem.put("acme", cap)
    got = FileCapabilityMemory(tmp_path).get("acme", "salesforce developer")
    assert got is not None and got.terms == ("Salesforce", "Apex", "SOQL")
    # Org isolation.
    assert FileCapabilityMemory(tmp_path).get("other", "salesforce developer") is None


def test_proposer_memory_hit_skips_llm():
    mem = InMemoryCapabilityMemory()
    mem.put("acme", LearnedCapability(normalise_key("AI Engineer"), "AI / ML", ("AI", "LLM"), "AI"))
    calls = []
    proposer = CapabilityProposer(mem, llm_proposer=lambda *a: calls.append(1) or None)
    groups = proposer.propose("acme", "Senior AI Engineer")
    assert len(groups) == 1 and groups[0].label == "AI / ML"
    assert calls == []  # cached -> no LLM call


def test_proposer_calls_llm_once_then_caches():
    mem = InMemoryCapabilityMemory()
    calls = []

    def llm(identity, posted, reqs):
        calls.append(identity)
        return LearnedCapability("", "Salesforce", ("Salesforce", "Apex"), "Salesforce")

    proposer = CapabilityProposer(mem, llm_proposer=llm)
    first = proposer.propose("acme", "Salesforce Developer")
    second = proposer.propose("acme", "Salesforce Developer")
    assert first[0].terms == ("Salesforce", "Apex")
    assert second[0].terms == ("Salesforce", "Apex")
    assert len(calls) == 1  # second was served from memory


def test_broad_role_is_cached_and_never_re_asked():
    mem = InMemoryCapabilityMemory()
    calls = []
    proposer = CapabilityProposer(mem, llm_proposer=lambda *a: calls.append(1) or None)
    assert proposer.propose("acme", "Senior Backend Engineer") == ()
    assert proposer.propose("acme", "Senior Backend Engineer") == ()
    assert len(calls) == 1  # broad marker cached after the first miss


def test_no_llm_configured_stays_broad():
    proposer = CapabilityProposer(InMemoryCapabilityMemory())
    assert proposer.propose("acme", "AI Engineer") == ()
