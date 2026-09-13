"""Persistence.

SQLite, because a person's financial record is small -- a few thousand rows
even for a family office -- and because a single file that any auditor can open
with ``sqlite3`` is worth more than a server they have to be granted access to.
The repository is written against plain SQL with no ORM, so what runs is what
you read.

Swap in Postgres when multi-tenancy or write concurrency demands it: the
migrations are ordinary DDL and :class:`Store` is the only thing that knows
about a connection.
"""

from __future__ import annotations

from .repo import EncryptedTokenVault, Store, StoreError
from .schema import MIGRATIONS, migrate

__all__ = ["Store", "StoreError", "EncryptedTokenVault", "MIGRATIONS", "migrate"]
