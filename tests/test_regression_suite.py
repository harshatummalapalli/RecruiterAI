"""Phase 0 — semantic regression suite (executable).

This is NOT a candidate-scoring benchmark. It is a semantic test suite whose
job is to make it hard to accidentally make RecruiterAI worse: it pins, per JD,
what the recruiter MEANT (archetype, role family, logical structure, per-signal
routing) and the provider search plan that intent should compile to.

Today it validates that the fixtures are well-formed and internally consistent,
and it enforces the scoping guards agreed for the intent model (notably the
two-level logical-composition cap). Phase 3's compiler tests will import these
fixtures and assert the compiler reproduces each `expected_filter_tree`.

Start small (Epiq + Python), make it executable, expand as failures appear.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "regression_set"

VALID_ARCHETYPES = {"title_defined", "skill_defined", "hybrid"}
VALID_STRENGTHS = {"required", "preferred", "context", "required_and_preferred_mix"}
VALID_ROUTINGS = {
    "enforce",                    # provider hard filter
    "enforce_with_warning",       # verified filter, data_confidence unknown -> warn + verify downstream
    "enforce_but_not_verifiable", # filterable server-side but response-gated -> enforce + disclose/Harvest-verify
    "judge",                      # retrieve broad, verify per-candidate
    "context_or_evidence",        # no verified provider mechanism -> NL context / evidence only
    "disclose",                   # cannot enforce or verify -> state plainly
}
LEAF_KEYS = {"field", "type", "value"}


def _load() -> List[Dict[str, Any]]:
    out = []
    for p in sorted(FIXTURE_DIR.glob("*.json")):
        with p.open(encoding="utf-8") as fh:
            d = json.load(fh)
            d["_file"] = p.name
            out.append(d)
    return out


def _tree_depth(node: Dict[str, Any], _depth: int = 1) -> int:
    """Depth = number of nested boolean-group levels. A leaf contributes 0 extra."""
    if "op" in node:
        child_depths = [_tree_depth(c, _depth + 1) for c in node.get("conditions", []) if isinstance(c, dict)]
        return max([_depth] + child_depths)
    return _depth - 1  # a bare leaf at top is depth 0


FIXTURES = _load()


def test_suite_is_not_empty_and_has_the_two_anchors() -> None:
    ids = {f["jd_id"] for f in FIXTURES}
    assert "epiq_product_owner" in ids
    assert "python_backend_hyderabad" in ids


@pytest.mark.parametrize("fx", FIXTURES, ids=[f["jd_id"] for f in FIXTURES])
def test_fixture_is_well_formed(fx: Dict[str, Any]) -> None:
    for key in ("jd_id", "raw_brief", "archetype", "role_family", "logical_intent",
                "requirements", "expected_title_family", "expected_filter_tree"):
        assert key in fx, f"{fx['_file']}: missing '{key}'"

    assert fx["archetype"]["value"] in VALID_ARCHETYPES, f"{fx['_file']}: bad archetype"
    assert isinstance(fx["archetype"].get("confidence"), str) and fx["archetype"].get("rationale"), \
        f"{fx['_file']}: archetype must carry confidence + rationale (fallible LLM classification)"
    assert fx["role_family"], f"{fx['_file']}: empty role_family"


@pytest.mark.parametrize("fx", FIXTURES, ids=[f["jd_id"] for f in FIXTURES])
def test_every_requirement_is_routed(fx: Dict[str, Any]) -> None:
    for req in fx["requirements"]:
        assert req.get("strength") in VALID_STRENGTHS, f"{fx['_file']}: bad strength on {req.get('name')!r}"
        assert req.get("routing") in VALID_ROUTINGS, f"{fx['_file']}: bad routing on {req.get('name')!r}"
        # The honesty guard: a preferred company-type signal must never silently
        # claim a provider boost (NL injection was proven inert).
        if req.get("type") == "company" and req.get("strength") == "preferred":
            assert req.get("routing") in {"context_or_evidence", "disclose"}, \
                f"{fx['_file']}: preferred company must not pretend to be a provider boost"


@pytest.mark.parametrize("fx", FIXTURES, ids=[f["jd_id"] for f in FIXTURES])
def test_logical_intent_respects_two_level_cap(fx: Dict[str, Any]) -> None:
    li = fx["logical_intent"]
    assert set(li.keys()) <= {"all_of", "any_of"}, f"{fx['_file']}: top logical_intent must be all_of/any_of"
    groups = li.get("all_of", []) + li.get("any_of", [])
    for g in groups:
        if "group" in g:
            inner = g["group"]
            assert set(inner.keys()) <= {"all_of", "any_of"}, f"{fx['_file']}: group must be all_of/any_of"
            for leaf in inner.get("all_of", []) + inner.get("any_of", []):
                assert "group" not in leaf, f"{fx['_file']}: nesting exceeds two levels (scoping guard)"


@pytest.mark.parametrize("fx", FIXTURES, ids=[f["jd_id"] for f in FIXTURES])
def test_expected_filter_tree_is_structurally_valid_and_shallow(fx: Dict[str, Any]) -> None:
    tree = fx["expected_filter_tree"]
    assert tree.get("op") in {"and", "or"}, f"{fx['_file']}: root must be a boolean group"

    def walk(node: Dict[str, Any]) -> None:
        if "op" in node:
            assert node["op"] in {"and", "or"}
            assert node.get("conditions"), f"{fx['_file']}: empty group"
            for c in node["conditions"]:
                walk(c)
        else:
            assert LEAF_KEYS <= set(node.keys()), f"{fx['_file']}: leaf missing field/type/value: {node}"

    walk(tree)
    # Provider filter trees may nest one OR-group inside the root AND — depth 2.
    assert _tree_depth(tree) <= 2, f"{fx['_file']}: filter tree deeper than two levels"
