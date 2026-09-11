"""Vercel serverless entry point for the carbonstack API.

Read-only, on purpose.

Vercel's filesystem is ephemeral and per-invocation: a write to SQLite here
would appear to succeed, return 200, and then vanish when the container is
recycled. A vintage that approves and then un-approves itself is far worse
than one that refuses to approve at all, so every write returns 503 with the
reason and the fix rather than pretending.

Making writes real needs durable storage behind the store — Postgres, Turso,
or any managed SQLite — or running the API on a host with a real disk. Until
then this deployment is a public read surface over a committed demo database:
projects, plots, eligibility, vintages, derivations, issuances, payments and
the event chain, all queryable.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carbonstack.api import dispatch          # noqa: E402
from carbonstack.store import Store           # noqa: E402

BUNDLED_DB = ROOT / "dashboard" / "pilot.db"
#: /tmp is the only writable path on Vercel. The store runs migrations on open,
#: so it needs a writable copy even though nothing here will write data.
RUNTIME_DB = Path(os.environ.get("CARBONSTACK_DB", "/tmp/carbonstack.db"))

WRITE_REFUSED = {
    "error": "this deployment is read-only",
    "reason": (
        "Serverless storage here is ephemeral, so a write would look like it "
        "succeeded and then disappear. Refusing is the honest answer."
    ),
    "fix": (
        "Point the store at durable storage (Postgres, Turso, or managed "
        "SQLite), or run `carbonstack serve` on a host with a real disk."
    ),
}

_store: Store | None = None


def get_store() -> Store:
    """Open the demo database, copying it somewhere writable on cold start."""
    global _store
    if _store is None:
        if not RUNTIME_DB.exists() and BUNDLED_DB.exists():
            RUNTIME_DB.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(BUNDLED_DB, RUNTIME_DB)
        _store = Store(RUNTIME_DB, actor="readonly")
    return _store


def resolve(raw_path: str) -> tuple[str, dict]:
    """Undo the vercel.json rewrite to recover the route the caller asked for.

    The rewrite sends everything to this one function and passes the original
    tail as `p`, so `/api/projects/X/vintages` arrives as
    `/api/index?p=projects/X/vintages`. We rebuild the real path and hand back
    whatever other query parameters came along.
    """
    parsed = urlparse(raw_path)
    query = parse_qs(parsed.query)
    tail = query.pop("p", [""])[0].strip("/")
    path = "/api/" + tail if tail else "/api/health"
    return path, query


class handler(BaseHTTPRequestHandler):
    server_version = "carbonstack"

    def log_message(self, fmt, *args):
        pass  # Vercel captures stdout; the default access log is noise

    def _send(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload, indent=2, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "public, max-age=60")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        path, query = resolve(self.path)
        if path == "/api/health":
            # Say up front that this is a read surface, so nobody discovers it
            # by having a write silently do nothing.
            try:
                status, payload = dispatch(get_store(), "GET", path, query, {})
            except Exception as exc:                       # pragma: no cover
                self._send(500, {"error": str(exc)})
                return
            payload["mode"] = "read-only"
            payload["writes"] = WRITE_REFUSED["reason"]
            self._send(status, payload)
            return

        try:
            status, payload = dispatch(get_store(), "GET", path, query, {})
        except Exception as exc:                           # pragma: no cover
            self._send(500, {"error": str(exc)})
            return
        self._send(status, payload)

    def do_POST(self) -> None:
        path, _ = resolve(self.path)
        self._send(503, {**WRITE_REFUSED, "path": path})

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()
