"""The web-grounded capability proposer — fully offline. A fake `research` stands
in for the network call, so these prove the mapping (grounded JSON -> capability),
the fail-safe (broad/empty/error -> None, role stays broad), that the grounded
terms reach the hard keyword group via the real CapabilityProposer, and that the
rare call is cached (not re-run on the second role of the same shape)."""

from recruiter.agents.intake.capability_memory import InMemoryCapabilityMemory
from recruiter.agents.intake.capability_proposal import CapabilityProposer
from recruiter.agents.intake.grounded_proposer import make_grounded_proposer

# What a grounded research call returns for the Relativity role (the live LLM chat's
# own finding). Note "C#" / ".NET" are present but must be dropped as generic.
RELATIVITY = {
    "broad": False,
    "label": "Relativity Platform Development",
    "qualifier": "eDiscovery",
    "strong_terms": ["Relativity", "RelativityOne", "Object Manager API", "Kepler", "RSAPI",
                     "Event Handlers", "RDO", "RAP", "IDBContext", "C#", ".NET"],
    "anti_signals": ["document review", "Relativity reviewer"],
    "employer_pools": ["eDiscovery vendors", "AmLaw 100 law firms"],
    "sources": [{"claim": "Object Manager replaces direct SQL", "url": "https://platform.relativity.com"}],
}


def _research_returning(payload):
    calls = {"n": 0}
    def research(system, user, model):
        calls["n"] += 1
        return payload, [{"url": "https://platform.relativity.com", "title": "docs"}]
    return research, calls


def test_maps_strong_terms_and_drops_generics():
    research, _ = _research_returning(RELATIVITY)
    cap = make_grounded_proposer(research=research)("Software Engineer", "Software Engineer",
                                                    ["prior Relativity API experience", "convert SQL to .NET"])
    assert cap is not None
    assert cap.label == "Relativity Platform Development"
    assert "Object Manager API" in cap.terms and "Kepler" in cap.terms and "RSAPI" in cap.terms
    # Languages are context, not capability evidence — the sanitizer drops them.
    assert "C#" not in cap.terms and ".NET" not in cap.terms


def test_broad_verdict_stays_broad():
    research, _ = _research_returning({"broad": True})
    assert make_grounded_proposer(research=research)("Backend Engineer", None, []) is None


def test_no_strong_terms_is_none():
    research, _ = _research_returning({"broad": False, "label": "X", "strong_terms": []})
    assert make_grounded_proposer(research=research)("Engineer", None, []) is None


def test_research_error_falls_back_to_broad():
    def research(system, user, model):
        raise RuntimeError("web search unavailable")
    assert make_grounded_proposer(research=research)("Engineer", None, []) is None


def test_terms_reach_a_hard_keyword_group_via_the_real_proposer():
    """The grounded terms must flow through the production CapabilityProposer as a
    CapabilityGroup — that is exactly what BriefingAgent turns into the hard
    must_have_keyword_groups filter + NL lead."""
    research, calls = _research_returning(RELATIVITY)
    proposer = CapabilityProposer(InMemoryCapabilityMemory(), make_grounded_proposer(research=research))
    reqs = ["prior Relativity API experience", "convert SQL to .NET"]
    groups = proposer.propose("dayzero.partners", "Software Engineer", "Software Engineer", reqs)
    assert len(groups) == 1
    assert "Kepler" in groups[0].terms and "Object Manager API" in groups[0].terms
    assert calls["n"] == 1

    # Second role of the same shape is served from memory — the costly grounded call
    # is NOT re-run (rare + cached, same contract as the closed-book proposer).
    again = proposer.propose("dayzero.partners", "Software Engineer", "Software Engineer", reqs)
    assert "Kepler" in again[0].terms
    assert calls["n"] == 1
