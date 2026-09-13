"""A small TTL cache on disk.

Vendor quotas are the binding constraint on a wealth product's data bill, and
the access pattern is extremely cacheable: thousands of users hold the same two
hundred funds. One file per key, JSON, atomically replaced.

Deliberately not an in-memory cache: the API runs as several processes and, on
a serverless deployment, as several short-lived ones. A cache that dies with
the process would cache almost nothing.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class Cache:
    directory: Path
    default_ttl: int = 900                   # 15 minutes suits intraday quotes

    def __post_init__(self) -> None:
        self.directory = Path(self.directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()[:24]
        return self.directory / f"{digest}.json"

    def get(self, key: str, *, ttl: int | None = None) -> Any | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        age = time.time() - payload.get("stored_at", 0)
        if age > (self.default_ttl if ttl is None else ttl):
            return None
        return payload.get("value")

    def get_stale(self, key: str) -> tuple[Any | None, float]:
        """Return a value regardless of age, with its age in seconds.

        Used when a provider is unreachable: an hour-old price marked stale is
        far more useful than no price, as long as the staleness travels with it.
        """
        path = self._path(key)
        if not path.exists():
            return None, 0.0
        try:
            payload = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None, 0.0
        return payload.get("value"), time.time() - payload.get("stored_at", 0)

    def put(self, key: str, value: Any) -> None:
        path = self._path(key)
        payload = {"key": key, "stored_at": time.time(), "value": value}
        # Atomic replace: a half-written cache file read by another process is
        # a corrupt price, which is the one failure mode worth engineering out.
        handle, temporary = tempfile.mkstemp(dir=str(self.directory), suffix=".tmp")
        try:
            with os.fdopen(handle, "w") as stream:
                json.dump(payload, stream, default=str)
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def fetch(self, key: str, producer: Callable[[], Any], *, ttl: int | None = None) -> Any:
        hit = self.get(key, ttl=ttl)
        if hit is not None:
            return hit
        value = producer()
        if value is not None:
            self.put(key, value)
        return value

    def clear(self) -> int:
        count = 0
        for path in self.directory.glob("*.json"):
            path.unlink(missing_ok=True)
            count += 1
        return count
