#!/usr/bin/env python3
"""Inline the dataset into the dashboard template.

The data ships inside the page rather than being fetched, so the dashboard
opens with no network at all and cannot render half-empty.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "dashboard"


def main() -> int:
    data = (DASH / "data.json").read_text().strip()
    template = (DASH / "template.html").read_text()
    if "__DATA__" not in template:
        print("template has no __DATA__ placeholder", file=sys.stderr)
        return 1
    # The payload sits in a <script type="application/json">, so the only
    # sequence that can break out of it is a literal closing script tag.
    safe = data.replace("</", "<\\/")
    out = Path(os.environ.get("CARBONSTACK_PAGE_OUT", DASH / "index.html"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(template.replace("__DATA__", safe))
    try:
        shown = out.relative_to(ROOT)
    except ValueError:
        shown = out
    print(f"wrote {shown}  {out.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
