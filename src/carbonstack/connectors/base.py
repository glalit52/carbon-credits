"""How outside data gets in, and what it has to carry when it does.

Every external number this product uses -- a month of rainfall, a clay
fraction, the list of Sentinel-1 scenes over a plot, a registry's issuance
record -- ends up inside a derivation that a verifier reads. So a connector's
job is not only to fetch. It is to fetch **in a way that can be repeated**:
the request that was made, when, and a hash of exactly what came back. A
weather series that cannot be re-retrieved and shown to match is, for audit,
a weather series somebody typed in.

Two rules follow, and both are enforced here rather than left to each
connector:

* **Every response is pinned.** `Snapshot` records the URL, the parameters,
  the retrieval time and a SHA-256 of the body. Derivations cite the hash.
* **Network is a transport, not a dependency.** The core stays stdlib-only
  and runs where there is no network at all. `UrllibTransport` talks to the
  internet; `ReplayTransport` serves the same requests from a directory of
  pinned responses, which is how tests run and how a VVB re-runs our numbers
  from the evidence pack without needing our API keys.

A connector that cannot reach its source raises `ConnectorUnavailable` with
the reason and the fix. It never falls back to a default value silently --
a default rainfall series dressed as a retrieved one is the worst outcome
this module can produce.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


class ConnectorUnavailable(RuntimeError):
    """The source could not be reached or did not answer usefully."""

    def __init__(self, connector: str, reason: str, fix: str = ""):
        self.connector = connector
        self.reason = reason
        self.fix = fix
        msg = f"{connector}: {reason}"
        if fix:
            msg += f" -- {fix}"
        super().__init__(msg)


@dataclass(frozen=True)
class Snapshot:
    """One response, pinned well enough to prove it later."""

    connector: str
    url: str
    params: tuple[tuple[str, str], ...]
    retrieved_at: str
    sha256: str
    body: bytes = field(repr=False, compare=False)
    replayed: bool = False

    @property
    def request_key(self) -> str:
        return request_key(self.url, dict(self.params))

    def json(self) -> Any:
        try:
            return json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ConnectorUnavailable(
                self.connector, f"response was not JSON ({exc})",
                "the source may be returning an error page; check the URL") from exc

    def text(self) -> str:
        return self.body.decode("utf-8-sig")

    def provenance(self) -> dict:
        """What a derivation cites. Small enough to embed everywhere."""
        return {
            "connector": self.connector,
            "url": self.url,
            "params": dict(self.params),
            "retrieved_at": self.retrieved_at,
            "sha256": self.sha256,
            "replayed": self.replayed,
        }

    def citation(self) -> str:
        return (f"{self.connector} {self.url} retrieved {self.retrieved_at} "
                f"sha256:{self.sha256[:16]}")


def request_key(url: str, params: dict[str, Any] | None = None,
                body: Any = None) -> str:
    """A stable name for a request, so a replay can find its response.

    Parameters are sorted, so two calls that differ only in dict order are the
    same request -- which they are. Values are compared as strings, because
    that is what goes on the wire and what a pinned response records.
    """
    canon = json.dumps({"url": url,
                        "params": sorted((k, str(v)) for k, v in (params or {}).items()),
                        "body": body}, sort_keys=True, default=str)
    return hashlib.sha256(canon.encode()).hexdigest()[:24]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Transport(Protocol):
    """Gets bytes for a request. Knows nothing about what they mean."""

    def fetch(self, connector: str, url: str, params: dict[str, Any] | None = None,
              *, body: Any = None) -> Snapshot:
        ...


class UrllibTransport:
    """The real network, through the standard library.

    `urllib` honours HTTPS_PROXY and the system CA bundle on its own, so this
    works behind a corporate proxy with no configuration here.
    """

    def __init__(self, *, timeout: float = 30.0, user_agent: str = "carbonstack/0.1",
                 headers: dict[str, str] | None = None):
        self.timeout = timeout
        self.headers = {"User-Agent": user_agent, "Accept": "application/json, text/csv, */*"}
        self.headers.update(headers or {})

    def fetch(self, connector: str, url: str, params: dict[str, Any] | None = None,
              *, body: Any = None) -> Snapshot:
        full = url
        if params:
            full += ("&" if "?" in url else "?") + urllib.parse.urlencode(
                sorted(params.items()), doseq=True)
        data = None
        headers = dict(self.headers)
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(full, data=data, headers=headers,
                                     method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = resp.read()
        except urllib.error.HTTPError as exc:
            raise ConnectorUnavailable(
                connector, f"HTTP {exc.code} from {url}",
                "check the request parameters and the source's status page") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ConnectorUnavailable(
                connector, f"could not reach {url} ({exc})",
                "check network policy, or replay pinned responses with --replay DIR") from exc
        return Snapshot(
            connector=connector, url=url,
            params=tuple(sorted((k, str(v)) for k, v in (params or {}).items())),
            retrieved_at=_now(), sha256=hashlib.sha256(payload).hexdigest(),
            body=payload)


class ReplayTransport:
    """Serves pinned responses from disk. No network, ever.

    Layout: `<root>/<connector>/<request_key>.json` holding
    `{"url", "params", "retrieved_at", "body"}`. The stored hash is
    recomputed on load and a mismatch is refused, because a pinned response
    that was edited after pinning is precisely what pinning exists to catch.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def path_for(self, connector: str, url: str, params: dict | None,
                 body: Any = None) -> Path:
        return self.root / connector / f"{request_key(url, params, body)}.json"

    def fetch(self, connector: str, url: str, params: dict[str, Any] | None = None,
              *, body: Any = None) -> Snapshot:
        path = self.path_for(connector, url, params, body)
        if not path.exists():
            raise ConnectorUnavailable(
                connector, f"no pinned response for this request ({path.name})",
                f"record one with a live run and --record {self.root}")
        rec = json.loads(path.read_text())
        payload = rec["body"].encode() if isinstance(rec["body"], str) else \
            json.dumps(rec["body"]).encode()
        digest = hashlib.sha256(payload).hexdigest()
        if rec.get("sha256") and rec["sha256"] != digest:
            raise ConnectorUnavailable(
                connector, f"pinned response {path.name} does not match its hash",
                "the file was edited after it was recorded; re-record it")
        return Snapshot(
            connector=connector, url=url,
            params=tuple(sorted((k, str(v)) for k, v in (params or {}).items())),
            retrieved_at=rec.get("retrieved_at", ""), sha256=digest,
            body=payload, replayed=True)


class RecordingTransport:
    """Wraps a live transport and pins everything it fetches.

    Run once with network, commit the directory, and every later run --
    tests, the evidence pack, a verifier's laptop -- replays it exactly.
    """

    def __init__(self, inner: Transport, root: str | Path):
        self.inner = inner
        self.root = Path(root)

    def fetch(self, connector: str, url: str, params: dict[str, Any] | None = None,
              *, body: Any = None) -> Snapshot:
        snap = self.inner.fetch(connector, url, params, body=body)
        pin(self.root, snap, body=body)
        return snap


def pin(root: str | Path, snap: Snapshot, *, body: Any = None) -> Path:
    """Write a snapshot where `ReplayTransport` will find it."""
    path = Path(root) / snap.connector / f"{request_key(snap.url, dict(snap.params), body)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = snap.body.decode("utf-8")
    path.write_text(json.dumps({
        "url": snap.url, "params": dict(snap.params),
        "retrieved_at": snap.retrieved_at, "sha256": snap.sha256, "body": text,
    }, indent=1))
    return path


def default_transport(replay: str | None = None, record: str | None = None) -> Transport:
    """Pick a transport from flags or the environment.

    `CARBONSTACK_REPLAY` points every connector at pinned responses, which
    is how the evidence pack and CI run without network.
    """
    replay = replay or os.environ.get("CARBONSTACK_REPLAY")
    if replay:
        return ReplayTransport(replay)
    live: Transport = UrllibTransport()
    record = record or os.environ.get("CARBONSTACK_RECORD")
    return RecordingTransport(live, record) if record else live
