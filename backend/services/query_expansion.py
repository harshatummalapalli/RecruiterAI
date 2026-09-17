import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.models.search_plan import SearchPlan, SearchQuery
from backend.utils.text import deduplicate_preserve_order, normalize_text


class QueryExpansionService:
    """Expand SearchQuery values using provider-agnostic knowledge dictionaries."""

    def __init__(self, knowledge_dir: Optional[Path | str] = None):
        self.knowledge_dir = Path(knowledge_dir or Path(__file__).resolve().parents[1] / "knowledge")

    def expand(self, plan: SearchPlan) -> SearchPlan:
        expanded_searches: List[SearchQuery] = []
        for query in plan.searches:
            expanded_searches.append(self._expand_query(query))
        return SearchPlan(
            searches=expanded_searches,
            strategy=plan.strategy,
            reasoning=plan.reasoning,
            confidence_score=plan.confidence_score,
        )

    def _expand_query(self, query: SearchQuery) -> SearchQuery:
        # Skill expansion was deliberately removed: backend/knowledge/skills.json
        # mapped e.g. "Python" -> ["Python 3", "PySpark"], silently turning a
        # recruiter-stated requirement into an unstated one. Never re-add
        # skill expansion here without the recruiter/JD explicitly naming the
        # added skill — see the V0.1 discovery architecture notes.
        knowledge = self._load_knowledge()
        expanded_query = query.model_copy(deep=True)

        expanded_query.include_titles = self._expand_values(query.include_titles, knowledge.get("titles", {}))
        expanded_query.exclude_titles = self._expand_values(query.exclude_titles, knowledge.get("titles", {}))

        if query.minimum_years is not None:
            expanded_query.minimum_years = query.minimum_years

        if query.maximum_years is not None:
            expanded_query.maximum_years = query.maximum_years

        if query.work_mode:
            expanded_query.work_mode = self._expand_seniority(query.work_mode, knowledge.get("seniority", {}))

        return expanded_query

    def _load_knowledge(self) -> Dict[str, Dict[str, List[str]]]:
        data: Dict[str, Dict[str, List[str]]] = {
            "titles": {},
            "skills": {},
            "seniority": {},
        }
        for key in data:
            file_path = self.knowledge_dir / f"{key}.json"
            if file_path.exists():
                parsed = json.loads(file_path.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    data[key] = parsed
        return data

    def _expand_values(self, values: List[str], mapping: Dict[str, List[str]]) -> List[str]:
        expanded: List[str] = []
        for value in values:
            if not value:
                continue
            if value not in expanded:
                expanded.append(value)

        for value in values:
            if not value:
                continue
            if value in mapping:
                for variant in mapping[value]:
                    if variant and variant not in expanded:
                        expanded.append(variant)
        return self._deduplicate_preserve_order(expanded)

    def _expand_seniority(self, value: str, mapping: Dict[str, List[str]]) -> str:
        if value in mapping:
            variants = mapping[value]
            if variants:
                return variants[0]
        return value

    def _deduplicate_preserve_order(self, values: List[str]) -> List[str]:
        return deduplicate_preserve_order(values)
