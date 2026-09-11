"""The Vercel entry point.

Its whole job is to undo a rewrite and refuse writes. Both are easy to break
silently -- a wrong path resolution turns every route into a 404, and a write
that stops being refused starts losing data -- so both are pinned here.
"""

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def adapter():
    spec = importlib.util.spec_from_file_location("vercel_api", ROOT / "api" / "index.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rewrite(path: str) -> str:
    """Apply vercel.json's rewrites the way Vercel would."""
    config = json.loads((ROOT / "vercel.json").read_text())
    for rule in config["rewrites"]:
        hit = re.match("^" + rule["source"] + "$", path.split("?")[0])
        if hit:
            dest = rule["destination"]
            for i, group in enumerate(hit.groups(), 1):
                dest = dest.replace(f"${i}", group)
            tail = path.split("?", 1)[1] if "?" in path else ""
            return dest + ("&" + tail if tail else "")
    return path


@pytest.mark.parametrize("asked,expected", [
    ("/api", "/api/health"),
    ("/api/projects", "/api/projects"),
    ("/api/projects/IN-TNJ-01", "/api/projects/IN-TNJ-01"),
    ("/api/projects/IN-TNJ-01/vintages", "/api/projects/IN-TNJ-01/vintages"),
    ("/api/vintages/IN-TNJ-01:2025/derivation", "/api/vintages/IN-TNJ-01:2025/derivation"),
    ("/api/integrity", "/api/integrity"),
])
def test_the_rewrite_round_trips_every_route(adapter, asked, expected):
    """Vercel funnels everything into one function, so the original route has
    to survive the trip. If it does not, every path 404s at once."""
    path, _ = adapter.resolve(rewrite(asked))
    assert path == expected


def test_other_query_parameters_survive_the_rewrite(adapter):
    path, query = adapter.resolve(rewrite("/api/events?limit=5&subject_type=vintage"))
    assert path == "/api/events"
    assert query["limit"] == ["5"]
    assert query["subject_type"] == ["vintage"]
    assert "p" not in query


def test_trailing_slashes_do_not_produce_a_different_route(adapter):
    assert adapter.resolve(rewrite("/api/projects/"))[0] == "/api/projects"


def test_every_api_route_survives_the_rewrite(adapter):
    """Checked against the real route table rather than a hand-written list,
    so a route added later cannot quietly become unreachable in production."""
    from carbonstack.api import _ROUTES

    for method, regex, _fn in _ROUTES:
        if method != "GET":
            continue
        sample = (regex.pattern[1:-1]
                  .replace("(?P<project_id>[^/]+)", "IN-TNJ-01")
                  .replace("(?P<vintage_id>[^/]+)", "IN-TNJ-01:2025")
                  .replace("(?P<payment_id>[^/]+)", "pay-1"))
        assert adapter.resolve(rewrite(sample))[0] == sample


def test_writes_are_refused_with_a_reason_and_a_fix(adapter):
    """Ephemeral storage would let a write return 200 and then vanish. A
    vintage that approves and then un-approves itself is worse than one that
    refuses, so the refusal has to stay."""
    refused = adapter.WRITE_REFUSED
    assert "read-only" in refused["error"]
    assert "ephemeral" in refused["reason"].lower()
    assert "Postgres" in refused["fix"] or "durable" in refused["fix"].lower()


def test_the_bundled_database_is_present_and_readable(adapter):
    """The deployment serves a committed database. If it stops being shipped,
    every route returns an empty project list instead of failing loudly."""
    assert adapter.BUNDLED_DB.exists(), (
        "dashboard/pilot.db is what the deployment serves; rebuild it with "
        "scripts/build_dashboard_data.py")
    store = adapter.get_store()
    assert len(store.list_projects()) >= 1
    assert store.verify_chain()[0] is True


def test_static_build_lists_what_it_publishes():
    """robots.txt disallows crawling: the packs contain farmer-level rows, and
    a demo deployment has no business being indexed."""
    script = (ROOT / "scripts" / "build_static.sh").read_text()
    assert "public/index.html" in script
    assert "Disallow: /" in script
