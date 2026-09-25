"""Rebuild the candidate-record data for a stored search, locally, so the record can be reviewed without the live site.

    python -m backend.experiments.record_preview output/record_preview/toronto_search.json --intent output/record_preview/toronto_intent.json

It reads a saved search record (a file from output/searches/, or a copy downloaded from the server), re-runs the
CURRENT evidence and explanation code on the stored candidates, stored profile reads and stored requirement
judgments, and writes frontend/src/preview-data/response.json (git-ignored, and outside public/ so it can never be copied into a production build). No network calls, no OpenAI, no CrustData, no
Harvest. Then run the frontend dev server and open /preview.html.

Search records do not store the search intent. Pass --intent (a SearchIntent JSON) to get the level and experience
lines; without it the requirements are recovered from the stored judgments and those two lines are simply absent."""

import argparse
import dataclasses
import json
from pathlib import Path
from typing import Any, Dict, List

from pydantic import TypeAdapter

from backend.models.candidate import Candidate
from backend.models.candidate_evidence import HarvestEvidence
from backend.models.search_intent import SearchIntent
from backend.services.candidate_evidence_builder import build_candidate_evidence
from backend.services.match_explainer import MatchExplainer

OUT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "preview-data" / "response.json"


def intent_from_judgments(candidates: List[Candidate]) -> SearchIntent:
    """Recover the requirement lists (in order) from the stored judgments when no intent file is given."""
    intent = SearchIntent()
    seen = {"core": [], "supporting": [], "differentiator": []}
    for candidate in candidates:
        for judgment in (candidate.raw_data or {}).get("__requirement_judgments") or []:
            tier, text = judgment.get("tier"), judgment.get("signal_text")
            if tier in seen and text and text not in seen[tier]:
                seen[tier].append(text)
    intent.core_signals, intent.supporting_signals, intent.differentiator_signals = seen["core"], seen["supporting"], seen["differentiator"]
    return intent


def build_response(record: Dict[str, Any], intent: SearchIntent | None) -> Dict[str, Any]:
    stored = (record.get("response") or {}).get("candidates") or []
    candidates = [Candidate(**item) for item in stored]
    intent = intent or intent_from_judgments(candidates)
    harvest = {cid: HarvestEvidence(**payload) for cid, payload in (record.get("harvest_evidence") or {}).items()}
    explainer = MatchExplainer()
    response = {
        "provider": "platform",
        "search_id": record.get("search_id", "preview"),
        "candidate_count": len(candidates),
        "candidates": [c.model_dump() for c in candidates],
        "explanations": [explainer.explain(c, intent, harvest_evidence=harvest.get(c.candidate_id)).model_dump() for c in candidates],
        "evidence": [dataclasses.asdict(build_candidate_evidence(c, intent, harvest_evidence=harvest.get(c.candidate_id))) for c in candidates],
        "diagnostics": {},
        "status": "complete",
        "candidate_states": {c.candidate_id: "review_ready" for c in candidates},
    }
    for item in response["candidates"]:
        item["raw_data"] = {}      # the record does not need the raw provider item
    return response


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("record", help="a saved search record (.json)")
    parser.add_argument("--intent", help="a SearchIntent JSON for this search (optional)")
    args = parser.parse_args()
    record = json.loads(Path(args.record).read_text(encoding="utf-8"))
    intent = TypeAdapter(SearchIntent).validate_python(json.loads(Path(args.intent).read_text(encoding="utf-8"))) if args.intent else None
    response = build_response(record, intent)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(response, default=str, ensure_ascii=False), encoding="utf-8")
    judged = sum(1 for e in response["evidence"] if e.get("requirement_judgments"))
    print(f"Wrote {OUT}\n  {response['candidate_count']} candidates, {judged} with a requirement ledger. Now run: cd frontend && npm run dev  ->  http://localhost:5173/preview.html")


if __name__ == "__main__":
    main()
