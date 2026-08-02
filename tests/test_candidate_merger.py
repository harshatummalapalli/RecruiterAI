from backend.models.candidate import Candidate
from backend.services.candidate_merger import CandidateMerger


def test_merge_deduplicates_by_profile_url() -> None:
    candidates = [
        Candidate(name="Alice", company="OpenAI", profile_url="https://example.com/alice", provider_score=0.9, final_score=9.0, raw_data={"matched_queries": ["Primary"]}),
        Candidate(name="Alice", company="OpenAI", profile_url="https://example.com/alice", provider_score=0.95, final_score=9.5, raw_data={"matched_queries": ["Alternate 1"]}),
    ]

    merged = CandidateMerger().merge(candidates)

    assert len(merged) == 1
    assert merged[0].provider_score == 0.95
    assert merged[0].final_score == 9.5
    assert merged[0].raw_data["matched_queries"] == ["Primary", "Alternate 1"]


def test_merge_deduplicates_by_email() -> None:
    candidates = [
        Candidate(name="Bob", company="Anthropic", email="bob@example.com", provider_score=0.8, raw_data={"matched_queries": ["Primary"]}),
        Candidate(name="Bob", company="Anthropic", email="bob@example.com", provider_score=0.9, raw_data={"matched_queries": ["Alternate 1"]}),
    ]

    merged = CandidateMerger().merge(candidates)

    assert len(merged) == 1
    assert merged[0].provider_score == 0.9
    assert merged[0].raw_data["matched_queries"] == ["Primary", "Alternate 1"]


def test_merge_deduplicates_by_normalized_name_and_company() -> None:
    candidates = [
        Candidate(name="Carol", company="Acme", provider_score=0.7, raw_data={"matched_queries": ["Primary"]}),
        Candidate(name="carol", company="ACME", provider_score=0.8, raw_data={"matched_queries": ["Alternate 1"]}),
    ]

    merged = CandidateMerger().merge(candidates)

    assert len(merged) == 1
    assert merged[0].provider_score == 0.8
    assert merged[0].raw_data["matched_queries"] == ["Primary", "Alternate 1"]
