"""Provider abstraction and the failover resolver."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from abc import ABC
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from ..provenance import Provenance, SourceKind
from .cache import Cache

#: Every outbound call is bounded. A wealth dashboard that hangs because a
#: vendor is slow is indistinguishable, to the user, from one that is broken.
HTTP_TIMEOUT = float(os.environ.get("AICIO_HTTP_TIMEOUT", "12"))
USER_AGENT = "aicio/1.0 (+personal-ai-cio)"


class ProviderError(RuntimeError):
    """A provider could not answer. Never raised to the user as a number."""


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: float
    currency: str
    as_of: datetime
    provider: str
    previous_close: float | None = None
    change_pct: float | None = None
    stale: bool = False

    def provenance(self) -> Provenance:
        return Provenance(
            kind=SourceKind.MARKET_DATA,
            provider=self.provider,
            observed_at=self.as_of,
            reference=self.symbol,
            transformation="quote" + (" (served stale from cache)" if self.stale else ""),
            confidence=0.75 if self.stale else 1.0,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "price": self.price, "currency": self.currency,
            "as_of": self.as_of.isoformat(), "provider": self.provider,
            "previous_close": self.previous_close, "change_pct": self.change_pct,
            "stale": self.stale,
        }


@dataclass(frozen=True)
class NavPoint:
    scheme_code: str
    isin: str
    name: str
    nav: float
    on: date
    provider: str
    stale: bool = False

    def provenance(self) -> Provenance:
        return Provenance(
            kind=SourceKind.MARKET_DATA,
            provider=self.provider,
            observed_at=datetime.combine(self.on, datetime.min.time(), tzinfo=timezone.utc),
            reference=self.isin or self.scheme_code,
            transformation="declared NAV",
            confidence=0.75 if self.stale else 1.0,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "scheme_code": self.scheme_code, "isin": self.isin, "name": self.name,
            "nav": self.nav, "on": self.on.isoformat(), "provider": self.provider,
            "stale": self.stale,
        }


@dataclass(frozen=True)
class FundInfo:
    """Reference data about a scheme. Slow-moving, cached hard."""

    isin: str
    name: str
    category: str = ""
    benchmark: str = ""
    amc: str = ""
    expense_ratio: float | None = None
    aum_cr: float | None = None
    manager: str = ""
    manager_since: date | None = None
    holdings: dict[str, float] = field(default_factory=dict)
    equity_share: float | None = None
    as_of: date | None = None
    provider: str = ""

    def provenance(self) -> Provenance:
        return Provenance(
            kind=SourceKind.REFERENCE_DATA,
            provider=self.provider or "reference",
            observed_at=datetime.combine(
                self.as_of or date.today(), datetime.min.time(), tzinfo=timezone.utc
            ),
            reference=self.isin,
            transformation="fund reference data",
            confidence=0.95,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "isin": self.isin, "name": self.name, "category": self.category,
            "benchmark": self.benchmark, "amc": self.amc,
            "expense_ratio": self.expense_ratio, "aum_cr": self.aum_cr,
            "manager": self.manager,
            "manager_since": self.manager_since.isoformat() if self.manager_since else None,
            "holdings": dict(self.holdings), "equity_share": self.equity_share,
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "provider": self.provider,
        }


class MarketDataProvider(ABC):
    """What every data source must implement.

    Methods return ``None`` for "I do not cover this instrument" and raise
    :class:`ProviderError` for "I cover it but could not answer". The resolver
    treats those two cases differently: the first moves on quietly, the second
    is worth logging and eventually alerting on.
    """

    name: str = "provider"
    #: Which instrument families this provider is authoritative for.
    covers: tuple[str, ...] = ()

    def quote(self, symbol: str) -> Quote | None:
        return None

    def nav(self, *, isin: str = "", scheme_code: str = "") -> NavPoint | None:
        return None

    def nav_history(self, *, isin: str = "", scheme_code: str = "",
                    start: date | None = None) -> list[NavPoint]:
        return []

    def fund_info(self, isin: str) -> FundInfo | None:
        return None

    def health(self) -> dict[str, Any]:
        return {"provider": self.name, "status": "unknown"}


def http_json(url: str, *, headers: dict[str, str] | None = None, timeout: float = HTTP_TIMEOUT) -> Any:
    """GET a JSON document. Small on purpose -- the failure modes are the point.

    Note the absence of a retry loop: retries belong in the resolver, where
    they can fail over to a different provider, not here, where they would
    only hammer a source that is already struggling.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"{url} returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError(f"{url} unreachable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProviderError(f"{url} returned unparseable JSON") from exc


def http_text(url: str, *, headers: dict[str, str] | None = None, timeout: float = HTTP_TIMEOUT) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"{url} returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError(f"{url} unreachable: {exc}") from exc


class StaticProvider(MarketDataProvider):
    """Fixture-backed provider.

    Not a test double bolted on afterwards -- it is how the demo portfolio,
    the eval suite and CI all run without a vendor contract or a network. The
    same code path serves it as serves a live feed.
    """

    name = "static"
    covers = ("stock", "fund", "etf")

    def __init__(
        self,
        quotes: dict[str, float] | None = None,
        navs: dict[str, float] | None = None,
        funds: dict[str, FundInfo] | None = None,
        *,
        as_of: date | None = None,
    ) -> None:
        self._quotes = quotes or {}
        self._navs = navs or {}
        self._funds = funds or {}
        self._as_of = as_of or date.today()

    def quote(self, symbol: str) -> Quote | None:
        price = self._quotes.get(symbol.upper())
        if price is None:
            return None
        return Quote(
            symbol=symbol.upper(), price=price, currency="INR",
            as_of=datetime.combine(self._as_of, datetime.min.time(), tzinfo=timezone.utc),
            provider=self.name,
        )

    def nav(self, *, isin: str = "", scheme_code: str = "") -> NavPoint | None:
        key = isin or scheme_code
        value = self._navs.get(key)
        if value is None:
            return None
        fund = self._funds.get(isin)
        return NavPoint(
            scheme_code=scheme_code, isin=isin,
            name=fund.name if fund else key, nav=value, on=self._as_of, provider=self.name,
        )

    def fund_info(self, isin: str) -> FundInfo | None:
        return self._funds.get(isin)

    def health(self) -> dict[str, Any]:
        return {
            "provider": self.name, "status": "ok",
            "quotes": len(self._quotes), "navs": len(self._navs), "funds": len(self._funds),
        }


@dataclass
class Resolver:
    """Ask providers in order; take the first real answer.

    When every provider fails, the cache is consulted for a stale value, which
    is returned *marked stale* so the freshness rules downstream can decide
    whether it is good enough for the decision being made. A price good enough
    to show on a dashboard is not necessarily good enough to justify a sale,
    and that judgement belongs in the decision engine, not here.
    """

    providers: list[MarketDataProvider] = field(default_factory=list)
    cache: Cache | None = None
    quote_ttl: int = 900
    nav_ttl: int = 6 * 3600
    fund_ttl: int = 7 * 24 * 3600
    errors: list[str] = field(default_factory=list)

    def add(self, provider: MarketDataProvider) -> "Resolver":
        self.providers.append(provider)
        return self

    def quote(self, symbol: str) -> Quote | None:
        key = f"quote:{symbol.upper()}"
        if self.cache:
            cached = self.cache.get(key, ttl=self.quote_ttl)
            if cached:
                return _quote_from(cached)
        for provider in self.providers:
            try:
                result = provider.quote(symbol)
            except ProviderError as exc:
                self.errors.append(f"{provider.name}: {exc}")
                continue
            if result is not None:
                if self.cache:
                    self.cache.put(key, result.to_dict())
                return result
        return self._stale_quote(key)

    def _stale_quote(self, key: str) -> Quote | None:
        if not self.cache:
            return None
        cached, age = self.cache.get_stale(key)
        if not cached:
            return None
        self.errors.append(f"serving {key} from cache, {age / 3600:.1f}h old")
        return _quote_from({**cached, "stale": True})

    def nav(self, *, isin: str = "", scheme_code: str = "") -> NavPoint | None:
        key = f"nav:{isin or scheme_code}"
        if self.cache:
            cached = self.cache.get(key, ttl=self.nav_ttl)
            if cached:
                return _nav_from(cached)
        for provider in self.providers:
            try:
                result = provider.nav(isin=isin, scheme_code=scheme_code)
            except ProviderError as exc:
                self.errors.append(f"{provider.name}: {exc}")
                continue
            if result is not None:
                if self.cache:
                    self.cache.put(key, result.to_dict())
                return result
        if self.cache:
            cached, age = self.cache.get_stale(key)
            if cached:
                self.errors.append(f"serving {key} from cache, {age / 3600:.1f}h old")
                return _nav_from({**cached, "stale": True})
        return None

    def fund_info(self, isin: str) -> FundInfo | None:
        key = f"fund:{isin}"
        if self.cache:
            cached = self.cache.get(key, ttl=self.fund_ttl)
            if cached:
                return _fund_from(cached)
        for provider in self.providers:
            try:
                result = provider.fund_info(isin)
            except ProviderError as exc:
                self.errors.append(f"{provider.name}: {exc}")
                continue
            if result is not None:
                if self.cache:
                    self.cache.put(key, result.to_dict())
                return result
        return None

    def health(self) -> dict[str, Any]:
        return {
            "providers": [p.health() for p in self.providers],
            "recent_errors": self.errors[-10:],
        }


def _quote_from(raw: dict[str, Any]) -> Quote:
    return Quote(
        symbol=raw["symbol"], price=float(raw["price"]), currency=raw.get("currency", "INR"),
        as_of=datetime.fromisoformat(raw["as_of"]), provider=raw.get("provider", "cache"),
        previous_close=raw.get("previous_close"), change_pct=raw.get("change_pct"),
        stale=bool(raw.get("stale")),
    )


def _nav_from(raw: dict[str, Any]) -> NavPoint:
    return NavPoint(
        scheme_code=raw.get("scheme_code", ""), isin=raw.get("isin", ""),
        name=raw.get("name", ""), nav=float(raw["nav"]), on=date.fromisoformat(raw["on"]),
        provider=raw.get("provider", "cache"), stale=bool(raw.get("stale")),
    )


def _fund_from(raw: dict[str, Any]) -> FundInfo:
    return FundInfo(
        isin=raw["isin"], name=raw.get("name", ""), category=raw.get("category", ""),
        benchmark=raw.get("benchmark", ""), amc=raw.get("amc", ""),
        expense_ratio=raw.get("expense_ratio"), aum_cr=raw.get("aum_cr"),
        manager=raw.get("manager", ""),
        manager_since=date.fromisoformat(raw["manager_since"]) if raw.get("manager_since") else None,
        holdings=dict(raw.get("holdings", {})), equity_share=raw.get("equity_share"),
        as_of=date.fromisoformat(raw["as_of"]) if raw.get("as_of") else None,
        provider=raw.get("provider", "cache"),
    )
