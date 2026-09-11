"""Persistence.

The library computed credits and forgot them. A product has to remember: what
was enrolled, what was observed, what was quantified, who approved it, what was
issued, and who got paid. That record is the asset -- the credits are just its
output -- so it is kept in one portable file that a verification body can open
without installing anything.
"""

from __future__ import annotations

from .repo import Store, StoreError
from .schema import LATEST as SCHEMA_VERSION

__all__ = ["Store", "StoreError", "SCHEMA_VERSION"]
