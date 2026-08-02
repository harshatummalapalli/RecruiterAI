from typing import Iterable, List, Optional, Sequence, TypeVar

T = TypeVar("T")


def normalize_text(value: Optional[str]) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def normalize_text_values(values: Iterable[Optional[str]]) -> List[str]:
    normalized: List[str] = []
    for value in values:
        if value is None:
            continue
        normalized.append(str(value).strip())
    return normalized


def deduplicate_preserve_order(values: Iterable[Optional[str]]) -> List[str]:
    seen = set()
    deduped: List[str] = []
    for value in values:
        if value is None:
            continue
        normalized = normalize_text(value)
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(str(value))
    return deduped


def deduplicate_preserve_order_with_strings(values: Iterable[str]) -> List[str]:
    return deduplicate_preserve_order(values)


def contains_normalized_text(haystack: Optional[str], needles: Sequence[str]) -> bool:
    normalized_haystack = normalize_text(haystack)
    return any(normalize_text(needle) in normalized_haystack for needle in needles if needle)


def equals_normalized_text(left: Optional[str], right: Optional[str]) -> bool:
    return normalize_text(left) == normalize_text(right)
