"""Equity and ETF quotes.

Four vendors are implemented behind one interface because quote data is the
part of this stack most likely to be renegotiated: pricing changes, coverage
differs by exchange, and free tiers disappear. The resolver is assembled from
whichever API keys are actually present in the environment, so moving from one
vendor to another is a configuration change, not a code change.

Symbols are normalised per vendor. An Indian listed share is ``RELIANCE`` on
NSE, ``RELIANCE.NS`` to Yahoo, ``RELIANCE.BSE`` to Alpha Vantage and
``NSE:RELIANCE`` to Finnhub -- getting this wrong returns a plausible quote for
the wrong instrument, which is the most dangerous class of data error here.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from .cache import Cache
from .providers import (
    MarketDataProvider, ProviderError, Quote, Resolver, http_json,
)


def _utc(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


class YahooQuoteProvider(MarketDataProvider):
    """Yahoo's chart endpoint. No key, good Indian coverage, no licence for
    commercial redistribution -- fine for development and for a user's own
    portfolio view, and to be replaced with a licensed feed before launch.
    That trade-off is recorded here rather than discovered later."""

    name = "yahoo"
    covers = ("stock", "etf", "index")
    BASE = "https://query1.finance.yahoo.com/v8/finance/chart/"

    def __init__(self, *, suffix: str = ".NS") -> None:
        self.suffix = suffix

    def symbol_for(self, symbol: str) -> str:
        if "." in symbol or "^" in symbol:
            return symbol
        return f"{symbol.upper()}{self.suffix}"

    def quote(self, symbol: str) -> Quote | None:
        payload = http_json(f"{self.BASE}{self.symbol_for(symbol)}?interval=1d&range=5d")
        try:
            result = payload["chart"]["result"][0]
            meta = result["meta"]
            price = float(meta["regularMarketPrice"])
            stamp = float(meta.get("regularMarketTime") or 0)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError(f"unexpected Yahoo payload for {symbol}") from exc
        previous = meta.get("chartPreviousClose") or meta.get("previousClose")
        change = (price / float(previous) - 1) if previous else None
        return Quote(
            symbol=symbol.upper(), price=price,
            currency=meta.get("currency", "INR"),
            as_of=_utc(stamp) if stamp else datetime.now(timezone.utc),
            provider=self.name,
            previous_close=float(previous) if previous else None,
            change_pct=change,
        )

    def health(self) -> dict[str, Any]:
        return {"provider": self.name, "status": "configured", "keyless": True}


class AlphaVantageProvider(MarketDataProvider):
    name = "alphavantage"
    covers = ("stock", "etf")
    BASE = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str, *, suffix: str = ".BSE") -> None:
        if not api_key:
            raise ValueError("AlphaVantage needs an API key")
        self.api_key = api_key
        self.suffix = suffix

    def quote(self, symbol: str) -> Quote | None:
        target = symbol if "." in symbol else f"{symbol.upper()}{self.suffix}"
        payload = http_json(
            f"{self.BASE}?function=GLOBAL_QUOTE&symbol={target}&apikey={self.api_key}"
        )
        if payload.get("Note") or payload.get("Information"):
            # Alpha Vantage reports rate limiting with HTTP 200 and a prose
            # field. Treating it as an error is what stops the resolver from
            # caching a quoteless response as if it were real.
            raise ProviderError("AlphaVantage rate limit reached")
        block = payload.get("Global Quote") or {}
        price_raw = block.get("05. price")
        if not price_raw:
            return None
        return Quote(
            symbol=symbol.upper(), price=float(price_raw), currency="INR",
            as_of=datetime.now(timezone.utc), provider=self.name,
            previous_close=float(block["08. previous close"]) if block.get("08. previous close") else None,
        )

    def health(self) -> dict[str, Any]:
        return {"provider": self.name, "status": "configured", "keyless": False}


class FinnhubProvider(MarketDataProvider):
    name = "finnhub"
    covers = ("stock", "etf")
    BASE = "https://finnhub.io/api/v1"

    def __init__(self, api_key: str, *, exchange: str = "NSE") -> None:
        if not api_key:
            raise ValueError("Finnhub needs an API key")
        self.api_key = api_key
        self.exchange = exchange

    def quote(self, symbol: str) -> Quote | None:
        target = symbol if ":" in symbol else f"{self.exchange}:{symbol.upper()}"
        payload = http_json(f"{self.BASE}/quote?symbol={target}&token={self.api_key}")
        price = payload.get("c")
        if not price:
            return None
        return Quote(
            symbol=symbol.upper(), price=float(price), currency="INR",
            as_of=_utc(float(payload.get("t") or 0)) if payload.get("t") else datetime.now(timezone.utc),
            provider=self.name,
            previous_close=float(payload["pc"]) if payload.get("pc") else None,
            change_pct=(float(payload["dp"]) / 100) if payload.get("dp") is not None else None,
        )

    def health(self) -> dict[str, Any]:
        return {"provider": self.name, "status": "configured", "keyless": False}


class TwelveDataProvider(MarketDataProvider):
    name = "twelvedata"
    covers = ("stock", "etf", "fx")
    BASE = "https://api.twelvedata.com"

    def __init__(self, api_key: str, *, exchange: str = "NSE") -> None:
        if not api_key:
            raise ValueError("TwelveData needs an API key")
        self.api_key = api_key
        self.exchange = exchange

    def quote(self, symbol: str) -> Quote | None:
        payload = http_json(
            f"{self.BASE}/quote?symbol={symbol.upper()}&exchange={self.exchange}"
            f"&apikey={self.api_key}"
        )
        if payload.get("status") == "error":
            raise ProviderError(payload.get("message", "TwelveData error"))
        price = payload.get("close")
        if not price:
            return None
        return Quote(
            symbol=symbol.upper(), price=float(price),
            currency=payload.get("currency", "INR"),
            as_of=datetime.now(timezone.utc), provider=self.name,
            previous_close=float(payload["previous_close"]) if payload.get("previous_close") else None,
            change_pct=(float(payload["percent_change"]) / 100)
            if payload.get("percent_change") else None,
        )

    def health(self) -> dict[str, Any]:
        return {"provider": self.name, "status": "configured", "keyless": False}


def build_resolver(
    *,
    cache: Cache | None = None,
    environ: dict[str, str] | None = None,
    include_amfi: bool = True,
    amfi_text: str | None = None,
) -> Resolver:
    """Assemble the live data stack from whatever credentials exist.

    Order matters and is not arbitrary: AMFI first because it is authoritative
    for the instrument class most of this product's users hold, then keyed
    vendors in order of reliability, then the keyless one last as a fallback.
    """
    environ = environ if environ is not None else dict(os.environ)
    resolver = Resolver(cache=cache)

    if include_amfi:
        from .amfi import AmfiProvider
        provider = AmfiProvider(cache=cache)
        if amfi_text is not None:
            provider.load(amfi_text)
        resolver.add(provider)

    if environ.get("AICIO_FINNHUB_KEY"):
        resolver.add(FinnhubProvider(environ["AICIO_FINNHUB_KEY"]))
    if environ.get("AICIO_TWELVEDATA_KEY"):
        resolver.add(TwelveDataProvider(environ["AICIO_TWELVEDATA_KEY"]))
    if environ.get("AICIO_ALPHAVANTAGE_KEY"):
        resolver.add(AlphaVantageProvider(environ["AICIO_ALPHAVANTAGE_KEY"]))
    if environ.get("AICIO_ENABLE_YAHOO", "1") not in {"0", "false", "no"}:
        resolver.add(YahooQuoteProvider())
    return resolver
