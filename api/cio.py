"""Vercel serverless entry point for the Personal AI CIO API.

Read-only, on purpose, and for a reason specific to this product rather than a
general aversion to writes.

Vercel's filesystem is ephemeral and per-invocation. A write here would appear
to succeed, return 200, and vanish when the container recycles. For a carbon
ledger that is bad; for a wealth product it is worse -- a user who approves a
recommendation and finds no record of it afterwards has learned something about
the product that no amount of later correctness undoes. So every write returns
503 with the reason and the fix rather than pretending.

Making writes real needs durable storage behind the store (Postgres, Turso, or
any managed SQLite) or the API running on a host with a real disk. Until then
this deployment is a public read surface over a committed demo portfolio:
analysis, allocation, X-ray, actions, goals, risk, tax and reports.
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

from aicio.api import dispatch                          # noqa: E402
from aicio.store import Store                           # noqa: E402

BUNDLED_DB = ROOT / "aicio_dashboard" / "demo.db"
#: /tmp is the only writable path on Vercel. The store runs migrations on open,
#: so it needs a writable copy even though nothing here will write data.
RUNTIME_DB = Path(os.environ.get("AICIO_DB", "/tmp/aicio.db"))

WRITE_REFUSED = {
    "error": "this deployment is read-only",
    "reason": (
        "Serverless storage here is ephemeral, so an import or an approval "
        "would look like it succeeded and then disappear. For a record of "
        "someone's money, refusing is the honest answer."
    ),
    "fix": (
        "Point the store at durable storage (Postgres, Turso, or managed "
        "SQLite), or run `python -m aicio serve` on a host with a real disk."
    ),
}

_store: Store | None = None


def get_store() -> Store:
    """Open the demo database, copying it somewhere writable on cold start."""
    global _store
    if _store is None:
        if not RUNTIME_DB.exists():
            RUNTIME_DB.parent.mkdir(parents=True, exist_ok=True)
            if BUNDLED_DB.exists():
                shutil.copy(BUNDLED_DB, RUNTIME_DB)
        _store = Store(RUNTIME_DB, actor="readonly")
        if not _store.connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            _seed(_store)
    return _store


def _seed(store: Store) -> None:
    """Populate the demo portfolio if no database was bundled.

    Keeps the deployment self-healing: a cold container with no committed
    database still serves a complete, correct demo rather than 404s.
    """
    from aicio.seed import demo_bundle

    bundle = demo_bundle()
    store.save_user(bundle["user"])
    store.save_profile(bundle["profile"])
    store.save_policy(bundle["policy"])
    store.save_goals(bundle["goals"])
    store.save_portfolio(bundle["portfolio"])


def resolve(raw_path: str) -> tuple[str, dict]:
    """Undo the vercel.json rewrite to recover the route the caller asked for.

    The rewrite sends everything here and passes the original tail as ``p``, so
    ``/cio/api/users/x/xray`` arrives as ``/api/cio?p=users/x/xray``.
    """
    parsed = urlparse(raw_path)
    query = parse_qs(parsed.query)
    tail = query.pop("p", [""])[0].strip("/")
    path = "/api/" + tail if tail else "/api/health"
    return path, {k: v[0] for k, v in query.items()}


class handler(BaseHTTPRequestHandler):
    server_version = "aicio"

    def log_message(self, fmt, *args):
        pass  # Vercel captures stdout; the default access log is noise

    def _send(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload, indent=2, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "public, max-age=60")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        path, query = resolve(self.path)
        try:
            status, payload = dispatch(get_store(), "GET", path, query, {})
        except Exception as exc:                          # pragma: no cover
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if path == "/api/health":
            # Say up front that this is a read surface, so nobody discovers it
            # by having a write silently do nothing.
            payload["mode"] = "read-only"
            payload["writes"] = WRITE_REFUSED["reason"]
        self._send(status, payload)

    def do_POST(self) -> None:
        path, _ = resolve(self.path)
        self._send(503, {**WRITE_REFUSED, "path": path})

    do_DELETE = do_POST

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()
