"""Verified experience floor — derived from the candidate's own dated roles,
not CrustData's `years_of_experience_raw` (which can be inflated or ignored by
the hybrid search, letting juniors leak past a min-years filter).

Sums the time covered by dated employment, merging overlaps so concurrent roles
aren't double-counted; a current role runs to today; undated/open past roles are
skipped (not guessed). Returns None when there are no usable dates — unknown,
never treated as below-floor.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, List, Optional, Tuple

from recruiter.candidates import CandidateRecord


def _parse(value: Any) -> Optional[date]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


def derived_years(record: CandidateRecord, today: Optional[date] = None) -> Optional[float]:
    raw = record.raw if isinstance(record.raw, dict) else {}
    details = ((raw.get("experience") or {}).get("employment_details") or {}) if isinstance(raw.get("experience"), dict) else {}
    today = today or date.today()
    intervals: List[Tuple[date, date]] = []

    for role in details.get("current") or []:
        start = _parse(role.get("start_date")) if isinstance(role, dict) else None
        if start and start <= today:
            intervals.append((start, today))
    for role in details.get("past") or []:
        if not isinstance(role, dict):
            continue
        start, end = _parse(role.get("start_date")), _parse(role.get("end_date"))
        if start and end and start <= end:
            intervals.append((start, end))

    if not intervals:
        return None
    intervals.sort()
    merged = [list(intervals[0])]
    for start, end in intervals[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return round(sum((end - start).days for start, end in merged) / 365.25, 1)


def below_floor(record: CandidateRecord, min_years: Optional[int]) -> bool:
    """True only when the minimum is set AND the candidate's dated experience is
    known AND clearly below it. Unknown dates are kept (conservative)."""
    if not min_years:
        return False
    years = derived_years(record)
    return years is not None and years < min_years
