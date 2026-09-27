"""How large is the search the provider returned? A search-universe signal, never a count of qualified candidates.

Kept apart from candidate evidence on purpose: "50 profiles returned, 3 with strong evidence" says nothing about how
many suitable people exist. The recruiter is told what the provider returned and nothing more.
"""

from typing import Any, Dict, Optional

from backend.services.role_lifecycle import NARROW_UNIVERSE

ZERO = "zero"
NARROW = "narrow"
OK = "ok"


def availability(provider_total: Optional[int], retrieved: int) -> Dict[str, Any]:
    """`provider_total` is the size of the pool that passed the query's hard filters when the provider reported it;
    otherwise the profiles actually retrieved are used. Either way it is described as profiles returned."""
    universe = provider_total if isinstance(provider_total, (int, float)) and provider_total >= 0 else retrieved
    universe = int(max(universe, retrieved)) if retrieved else int(universe)
    if universe == 0:
        kind = ZERO
    elif universe < NARROW_UNIVERSE:
        kind = NARROW
    else:
        kind = OK
    return {"kind": kind, "profiles_returned": universe, "retrieved": retrieved}
