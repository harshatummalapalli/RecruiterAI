"""Enricher backed by the keeper Harvest service.

Reads the deep profile and stashes (a) a text blob for the regex-coverage
signal and (b) the raw HarvestEvidence for the Judge to cite. Lazy backend
import; no-op when the candidate has no profile URL.
"""

from __future__ import annotations

from recruiter.candidates import CandidateRecord


def _harvest_text(evidence) -> str:
    if not getattr(evidence, "success", False) or not isinstance(getattr(evidence, "raw", None), dict):
        return ""
    element = evidence.raw.get("element") or {}
    parts = []
    for entry in element.get("experience") or []:
        if isinstance(entry, dict) and entry.get("description"):
            parts.append(str(entry["description"]))
    if element.get("about"):
        parts.append(str(element["about"]))
    for skill in element.get("topSkills") or []:
        if isinstance(skill, str):
            parts.append(skill)
    return " ".join(parts)


class HarvestAdapter:
    def __init__(self, service=None) -> None:
        self._service = service

    def _get(self):
        if self._service is None:
            from backend.providers.harvest import HarvestEnrichmentService
            self._service = HarvestEnrichmentService()
        return self._service

    def enrich(self, record: CandidateRecord) -> None:
        if not record.profile_url:
            return
        from backend.models.candidate import Candidate

        candidate = Candidate(candidate_id=record.candidate_id, profile_url=record.profile_url, raw_data=record.raw)
        evidence = self._get()._fetch_one(candidate)
        record.raw["_harvest_evidence"] = evidence
        record.raw["_enriched_text"] = _harvest_text(evidence)
