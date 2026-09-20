import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_STORAGE_DIR = Path(__file__).resolve().parents[2] / "output" / "searches"


class SearchStore:
    """File-backed persistence for a search's full record.

    Deliberately simple (one JSON file per search_id) rather than a
    database — the requirement is "a refresh must not re-run OpenAI/
    CrustData," not high-concurrency multi-user storage. Survives server
    restarts, unlike an in-memory dict.
    """

    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        self.storage_dir = Path(storage_dir or DEFAULT_STORAGE_DIR)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, search_id: str) -> Path:
        safe_id = "".join(char for char in search_id if char.isalnum() or char in ("-", "_"))
        return self.storage_dir / f"{safe_id}.json"

    def save(self, search_id: str, record: Dict[str, Any]) -> None:
        # Re-ensured on every write, not just at construction — if the
        # directory is ever removed while the process is running (manual
        # cleanup, a deploy step, disk housekeeping), every subsequent save
        # would otherwise 500 until the process restarts.
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(search_id)
        path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
        logger.info("Persisted search record | search_id=%s path=%s", search_id, path)

    def load(self, search_id: str) -> Optional[Dict[str, Any]]:
        path = self._path(search_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            logger.exception("Failed to load persisted search | search_id=%s", search_id)
            return None
