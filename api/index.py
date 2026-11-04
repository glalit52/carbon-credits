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

A few POSTs are served, all computing without storing: /api/estimate (a
farm's credit estimate), /api/forecast (a project's forward delivery),
/api/sensors (a water-logger file, scored against the radar), /api/scenes
(the Sentinel catalogue over a farm) and /api/reconcile (issued vintages
against a registry export). They need CARBONSTACK_ENGINE_TOKEN set here and
sent as a bearer token: some fetch on the caller's behalf, and all cost real
CPU.
"""

from __future__ import annotations

import hmac
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

#: POST routes that compute without writing, so this deployment can serve them.
STATELESS_POSTS = {"/api/estimate", "/api/forecast", "/api/sensors", "/api/scenes",
                   "/api/reconcile"}
MAX_BODY = 4_000_000

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

    def _send(self, status: int, payload: dict, *, cache: bool = True) -> None:
        raw = json.dumps(payload, indent=2, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "public, max-age=60" if cache else "no-store")
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
        path, query = resolve(self.path)
        if path not in STATELESS_POSTS:
            self._send(503, {**WRITE_REFUSED, "path": path})
            return
        # The estimate fetches weather on the caller's behalf, so it is not
        # left open to the internet: the web app's server holds the token.
        token = os.environ.get("CARBONSTACK_ENGINE_TOKEN")
        if not token:
            self._send(503, {"error": "estimates are disabled",
                             "fix": "set CARBONSTACK_ENGINE_TOKEN on this deployment"})
            return
        if not hmac.compare_digest(self.headers.get("Authorization", ""), f"Bearer {token}"):
            self._send(401, {"error": "bearer token required"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._send(413, {"error": f"request body over {MAX_BODY} bytes"})
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as exc:
            self._send(400, {"error": f"body is not JSON ({exc})"})
            return
        try:
            status, payload = dispatch(get_store(), "POST", path, query, body)
        except Exception as exc:                           # pragma: no cover
            self._send(500, {"error": str(exc)})
            return
        self._send(status, payload, cache=False)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()
