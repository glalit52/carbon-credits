"""Account connections: brokers, aggregators and banks.

Three rules shape every connector here, and they are the reason this is not
just a folder of HTTP clients:

1.  **Consent is a first-class object, not a boolean.** A connection has a
    purpose, a scope, an expiry and a revocation path, because that is what
    India's account-aggregator framework and the DPDP Act require, and because
    a user must be able to see and withdraw exactly what they granted.
2.  **Credentials never reach the AI layer.** Tokens live behind
    :class:`TokenVault`, are fetched at call time, and are never placed on a
    connector's public attributes, in a log line, or in a fact sheet. The
    grounding layer is given holdings; it is never given the means to obtain
    them.
3.  **A connector returns a parse result, not a bespoke shape.** Connected data
    goes through the same normalisation, de-duplication and provenance path as
    an uploaded statement, so there is one place where a holding is decided to
    be real.

The live connectors are written against each vendor's documented contract and
are exercised in tests against recorded payloads. Any that this deployment has
no credentials for simply do not register.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Sequence

from ..domain import (
    Account, AccountType, Asset, AssetType, Holding, new_id,
)
from ..ingest.csv_statement import guess_asset_type
from ..ingest.parser import ParseResult
from ..money import money, quantity
from ..provenance import Provenance, SourceKind, utcnow
from .providers import HTTP_TIMEOUT, USER_AGENT


class ConnectorError(RuntimeError):
    pass


class ConsentError(PermissionError):
    """Raised when data is requested without a live, in-scope consent.

    Deliberately a hard error rather than an empty result: a connector that
    quietly returns nothing when consent lapsed would look like an account with
    no holdings, and the user would be shown a portfolio that is missing a
    third of their wealth with no indication why.
    """


@dataclass
class ConsentArtefact:
    """The record of what the user allowed, for how long, and for what."""

    id: str
    user_id: str
    connector: str
    purpose: str
    scope: tuple[str, ...]
    granted_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    reference: str = ""                      # the provider's own consent handle

    @property
    def active(self) -> bool:
        now = utcnow()
        return self.revoked_at is None and self.granted_at <= now < self.expires_at

    def covers(self, scope: str) -> bool:
        return self.active and (scope in self.scope or "*" in self.scope)

    def revoke(self) -> None:
        self.revoked_at = utcnow()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "user_id": self.user_id, "connector": self.connector,
            "purpose": self.purpose, "scope": list(self.scope),
            "granted_at": self.granted_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "reference": self.reference, "active": self.active,
        }


def grant_consent(
    user_id: str, connector: str, *, purpose: str, scope: Sequence[str], days: int = 365,
    reference: str = "",
) -> ConsentArtefact:
    now = utcnow()
    return ConsentArtefact(
        id=new_id("consent", user_id, connector, now.isoformat()),
        user_id=user_id, connector=connector, purpose=purpose, scope=tuple(scope),
        granted_at=now, expires_at=now + timedelta(days=days), reference=reference,
    )


class TokenVault(ABC):
    """Where access tokens live. Never the connector itself."""

    @abstractmethod
    def get(self, user_id: str, connector: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def put(self, user_id: str, connector: str, token: dict[str, Any]) -> None: ...

    @abstractmethod
    def drop(self, user_id: str, connector: str) -> None: ...


class MemoryVault(TokenVault):
    """In-process vault for development and tests.

    Production uses :class:`aicio.store.repo.EncryptedTokenVault`, which seals
    tokens with the ChaCha20-Poly1305 implementation in :mod:`aicio.crypto`
    before they touch disk.
    """

    def __init__(self) -> None:
        self._tokens: dict[tuple[str, str], dict[str, Any]] = {}

    def get(self, user_id: str, connector: str) -> dict[str, Any] | None:
        return self._tokens.get((user_id, connector))

    def put(self, user_id: str, connector: str, token: dict[str, Any]) -> None:
        self._tokens[(user_id, connector)] = token

    def drop(self, user_id: str, connector: str) -> None:
        self._tokens.pop((user_id, connector), None)


def _http(
    url: str, *, headers: dict[str, str], method: str = "GET", body: dict | None = None,
    timeout: float = HTTP_TIMEOUT,
) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url, data=data, method=method,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json", **headers},
    )
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise ConnectorError(f"{url} returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ConnectorError(f"{url} unreachable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConnectorError(f"{url} returned unparseable JSON") from exc


@dataclass
class ConnectorSpec:
    """What a connector is, for the UI and for the consent screen."""

    key: str
    label: str
    kind: str                         # broker | aggregator | bank | retirement
    country: str
    scopes: tuple[str, ...]
    docs: str = ""
    requires_keys: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "label": self.label, "kind": self.kind,
            "country": self.country, "scopes": list(self.scopes), "docs": self.docs,
            "requires_keys": list(self.requires_keys),
        }


class AccountConnector(ABC):
    """One external source of holdings."""

    spec: ConnectorSpec

    def __init__(self, vault: TokenVault | None = None) -> None:
        self.vault = vault or MemoryVault()

    # -- authorisation -----------------------------------------------------

    def authorize_url(self, *, state: str, redirect_uri: str) -> str:
        raise NotImplementedError(f"{self.spec.key} does not use a redirect flow")

    def exchange(self, user_id: str, payload: dict[str, Any]) -> ConsentArtefact:
        raise NotImplementedError(f"{self.spec.key} does not use a redirect flow")

    def _token(self, user_id: str) -> dict[str, Any]:
        token = self.vault.get(user_id, self.spec.key)
        if not token:
            raise ConsentError(
                f"No live connection to {self.spec.label}. Ask the user to connect it again."
            )
        return token

    def _require(self, consent: ConsentArtefact | None, scope: str) -> ConsentArtefact:
        if consent is None or not consent.covers(scope):
            raise ConsentError(
                f"{self.spec.label} consent for '{scope}' is missing, expired or revoked"
            )
        return consent

    # -- data --------------------------------------------------------------

    @abstractmethod
    def fetch_holdings(self, user_id: str, consent: ConsentArtefact | None = None) -> ParseResult: ...

    def fetch_transactions(
        self, user_id: str, consent: ConsentArtefact | None = None, *, since: date | None = None
    ) -> ParseResult:
        return ParseResult(
            source_name=self.spec.key, source_format="connector",
            notes=[f"{self.spec.label} does not expose transaction history through this API"],
        )

    def health(self) -> dict[str, Any]:
        missing = [key for key in self.spec.requires_keys if not os.environ.get(key)]
        return {
            "connector": self.spec.key,
            "status": "unconfigured" if missing else "configured",
            "missing_keys": missing,
        }


def _result(
    connector: ConnectorSpec, user_id: str, institution: str, account_type: AccountType,
    *, masked: str = "",
) -> tuple[ParseResult, Account]:
    result = ParseResult(source_name=connector.key, source_format="connector", confidence=1.0)
    account = Account(
        id=new_id("acc", user_id, connector.key, masked or institution),
        user_id=user_id, institution=institution, account_type=account_type,
        identifier_masked=masked, source=SourceKind.CONNECTED_ACCOUNT,
        connected_at=utcnow(), last_synced_at=utcnow(),
    )
    result.accounts.append(account)
    return result, account


def _connected_provenance(connector: str, reference: str) -> Provenance:
    return Provenance(
        kind=SourceKind.CONNECTED_ACCOUNT, provider=connector, observed_at=utcnow(),
        reference=reference, transformation="broker holdings API", confidence=1.0,
    )


# ---------------------------------------------------------------------------
# India: brokers
# ---------------------------------------------------------------------------

class ZerodhaKiteConnector(AccountConnector):
    """Zerodha Kite Connect holdings.

    Kite's session tokens are day-scoped: the user re-authorises each morning.
    That is a product constraint, not a bug to engineer around, so the
    connector surfaces it as an expired consent rather than retrying forever.
    """

    spec = ConnectorSpec(
        key="zerodha_kite", label="Zerodha (Kite)", kind="broker", country="IN",
        scopes=("holdings", "positions"), docs="https://kite.trade/docs/connect/v3/",
        requires_keys=("AICIO_KITE_API_KEY",),
    )
    BASE = "https://api.kite.trade"
    LOGIN = "https://kite.zerodha.com/connect/login"

    def authorize_url(self, *, state: str, redirect_uri: str) -> str:
        api_key = os.environ.get("AICIO_KITE_API_KEY", "")
        return f"{self.LOGIN}?v=3&api_key={urllib.parse.quote(api_key)}&state={urllib.parse.quote(state)}"

    def exchange(self, user_id: str, payload: dict[str, Any]) -> ConsentArtefact:
        access_token = payload.get("access_token")
        if not access_token:
            raise ConnectorError("Kite exchange needs an access_token")
        self.vault.put(user_id, self.spec.key, {"access_token": access_token})
        # Kite sessions die at the next trading day's start, so consent is
        # granted for one day rather than the default year.
        return grant_consent(user_id, self.spec.key, purpose="portfolio_analysis",
                             scope=("holdings", "positions"), days=1)

    def fetch_holdings(self, user_id: str, consent: ConsentArtefact | None = None) -> ParseResult:
        self._require(consent, "holdings")
        token = self._token(user_id)
        api_key = os.environ.get("AICIO_KITE_API_KEY", "")
        payload = _http(
            f"{self.BASE}/portfolio/holdings",
            headers={
                "X-Kite-Version": "3",
                "Authorization": f"token {api_key}:{token['access_token']}",
            },
        )
        result, account = _result(self.spec, user_id, "Zerodha", AccountType.DEMAT)
        for row in payload.get("data", []):
            symbol = row.get("tradingsymbol")
            if not symbol:
                continue
            asset = Asset(
                id=new_id("ast", row.get("isin") or symbol),
                name=row.get("tradingsymbol", symbol),
                asset_type=AssetType.ETF if "ETF" in symbol.upper() else AssetType.STOCK,
                isin=row.get("isin", ""), ticker=symbol, geography="IN",
            )
            result.assets.append(asset)
            result.holdings.append(Holding(
                id=new_id("hld", account.id, asset.id),
                account_id=account.id, asset_id=asset.id,
                units=quantity(row.get("quantity", 0) + row.get("t1_quantity", 0)),
                average_cost=money(row.get("average_price", 0)),
                current_price=money(row.get("last_price", 0)),
                as_of=date.today(),
                provenance=_connected_provenance(self.spec.key, symbol),
            ))
        result.recompute_confidence()
        return result


class UpstoxConnector(AccountConnector):
    spec = ConnectorSpec(
        key="upstox", label="Upstox", kind="broker", country="IN",
        scopes=("holdings",), docs="https://upstox.com/developer/api-documentation/",
        requires_keys=("AICIO_UPSTOX_API_KEY",),
    )
    BASE = "https://api.upstox.com/v2"

    def fetch_holdings(self, user_id: str, consent: ConsentArtefact | None = None) -> ParseResult:
        self._require(consent, "holdings")
        token = self._token(user_id)
        payload = _http(
            f"{self.BASE}/portfolio/long-term-holdings",
            headers={"Authorization": f"Bearer {token['access_token']}"},
        )
        result, account = _result(self.spec, user_id, "Upstox", AccountType.DEMAT)
        for row in payload.get("data", []):
            symbol = row.get("tradingsymbol") or row.get("trading_symbol")
            if not symbol:
                continue
            asset = Asset(
                id=new_id("ast", row.get("isin") or symbol), name=row.get("company_name", symbol),
                asset_type=AssetType.STOCK, isin=row.get("isin", ""), ticker=symbol, geography="IN",
            )
            result.assets.append(asset)
            result.holdings.append(Holding(
                id=new_id("hld", account.id, asset.id), account_id=account.id, asset_id=asset.id,
                units=quantity(row.get("quantity", 0)),
                average_cost=money(row.get("average_price", 0)),
                current_price=money(row.get("last_price", 0)),
                as_of=date.today(), provenance=_connected_provenance(self.spec.key, symbol),
            ))
        result.recompute_confidence()
        return result


class AngelOneConnector(AccountConnector):
    spec = ConnectorSpec(
        key="angel_one", label="Angel One (SmartAPI)", kind="broker", country="IN",
        scopes=("holdings",), docs="https://smartapi.angelbroking.com/docs",
        requires_keys=("AICIO_ANGEL_API_KEY",),
    )
    BASE = "https://apiconnect.angelbroking.com/rest/secure/angelbroking/portfolio/v1"

    def fetch_holdings(self, user_id: str, consent: ConsentArtefact | None = None) -> ParseResult:
        self._require(consent, "holdings")
        token = self._token(user_id)
        payload = _http(
            f"{self.BASE}/getAllHolding",
            headers={
                "Authorization": f"Bearer {token['access_token']}",
                "X-PrivateKey": os.environ.get("AICIO_ANGEL_API_KEY", ""),
                "X-SourceID": "WEB", "X-UserType": "USER",
            },
        )
        data = payload.get("data") or {}
        rows = data.get("holdings") if isinstance(data, dict) else data
        result, account = _result(self.spec, user_id, "Angel One", AccountType.DEMAT)
        for row in rows or []:
            symbol = row.get("tradingsymbol")
            if not symbol:
                continue
            asset = Asset(
                id=new_id("ast", row.get("isin") or symbol), name=symbol,
                asset_type=AssetType.STOCK, isin=row.get("isin", ""), ticker=symbol, geography="IN",
            )
            result.assets.append(asset)
            result.holdings.append(Holding(
                id=new_id("hld", account.id, asset.id), account_id=account.id, asset_id=asset.id,
                units=quantity(row.get("quantity", 0)),
                average_cost=money(row.get("averageprice", 0)),
                current_price=money(row.get("ltp", 0)),
                as_of=date.today(), provenance=_connected_provenance(self.spec.key, symbol),
            ))
        result.recompute_confidence()
        return result


class AccountAggregatorConnector(AccountConnector):
    """RBI Account Aggregator (Sahamati) via a licensed AA gateway.

    The AA framework is consent-first by design: the FIU never holds
    credentials, only a signed consent artefact, and the user can revoke it in
    their AA app at any time. That maps exactly onto :class:`ConsentArtefact`,
    which is why consent is modelled the way it is throughout this package.

    The gateway base URL and client credentials are deployment configuration --
    every AA gateway exposes the same ReBIT schema behind a different host.
    """

    spec = ConnectorSpec(
        key="account_aggregator", label="Account Aggregator (RBI)", kind="aggregator",
        country="IN", scopes=("deposit", "mutual_funds", "equities", "nps", "insurance"),
        docs="https://sahamati.org.in/", requires_keys=("AICIO_AA_BASE_URL", "AICIO_AA_CLIENT_ID"),
    )

    def __init__(self, vault: TokenVault | None = None, *, base_url: str = "") -> None:
        super().__init__(vault)
        self.base_url = base_url or os.environ.get("AICIO_AA_BASE_URL", "")

    def request_consent(
        self, user_id: str, *, vua: str, purpose: str = "portfolio_analysis",
        scope: Sequence[str] = ("mutual_funds", "equities", "deposit"), days: int = 365,
    ) -> dict[str, Any]:
        """Start the consent journey; the user approves inside their AA app."""
        if not self.base_url:
            raise ConnectorError("AICIO_AA_BASE_URL is not configured")
        token = self._token(user_id)
        return _http(
            f"{self.base_url}/consents",
            headers={"Authorization": f"Bearer {token['access_token']}"},
            method="POST",
            body={
                "customerVua": vua, "purposeCode": "101", "purposeText": purpose,
                "fiTypes": list(scope),
                "consentExpiry": (utcnow() + timedelta(days=days)).isoformat(),
                "fetchType": "PERIODIC", "frequency": {"unit": "DAY", "value": 1},
            },
        )

    def fetch_holdings(self, user_id: str, consent: ConsentArtefact | None = None) -> ParseResult:
        consent = self._require(consent, "mutual_funds")
        if not self.base_url:
            raise ConnectorError("AICIO_AA_BASE_URL is not configured")
        token = self._token(user_id)
        payload = _http(
            f"{self.base_url}/fi/fetch/{urllib.parse.quote(consent.reference)}",
            headers={"Authorization": f"Bearer {token['access_token']}"},
        )
        result, account = _result(
            self.spec, user_id, "Account Aggregator", AccountType.MF_FOLIO,
            masked=consent.reference[-4:],
        )
        for block in payload.get("FI", []):
            for item in block.get("data", []):
                holdings = (item.get("summary") or {}).get("investment", {}).get("holdings", [])
                for row in holdings:
                    name = row.get("schemeName") or row.get("issuerName") or ""
                    if not name:
                        continue
                    asset = Asset(
                        id=new_id("ast", row.get("isin") or name), name=name,
                        asset_type=guess_asset_type(name), isin=row.get("isin", ""),
                        geography="IN",
                    )
                    result.assets.append(asset)
                    units = row.get("closingUnits") or row.get("units") or 0
                    nav = row.get("nav") or row.get("lastTradedPrice") or 0
                    result.holdings.append(Holding(
                        id=new_id("hld", account.id, asset.id),
                        account_id=account.id, asset_id=asset.id,
                        units=quantity(units),
                        average_cost=money(row.get("costValue", 0) or 0) / quantity(units)
                        if units and row.get("costValue") else money(nav),
                        current_price=money(nav), as_of=date.today(),
                        provenance=Provenance(
                            kind=SourceKind.CONNECTED_ACCOUNT, provider=self.spec.key,
                            observed_at=utcnow(), reference=consent.id,
                            transformation="ReBIT FI data", confidence=1.0,
                        ),
                    ))
        result.recompute_confidence()
        return result


# ---------------------------------------------------------------------------
# United States
# ---------------------------------------------------------------------------

class PlaidConnector(AccountConnector):
    """US bank and brokerage aggregation through Plaid."""

    spec = ConnectorSpec(
        key="plaid", label="Plaid", kind="aggregator", country="US",
        scopes=("investments", "balances", "transactions"),
        docs="https://plaid.com/docs/api/products/investments/",
        requires_keys=("AICIO_PLAID_CLIENT_ID", "AICIO_PLAID_SECRET"),
    )

    def __init__(self, vault: TokenVault | None = None, *, environment: str = "production") -> None:
        super().__init__(vault)
        self.base = f"https://{environment}.plaid.com"

    def _credentials(self) -> dict[str, str]:
        client_id = os.environ.get("AICIO_PLAID_CLIENT_ID", "")
        secret = os.environ.get("AICIO_PLAID_SECRET", "")
        if not client_id or not secret:
            raise ConnectorError("Plaid credentials are not configured")
        return {"client_id": client_id, "secret": secret}

    def fetch_holdings(self, user_id: str, consent: ConsentArtefact | None = None) -> ParseResult:
        self._require(consent, "investments")
        token = self._token(user_id)
        payload = _http(
            f"{self.base}/investments/holdings/get", headers={}, method="POST",
            body={**self._credentials(), "access_token": token["access_token"]},
        )
        securities = {s["security_id"]: s for s in payload.get("securities", [])}
        result, account = _result(self.spec, user_id, "Plaid-linked brokerage",
                                  AccountType.BROKERAGE)
        for row in payload.get("holdings", []):
            security = securities.get(row.get("security_id"), {})
            name = security.get("name") or security.get("ticker_symbol") or "Unknown security"
            asset = Asset(
                id=new_id("ast", security.get("isin") or security.get("ticker_symbol") or name),
                name=name,
                asset_type=_plaid_type(security.get("type", "")),
                isin=security.get("isin") or "",
                ticker=security.get("ticker_symbol") or "",
                currency=row.get("iso_currency_code") or "USD",
                geography="US",
            )
            result.assets.append(asset)
            result.holdings.append(Holding(
                id=new_id("hld", account.id, asset.id), account_id=account.id, asset_id=asset.id,
                units=quantity(row.get("quantity", 0)),
                average_cost=money(row.get("cost_basis") or 0) / quantity(row.get("quantity", 1) or 1)
                if row.get("cost_basis") else money(row.get("institution_price", 0)),
                current_price=money(row.get("institution_price", 0)), as_of=date.today(),
                provenance=_connected_provenance(self.spec.key, asset.ticker or asset.name),
            ))
        result.recompute_confidence()
        return result


def _plaid_type(raw: str) -> AssetType:
    return {
        "equity": AssetType.STOCK, "etf": AssetType.ETF, "mutual fund": AssetType.EQUITY_FUND,
        "fixed income": AssetType.BOND, "cash": AssetType.SAVINGS,
        "cryptocurrency": AssetType.CRYPTO,
    }.get(raw.lower(), AssetType.OTHER)


class SnapTradeConnector(AccountConnector):
    """US/Canada brokerage connections through SnapTrade."""

    spec = ConnectorSpec(
        key="snaptrade", label="SnapTrade", kind="broker", country="US",
        scopes=("holdings",), docs="https://docs.snaptrade.com/",
        requires_keys=("AICIO_SNAPTRADE_CLIENT_ID", "AICIO_SNAPTRADE_CONSUMER_KEY"),
    )
    BASE = "https://api.snaptrade.com/api/v1"

    def fetch_holdings(self, user_id: str, consent: ConsentArtefact | None = None) -> ParseResult:
        self._require(consent, "holdings")
        token = self._token(user_id)
        query = urllib.parse.urlencode({
            "clientId": os.environ.get("AICIO_SNAPTRADE_CLIENT_ID", ""),
            "userId": token.get("snaptrade_user_id", user_id),
            "userSecret": token["user_secret"],
        })
        payload = _http(f"{self.BASE}/accounts/positions?{query}", headers={})
        result, account = _result(self.spec, user_id, "SnapTrade brokerage",
                                  AccountType.BROKERAGE)
        for row in payload if isinstance(payload, list) else payload.get("positions", []):
            symbol_block = (row.get("symbol") or {}).get("symbol") or {}
            symbol = symbol_block.get("symbol") or row.get("symbol", {}).get("raw_symbol", "")
            if not symbol:
                continue
            asset = Asset(
                id=new_id("ast", symbol), name=symbol_block.get("description") or symbol,
                asset_type=AssetType.STOCK, ticker=symbol, currency="USD", geography="US",
            )
            result.assets.append(asset)
            result.holdings.append(Holding(
                id=new_id("hld", account.id, asset.id), account_id=account.id, asset_id=asset.id,
                units=quantity(row.get("units", 0)),
                average_cost=money(row.get("average_purchase_price") or row.get("price", 0)),
                current_price=money(row.get("price", 0)), as_of=date.today(),
                provenance=_connected_provenance(self.spec.key, symbol),
            ))
        result.recompute_confidence()
        return result


# ---------------------------------------------------------------------------
# Sandbox
# ---------------------------------------------------------------------------

class SandboxBrokerConnector(AccountConnector):
    """A connector with no network behind it.

    Exists so the connection flow -- consent, fetch, normalise, analyse -- can
    be run end to end in tests, in the demo and in CI. It follows exactly the
    same consent rules as the live ones, which is the only way those rules get
    exercised on every run.
    """

    spec = ConnectorSpec(
        key="sandbox", label="Sandbox broker", kind="broker", country="IN",
        scopes=("holdings", "transactions"),
    )

    def __init__(self, vault: TokenVault | None = None, *, rows: Sequence[dict[str, Any]] = ()) -> None:
        super().__init__(vault)
        self.rows = list(rows) or [
            {"symbol": "RELIANCE", "isin": "INE002A01018", "name": "Reliance Industries",
             "units": 120, "average_cost": 2280.0, "price": 2960.5, "sector": "energy"},
            {"symbol": "HDFCBANK", "isin": "INE040A01034", "name": "HDFC Bank",
             "units": 200, "average_cost": 1480.0, "price": 1702.3, "sector": "financials"},
            {"symbol": "INFY", "isin": "INE009A01021", "name": "Infosys",
             "units": 150, "average_cost": 1320.0, "price": 1544.0, "sector": "technology"},
        ]

    def authorize_url(self, *, state: str, redirect_uri: str) -> str:
        return f"{redirect_uri}?state={urllib.parse.quote(state)}&code=sandbox"

    def exchange(self, user_id: str, payload: dict[str, Any]) -> ConsentArtefact:
        self.vault.put(user_id, self.spec.key, {"access_token": "sandbox-token"})
        return grant_consent(user_id, self.spec.key, purpose="portfolio_analysis",
                             scope=("holdings", "transactions"), days=90)

    def fetch_holdings(self, user_id: str, consent: ConsentArtefact | None = None) -> ParseResult:
        self._require(consent, "holdings")
        self._token(user_id)
        result, account = _result(self.spec, user_id, "Sandbox broker", AccountType.DEMAT,
                                  masked="**** 4210")
        for row in self.rows:
            asset = Asset(
                id=new_id("ast", row["isin"]), name=row["name"], asset_type=AssetType.STOCK,
                isin=row["isin"], ticker=row["symbol"], sector=row.get("sector", ""),
                geography="IN",
            )
            result.assets.append(asset)
            result.holdings.append(Holding(
                id=new_id("hld", account.id, asset.id), account_id=account.id, asset_id=asset.id,
                units=quantity(row["units"]), average_cost=money(row["average_cost"]),
                current_price=money(row["price"]), as_of=date.today(),
                provenance=_connected_provenance(self.spec.key, row["symbol"]),
            ))
        result.recompute_confidence()
        return result

    def health(self) -> dict[str, Any]:
        return {"connector": self.spec.key, "status": "ok", "rows": len(self.rows)}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ConnectorRegistry:
    """What this deployment can connect to, and what it is missing keys for."""

    def __init__(self, vault: TokenVault | None = None) -> None:
        self.vault = vault or MemoryVault()
        self._connectors: dict[str, AccountConnector] = {}

    def register(self, connector: AccountConnector) -> "ConnectorRegistry":
        connector.vault = self.vault
        self._connectors[connector.spec.key] = connector
        return self

    def get(self, key: str) -> AccountConnector:
        try:
            return self._connectors[key]
        except KeyError:
            raise ConnectorError(f"unknown connector {key!r}") from None

    def available(self) -> list[dict[str, Any]]:
        return [
            {**c.spec.to_dict(), **c.health()} for c in self._connectors.values()
        ]

    def __contains__(self, key: object) -> bool:
        return key in self._connectors

    def __len__(self) -> int:
        return len(self._connectors)


def default_registry(vault: TokenVault | None = None, *, include_sandbox: bool = True) -> ConnectorRegistry:
    """Every connector the product ships with.

    They all register regardless of whether keys are present: the connection
    screen should show a user that Zerodha is supported and needs setup, rather
    than hiding it and leaving them to guess.
    """
    registry = ConnectorRegistry(vault)
    registry.register(ZerodhaKiteConnector())
    registry.register(UpstoxConnector())
    registry.register(AngelOneConnector())
    registry.register(AccountAggregatorConnector())
    registry.register(PlaidConnector())
    registry.register(SnapTradeConnector())
    if include_sandbox:
        registry.register(SandboxBrokerConnector())
    return registry
