import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_STORAGE_DIR = Path(__file__).resolve().parents[2] / "output" / "searches"


class SearchStore:
    """File-backed persistence for a search's full record.

    Deliberately simple (one JSON file per search_id) rather than a
    database — the requirement is "a refresh must not re-run OpenAI/
    CrustData," not high-concurrency multi-user storage. Survives server
    restarts, unlike an in-memory dict.

    Since a search now runs on a background thread while the recruiter polls
    it and records decisions against it, two things are guaranteed here:
    * writes are ATOMIC (temp file + os.replace), so a reader can never see
      a half-written file (which used to read as "search not found" and
      silently stop the frontend's polling);
    * read-modify-write cycles run under one lock (see `update`), so a
      recruiter's shortlist decision and the pipeline's progress saves can
      never overwrite each other.
    """

    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        self.storage_dir = Path(storage_dir or DEFAULT_STORAGE_DIR)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        # Re-entrant so update() can call load()/save() while holding it.
        self.lock = threading.RLock()

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
        payload = json.dumps(record, indent=2, default=str)
        with self.lock:
            temp_path = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
            temp_path.write_text(payload, encoding="utf-8")
            os.replace(temp_path, path)
        logger.info("Persisted search record | search_id=%s path=%s", search_id, path)

    def load(self, search_id: str) -> Optional[Dict[str, Any]]:
        path = self._path(search_id)
        with self.lock:
            if not path.exists():
                return None
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                logger.exception("Failed to load persisted search | search_id=%s", search_id)
                return None

    def update(self, search_id: str, mutate: Callable[[Dict[str, Any]], None]) -> Optional[Dict[str, Any]]:
        """Load, apply `mutate` in place, save — atomically with respect to
        every other save/update on this store. Returns the saved record, or
        None if the search does not exist."""
        with self.lock:
            record = self.load(search_id)
            if record is None:
                return None
            mutate(record)
            self.save(search_id, record)
            return record
