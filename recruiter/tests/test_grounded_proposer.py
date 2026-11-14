"""The web-grounded capability proposer — fully offline. A fake `research` stands
in for the network call, so these prove the COMPOSITION mapping (grounded JSON ->
domain + craft dimensions), that the craft dimension KEEPS its languages (C#/.NET)
while the domain dimension strips them, the fail-safe (broad/empty/error -> (),
role stays broad), that the two dimensions reach TWO hard keyword groups via the
real CapabilityProposer, and that the rare call is cached."""

from recruiter.agents.intake.capability_memory import InMemoryCapabilityMemory
from recruiter.agents.intake.capability_proposal import CapabilityProposer
from recruiter.agents.intake.grounded_proposer import make_grounded_proposer

# What a grounded research call returns for the Relativity .NET-engineer role (a
# COMPOSITION): a domain dimension (Relativity platform) AND a craft dimension
# (.NET/SQL development). The domain dimension carries a stray "C#"/".NET" that the
# sanitizer must drop; the craft dimension carries them as its whole point.
RELATIVITY = {
    "broad": False,
    "dimensions": [
        {"label": "Relativity Platform Development", "kind": "domain",
         "terms": ["Relativity", "RelativityOne", "Object Manager", "Kepler", "RSAPI",
                   "RDO", "Event Handlers", "C#", ".NET"]},
        {"label": ".NET / SQL Development", "kind": "craft",
         "terms": ["C#", ".NET", "ASP.NET", "SQL Server", "T-SQL"]},
    ],
}


def _research_returning(payload):
    calls = {"n": 0}
    def research(system, user, model):
        calls["n"] += 1
        return payload, [{"url": "https://platform.relativity.com", "title": "docs"}]
    return research, calls


def test_composition_maps_domain_and_craft():
    research, _ = _research_returning(RELATIVITY)
    dims = make_grounded_proposer(research=research)(
        "Software Engineer", "Software Engineer",
        ["prior Relativity API experience", "convert SQL to .NET"])
    assert len(dims) == 2
    # Domain is first (it is the corroboration/primary signal).
    domain, craft = dims
    assert domain.label == "Relativity Platform Development"
    # Anchored Relativity terms are kept: long acronyms/products + the label word.
    assert "RelativityOne" in domain.terms and "RSAPI" in domain.terms
    assert "Relativity" in domain.terms  # shares the domain label word
    # ...non-anchor domain terms are DEMOTED: generic phrases, a plain word not in
    # the label ("Kepler"), and a SHORT collision-prone acronym ("RDO").
    assert "Object Manager" not in domain.terms and "Event Handlers" not in domain.terms
    assert "Kepler" not in domain.terms and "RDO" not in domain.terms
    # ...and languages are context on the DOMAIN dimension — dropped there...
    assert "C#" not in domain.terms and ".NET" not in domain.terms
    # ...but the CRAFT dimension keeps them: they are the builder-vs-user evidence.
    assert "C#" in craft.terms and ".NET" in craft.terms and "SQL Server" in craft.terms


def test_generic_only_domain_term_is_demoted_but_craft_keeps_its_stack():
    # "Object Manager" (both words generic) is NOT a hard anchor -> dropped from the
    # domain group; "SQL Server" (also generic words) IS kept on the craft group.
    payload = {"broad": False, "dimensions": [
        {"label": "D", "kind": "domain", "terms": ["Object Manager", "RSAPI"]},
        {"label": "C", "kind": "craft", "terms": ["SQL Server", "C#"]},
    ]}
    research, _ = _research_returning(payload)
    domain, craft = make_grounded_proposer(research=research)("Engineer", None, [])
    assert domain.terms == ("RSAPI",)
    assert "SQL Server" in craft.terms and "C#" in craft.terms


def test_domain_with_no_anchor_is_dropped():
    # A domain dimension whose every term is generic-only collapses to no hard
    # group (the role is not keyword-expressible on that axis).
    payload = {"broad": False, "dimensions": [
        {"label": "D", "kind": "domain", "terms": ["Object Manager", "Event Handlers"]},
    ]}
    research, _ = _research_returning(payload)
    assert make_grounded_proposer(research=research)("Engineer", None, []) == ()


def test_broad_verdict_stays_broad():
    research, _ = _research_returning({"broad": True})
    assert make_grounded_proposer(research=research)("Backend Engineer", None, []) == ()


def test_no_dimensions_is_broad():
    research, _ = _research_returning({"broad": False, "dimensions": []})
    assert make_grounded_proposer(research=research)("Engineer", None, []) == ()


def test_dimension_with_only_generic_terms_is_dropped():
    # A domain dimension whose every term is a language sanitizes to empty -> dropped.
    research, _ = _research_returning(
        {"broad": False, "dimensions": [{"label": "X", "kind": "domain", "terms": ["C#", ".NET"]}]})
    assert make_grounded_proposer(research=research)("Engineer", None, []) == ()


def test_only_required_dimensions_become_hard_groups():
    # The JD lists useful extras (AI, Cloud) but only the core two GATE the match.
    payload = {"broad": False, "dimensions": [
        {"label": "Relativity Platform", "kind": "domain", "required": True, "terms": ["RSAPI", "RelativityOne"]},
        {"label": ".NET / SQL", "kind": "craft", "required": True, "terms": ["C#", ".NET"]},
        {"label": "AI / ML", "kind": "other", "required": False, "terms": ["RAG", "LLM", "LangChain"]},
        {"label": "Cloud", "kind": "other", "required": False, "terms": ["Azure", "Docker"]},
    ]}
    research, _ = _research_returning(payload)
    dims = make_grounded_proposer(research=research)("Software Engineer", None, [])
    labels = [d.label for d in dims]
    assert labels == ["Relativity Platform", ".NET / SQL"]  # domain-first, supporting dropped


def test_hard_groups_are_capped_to_avoid_over_filtering():
    # Even if the proposer marks many dimensions required, at most 3 become hard
    # groups (prefer domain, then craft) so the AND can't collapse the set to zero.
    payload = {"broad": False, "dimensions": [
        {"label": "D1", "kind": "domain", "required": True, "terms": ["RSAPI"]},
        {"label": "C1", "kind": "craft", "required": True, "terms": ["C#"]},
        {"label": "O1", "kind": "other", "required": True, "terms": ["Kafka"]},
        {"label": "O2", "kind": "other", "required": True, "terms": ["GraphQL"]},
    ]}
    research, _ = _research_returning(payload)
    dims = make_grounded_proposer(research=research)("Engineer", None, [])
    assert len(dims) == 3
    assert [d.label for d in dims][:2] == ["D1", "C1"]  # domain + craft kept first


def test_research_error_falls_back_to_broad():
    def research(system, user, model):
        raise RuntimeError("web search unavailable")
    assert make_grounded_proposer(research=research)("Engineer", None, []) == ()


def test_composition_reaches_two_hard_keyword_groups_via_the_real_proposer():
    """Both dimensions must flow through the production CapabilityProposer as TWO
    CapabilityGroups — exactly what BriefingAgent AND-s into must_have_keyword_groups,
    so the set is Relativity ∩ .NET-development, not all Relativity profiles."""
    research, calls = _research_returning(RELATIVITY)
    proposer = CapabilityProposer(InMemoryCapabilityMemory(), make_grounded_proposer(research=research))
    reqs = ["prior Relativity API experience", "convert SQL to .NET"]
    groups = proposer.propose("dayzero.partners", "Software Engineer", "Software Engineer", reqs)
    assert len(groups) == 2
    domain, craft = groups
    assert "RSAPI" in domain.terms and "RelativityOne" in domain.terms
    assert "Object Manager" not in domain.terms and "RDO" not in domain.terms  # demoted non-anchors
    assert "C#" in craft.terms and ".NET" in craft.terms
    assert calls["n"] == 1

    # Second role of the same shape is served from memory — the costly grounded call
    # is NOT re-run, and BOTH dimensions survive the round-trip through memory.
    again = proposer.propose("dayzero.partners", "Software Engineer", "Software Engineer", reqs)
    assert len(again) == 2
    assert "RSAPI" in again[0].terms and "C#" in again[1].terms
    assert calls["n"] == 1
