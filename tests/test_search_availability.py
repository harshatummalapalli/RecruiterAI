"""Search availability is what the provider RETURNED, never a count of qualified candidates."""

from backend.services.search_availability import NARROW, OK, ZERO, availability


def test_zero_profiles() -> None:
    assert availability(0, 0) == {"kind": ZERO, "profiles_returned": 0, "retrieved": 0}
    assert availability(None, 0)["kind"] == ZERO


def test_fewer_than_fifty_is_narrow() -> None:
    result = availability(12, 12)
    assert result["kind"] == NARROW and result["profiles_returned"] == 12
    assert availability(49, 49)["kind"] == NARROW


def test_fifty_or_more_is_not_narrow() -> None:
    assert availability(50, 50)["kind"] == OK
    assert availability(110577, 50)["kind"] == OK


def test_without_a_provider_total_the_retrieved_profiles_are_used() -> None:
    assert availability(None, 30) == {"kind": NARROW, "profiles_returned": 30, "retrieved": 30}
    assert availability(None, 50)["kind"] == OK


def test_the_universe_is_never_smaller_than_what_was_actually_retrieved() -> None:
    assert availability(10, 30)["profiles_returned"] == 30


def test_the_result_never_calls_the_count_qualified_candidates() -> None:
    assert set(availability(12, 12)) == {"kind", "profiles_returned", "retrieved"}
