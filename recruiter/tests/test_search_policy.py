"""Search policy — vendor-boundary adaptation (city aliases, ambiguous titles)."""

from recruiter.search_policy import (
    city_aliases,
    expand_city_aliases,
    hard_title_exclusions,
)


def test_expand_city_aliases_sends_every_spelling():
    out = expand_city_aliases(["Bangalore"])
    assert "Bangalore" in out and "Bengaluru" in out        # canonical carried in
    # Gurgaon -> also Gurugram (the spelling CrustData actually indexes)
    assert "Gurugram" in expand_city_aliases(["Gurgaon"])


def test_expand_city_aliases_dedupes_and_keeps_unknown():
    assert expand_city_aliases(["Pune", "pune"]) == ("Pune", "Poona")
    assert expand_city_aliases(["Indore"]) == ("Indore",)   # no alias group -> itself
    assert expand_city_aliases([]) == ()


def test_city_aliases_lowercased_for_matching():
    assert city_aliases("Bengaluru") == {"bengaluru", "bangalore"}


def test_hard_title_exclusions_drops_only_ambiguous():
    out = hard_title_exclusions(("Founder", "VP", "Director", "Managing Director", "Manager", "Head of"))
    assert "Manager" not in out                              # ambiguous -> verify net only
    assert "Managing Director" in out                        # distinct title, kept
    assert {"Founder", "VP", "Director", "Head of"} <= set(out)
