"""Market, reference and account data.

Everything outside the user's own files enters through here, and everything
that enters is wrapped in a :class:`~aicio.provenance.Provenance` before it is
allowed any further. The engine never calls a provider directly; it is handed
values that already know where they came from and how old they are.

Three properties this layer has to have, in priority order:

1.  **Honest failure.** A provider that is down produces a stale-marked value
    or nothing, never a plausible guess. The product can say "I don't have
    today's price"; it cannot afford to be wrong about one.
2.  **Substitutability.** Providers are licensed commercially and change. Every
    one implements the same small protocol, and the resolver fails over in a
    declared order.
3.  **Caching by default.** Rate limits are real and vendor bills are real.
    Nothing fetches twice what it fetched a minute ago.
"""

from __future__ import annotations

from .cache import Cache
from .connectors import (
    AccountConnector, ConnectorRegistry, ConsentError, SandboxBrokerConnector,
)
from .providers import (
    FundInfo, MarketDataProvider, NavPoint, ProviderError, Quote, Resolver,
    StaticProvider,
)

__all__ = [
    "Cache", "MarketDataProvider", "Quote", "NavPoint", "FundInfo", "Resolver",
    "ProviderError", "StaticProvider",
    "AccountConnector", "ConnectorRegistry", "SandboxBrokerConnector", "ConsentError",
]
