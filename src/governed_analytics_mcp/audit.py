import json
import threading
from datetime import UTC, datetime
from pathlib import Path


class AuditLog:
    def __init__(self, path: Path | None):
        self.path = path
        self._lock = threading.Lock()

    def write(self, **record) -> None:
        if self.path is None:
            return
        record = {"ts": datetime.now(UTC).isoformat(timespec="milliseconds"), **record}
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as f:
                f.write(json.dumps(record, default=str) + "\n")
