#!/usr/bin/env python3
"""Is the committed dashboard still what the code produces?

The dashboard ships pre-built rather than generated at deploy time, which is
deliberate -- regenerating it inside a deploy would make the published page
depend on whatever the build container happens to have. The cost is that it
can silently drift from the code behind it, and this is the only thing that
would notice.

A plain `git diff` cannot do the job, because part of the payload is honestly
not reproducible. The governance section is read back from a **real** database
run, so it carries wall-clock timestamps, uuid4 identifiers, and event hashes
computed over both. Those differ on every run by design; that is what makes
the event chain worth anything.

So this compares the parts that must be stable -- readings, vintages,
economics, site metadata -- and normalises only the fields that cannot be:

  * timestamps written at run time
  * generated identifiers
  * hashes derived from either

Everything else is compared exactly, and the first real difference is printed
with its path so the failure says what changed rather than "files differ".
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMITTED = ROOT / "dashboard" / "data.json"
PAGE = ROOT / "dashboard" / "index.html"

#: Keys whose values come from the clock or a uuid. Matched by name at any
#: depth. Deliberately narrow: `day`, `enrolled_on`, `start` and `end` are NOT
#: here, because those are content and must match exactly.
VOLATILE_KEYS = {
    "generated_at",     # the as-of date, pinned on rebuild but stamped here
    "at",               # event time
    "hash", "head_hash", "prev_hash",
    "quantified_at",
    "issued_on",        # date.today() inside the ledger
    "due_on", "paid_on",
    "created_at",
}

#: Generated identifiers, recognised by prefix rather than by key path.
ID_PREFIXES = ("iss-", "pay-", "buf-")

PLACEHOLDER = "<volatile>"


def normalise(value):
    """Replace run-specific values so two honest runs compare equal."""
    if isinstance(value, dict):
        out = {}
        for key, inner in value.items():
            if key in VOLATILE_KEYS:
                out[key] = PLACEHOLDER
            elif key == "id" and isinstance(inner, str) \
                    and inner.startswith(ID_PREFIXES):
                out[key] = PLACEHOLDER
            else:
                out[key] = normalise(inner)
        return out
    if isinstance(value, list):
        return [normalise(v) for v in value]
    return value


def first_difference(a, b, path: str = "") -> str | None:
    """Where two payloads first disagree, as a readable path."""
    if type(a) is not type(b):
        return f"{path or '<root>'}: type changed, {type(a).__name__} -> {type(b).__name__}"
    if isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a:
                return f"{path}.{key}: added"
            if key not in b:
                return f"{path}.{key}: removed"
            hit = first_difference(a[key], b[key], f"{path}.{key}")
            if hit:
                return hit
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: length {len(a)} -> {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            hit = first_difference(x, y, f"{path}[{i}]")
            if hit:
                return hit
        return None
    if a != b:
        return f"{path}: {a!r} -> {b!r}"
    return None


def page_is_current(tmp: Path) -> str | None:
    """Is index.html what the template plus the committed data produce?

    Fully deterministic, unlike the data rebuild: both inputs are the files
    already in the tree. Without this, editing dashboard/template.html and
    forgetting to rebuild would ship a page nobody notices is out of date.
    """
    if not PAGE.exists():
        return "dashboard/index.html is missing"

    rebuilt = tmp / "index.html"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_dashboard.py")],
        env={**os.environ, "CARBONSTACK_PAGE_OUT": str(rebuilt)},
        capture_output=True, text=True)
    if proc.returncode != 0:
        return f"page rebuild failed: {proc.stderr.strip() or proc.stdout.strip()}"

    if rebuilt.read_text() != PAGE.read_text():
        return ("dashboard/index.html does not match dashboard/template.html "
                "plus the committed data")
    return None


def main() -> int:
    if not COMMITTED.exists():
        print(f"{COMMITTED} is missing; run scripts/build_dashboard_data.py",
              file=sys.stderr)
        return 1

    committed = json.loads(COMMITTED.read_text())
    as_of = committed.get("generated_at")
    if not as_of:
        print("committed data.json has no generated_at, so it cannot be "
              "reproduced; rebuild it", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        rebuilt_path = Path(tmp) / "data.json"
        env = {
            **os.environ,
            "CARBONSTACK_AS_OF": as_of,
            "CARBONSTACK_DATA_OUT": str(rebuilt_path),
        }
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_dashboard_data.py")],
            env=env, capture_output=True, text=True)
        if proc.returncode != 0:
            print("rebuild failed:", file=sys.stderr)
            print(proc.stdout, file=sys.stderr)
            print(proc.stderr, file=sys.stderr)
            return 1
        rebuilt = json.loads(rebuilt_path.read_text())

    diff = first_difference(normalise(committed), normalise(rebuilt))
    if diff is None:
        with tempfile.TemporaryDirectory() as tmp:
            page_problem = page_is_current(Path(tmp))
        if page_problem:
            print(page_problem, file=sys.stderr)
            print("  rebuild with: python3 scripts/build_dashboard.py",
                  file=sys.stderr)
            return 1
        print(f"dashboard/ is in sync (as of {as_of})")
        return 0

    print("dashboard/data.json is stale — the code produces something else now.",
          file=sys.stderr)
    print(f"  first difference: {diff}", file=sys.stderr)
    print("  rebuild with: python3 scripts/build_dashboard_data.py "
          "&& python3 scripts/build_dashboard.py", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
