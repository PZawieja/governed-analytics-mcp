import hashlib
import json
import time
from dataclasses import dataclass, field


@dataclass
class AnswerCache:
    """Answer cache keyed by who asked, not only by what was asked.

    A cache hit never reaches the warehouse, so the warehouse never gets to apply
    the asker's policy. keyed_by="sql_only" is the bug from the post, kept only so
    the evals can show it leaking.
    """

    keyed_by: str = "asker"
    ttl_seconds: int = 300
    _entries: dict[str, tuple[float, object]] = field(default_factory=dict)

    def key(self, user_id: str, backend: str, sql: str, params: list) -> str:
        normalized = " ".join(sql.split()) + "|" + json.dumps(params, default=str)
        scope = user_id if self.keyed_by == "asker" else "*"
        return hashlib.sha256(f"{scope}|{backend}|{normalized}".encode()).hexdigest()

    def get(self, key: str):
        hit = self._entries.get(key)
        if hit is None or time.monotonic() - hit[0] > self.ttl_seconds:
            return None
        return hit[1]

    def put(self, key: str, value) -> None:
        self._entries[key] = (time.monotonic(), value)

    def clear(self) -> None:
        self._entries.clear()
