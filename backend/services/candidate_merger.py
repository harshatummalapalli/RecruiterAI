from typing import Any, Dict, List, Optional, Tuple

from backend.models.candidate import Candidate
from backend.utils.text import normalize_text


class CandidateMerger:
    """Merge duplicate candidates while preserving the strongest available metadata."""

    def merge(self, candidates: List[Candidate]) -> List[Candidate]:
        merged: List[Candidate] = []
        seen_keys: set[Tuple[Optional[str], Optional[str], Optional[str]]] = set()

        for candidate in candidates:
            key = self._deduplication_key(candidate)
            if key is None:
                merged.append(candidate)
                continue

            existing_index = self._find_existing_index(merged, key)
            if existing_index is None:
                merged.append(candidate)
                continue

            merged[existing_index] = self._merge_candidate(merged[existing_index], candidate)

        return merged

    def _deduplication_key(self, candidate: Candidate) -> Optional[Tuple[Optional[str], Optional[str], Optional[str]]]:
        if candidate.profile_url:
            return ("profile_url", candidate.profile_url, None)
        if candidate.email:
            return ("email", candidate.email, None)
        if candidate.name or candidate.company:
            normalized_name = normalize_text(candidate.name)
            normalized_company = normalize_text(candidate.company)
            return ("name_company", normalized_name, normalized_company)
        return None

    def _find_existing_index(self, merged: List[Candidate], key: Tuple[Optional[str], Optional[str], Optional[str]]) -> Optional[int]:
        for index, candidate in enumerate(merged):
            candidate_key = self._deduplication_key(candidate)
            if candidate_key == key:
                return index
        return None

    def _merge_candidate(self, existing: Candidate, incoming: Candidate) -> Candidate:
        merged_data = existing.raw_data.copy()
        if isinstance(incoming.raw_data, dict):
            merged_data.update(incoming.raw_data)

        if "matched_queries" in existing.raw_data or "matched_queries" in incoming.raw_data:
            merged_data["matched_queries"] = self._merge_matched_queries(existing, incoming)

        provider_score = self._max_value(existing.provider_score, incoming.provider_score)
        final_score = self._max_value(existing.final_score, incoming.final_score)

        merged_candidate = Candidate(
            candidate_id=existing.candidate_id or incoming.candidate_id,
            name=existing.name or incoming.name,
            title=existing.title or incoming.title,
            company=existing.company or incoming.company,
            location=existing.location or incoming.location,
            email=existing.email or incoming.email,
            phone=existing.phone or incoming.phone,
            provider_score=provider_score,
            final_score=final_score,
            profile_url=existing.profile_url or incoming.profile_url,
            source=self._merge_sources(existing.source, incoming.source),
            raw_data=merged_data,
        )

        if hasattr(existing, "matched_queries") or hasattr(incoming, "matched_queries"):
            merged_candidate.raw_data["matched_queries"] = self._merge_matched_queries(existing, incoming)

        return merged_candidate

    def _merge_sources(self, existing: Optional[str], incoming: Optional[str]) -> Optional[str]:
        if not existing:
            return incoming
        if not incoming:
            return existing
        return f"{existing},{incoming}"

    def _merge_matched_queries(self, existing: Candidate, incoming: Candidate) -> List[str]:
        queries: List[str] = []
        for query in [existing.raw_data.get("matched_queries", []), incoming.raw_data.get("matched_queries", [])]:
            if isinstance(query, list):
                queries.extend([q for q in query if isinstance(q, str)])
        return queries

    def _max_value(self, first: Optional[float], second: Optional[float]) -> Optional[float]:
        values = [value for value in [first, second] if value is not None]
        if not values:
            return None
        return max(values)
