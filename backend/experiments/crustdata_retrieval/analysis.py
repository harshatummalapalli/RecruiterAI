"""Pure comparison functions for the NL-vs-structured experiment. Descriptive
only: nothing here claims causation or treats `fit` as a numeric score."""

import statistics
from typing import Any, Dict, List, Optional

# Ordinal encoding used ONLY to compute a descriptive rank correlation.
FIT_ORDER = {"weak": 0, "possible": 1, "strong": 2}


def overlap(a_ids: List[str], b_ids: List[str]) -> Dict[str, Any]:
    a, b = set(a_ids), set(b_ids)
    inter, union = a & b, a | b
    return {
        "a_count": len(a),
        "b_count": len(b),
        "intersection": len(inter),
        "a_only": len(a - b),
        "b_only": len(b - a),
        "union": len(union),
        "jaccard": round(len(inter) / len(union), 3) if union else None,
        "overlap_pct_of_a": round(100 * len(inter) / len(a), 1) if a else None,
        "overlap_pct_of_b": round(100 * len(inter) / len(b), 1) if b else None,
    }


def fit_distribution(rows: List[Dict[str, Any]], top_k: Optional[int] = None) -> Dict[str, int]:
    """Counts of strong/possible/weak/missing among the first `top_k` rows in
    PROVIDER order (all rows when top_k is None)."""
    subset = sorted(rows, key=lambda r: r["provider_position"])[:top_k] if top_k else rows
    out = {"strong": 0, "possible": 0, "weak": 0, "missing": 0}
    for row in subset:
        fit = row.get("fit")
        out[fit if fit in FIT_ORDER else "missing"] += 1
    return out


def _ranks(values: List[float]) -> List[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2
        i = j + 1
    return ranks


def spearman(x: List[float], y: List[float]) -> Optional[float]:
    if len(x) < 3 or len(set(x)) < 2 or len(set(y)) < 2:
        return None
    rx, ry = _ranks(x), _ranks(y)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return round(num / den, 3) if den else None


def fit_position_correlation(rows: List[Dict[str, Any]]) -> Optional[float]:
    """Spearman between provider position and ordinal fit. Negative means
    higher fit tends to sit at earlier (smaller) positions. Rows without a
    recognised fit are excluded; None when fit does not vary."""
    pairs = [(r["provider_position"], FIT_ORDER[r["fit"]]) for r in rows if r.get("fit") in FIT_ORDER]
    return spearman([p for p, _ in pairs], [f for _, f in pairs])


def preserves_provider_order(rows: List[Dict[str, Any]]) -> bool:
    return [r["provider_position"] for r in rows] == list(range(1, len(rows) + 1))
