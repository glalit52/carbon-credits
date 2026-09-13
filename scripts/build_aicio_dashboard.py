#!/usr/bin/env python3
"""Rebuild the committed Personal AI CIO dashboard.

The page is generated here, reviewed, and committed. Building it during a
deploy would make what a user sees depend on whatever the build container
happened to have, which for a page full of someone's net worth is the wrong
trade.

    python3 scripts/build_aicio_dashboard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aicio.web import build                              # noqa: E402

OUT = ROOT / "aicio_dashboard"


def main() -> int:
    for path in build(OUT):
        print(f"wrote {path.relative_to(ROOT)}  {path.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
