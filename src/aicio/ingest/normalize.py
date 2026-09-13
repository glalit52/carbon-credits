"""Normalisation: many statements, one portfolio.

Imports arrive overlapping. The same fund appears in a CAS and in a broker
export with a different name; the same position gets uploaded twice a month
apart. Merging them wrongly is worse than not merging: a duplicated holding
doubles someone's net worth on screen.

The resolution order is strictly identifier-first -- ISIN, then scheme code,
then ticker -- and only falls back to name similarity for instruments that have
no identifier at all, where it demands a high match and records that it guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
from typing import Any, Iterable, Sequence

from ..domain import (
    Account, Asset, Holding, Portfolio, SIP, Transaction,
)
from ..money import ZERO, money
from ..provenance import Provenance
from .parser import ParseResult

#: Noise words that differ between sources for the same scheme and carry no
#: distinguishing meaning.
_NOISE = re.compile(
    r"\b(direct|regular|plan|growth|option|idcw|dividend|reinvest(?:ment)?|"
    r"payout|fund|scheme|the|ltd|limited|-)\b",
    re.IGNORECASE,
)

#: Below this, two names are treated as different instruments. Set high on
#: purpose: "HDFC Small Cap" and "HDFC Mid Cap" score around 0.8 on raw
#: similarity and must not merge.
NAME_MATCH_THRESHOLD = 0.94


def _canonical(name: str) -> str:
    text = _NOISE.sub(" ", name.lower())
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _similar(left: str, right: str) -> float:
    return SequenceMatcher(None, _canonical(left), _canonical(right)).ratio()


def resolve_asset(candidate: Asset, known: Iterable[Asset]) -> Asset | None:
    """Find the existing asset that ``candidate`` is another name for."""
    known = list(known)
    if candidate.isin:
        for asset in known:
            if asset.isin and asset.isin == candidate.isin:
                return asset
    if candidate.scheme_code:
        for asset in known:
            if asset.scheme_code and asset.scheme_code == candidate.scheme_code:
                return asset
    if candidate.ticker:
        for asset in known:
            if asset.ticker and asset.ticker.upper() == candidate.ticker.upper():
                return asset
    if candidate.isin:
        # It has an identifier and nothing matched it: it is genuinely new.
        # Falling through to name matching here is how two share classes of
        # the same fund get silently merged.
        return None
    best, score = None, 0.0
    for asset in known:
        if asset.isin:
            continue
        ratio = _similar(candidate.name, asset.name)
        if ratio > score:
            best, score = asset, ratio
    return best if score >= NAME_MATCH_THRESHOLD else None


@dataclass
class NormalisationReport:
    merged_assets: list[tuple[str, str]] = field(default_factory=list)
    duplicate_holdings: list[str] = field(default_factory=list)
    duplicate_transactions: int = 0
    unresolved: list[str] = field(default_factory=list)
    corrections_applied: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "merged_assets": [{"from": a, "into": b} for a, b in self.merged_assets],
            "duplicate_holdings": list(self.duplicate_holdings),
            "duplicate_transactions": self.duplicate_transactions,
            "unresolved": list(self.unresolved),
            "corrections_applied": self.corrections_applied,
        }


@dataclass
class Correction:
    """A user's manual fix. Applied after parsing, recorded as provenance, and
    always winning over parsed data -- the user is the authority on their own
    portfolio."""

    target: str                      # "holding" | "asset"
    target_id: str
    field: str
    value: Any
    note: str = ""


def normalise(
    results: Sequence[ParseResult],
    *,
    user_id: str,
    as_of: date | None = None,
    existing: Portfolio | None = None,
    corrections: Sequence[Correction] = (),
    cash: Any = ZERO,
    sips: Sequence[SIP] = (),
) -> tuple[Portfolio, NormalisationReport]:
    """Merge parse results (and anything already stored) into one portfolio."""
    report = NormalisationReport()
    as_of = as_of or date.today()

    assets: dict[str, Asset] = dict(existing.assets) if existing else {}
    accounts: dict[str, Account] = {a.id: a for a in (existing.accounts if existing else [])}
    holdings: dict[tuple[str, str], Holding] = {
        (h.account_id, h.asset_id): h for h in (existing.holdings if existing else [])
    }
    transactions: dict[str, Transaction] = {
        t.id: t for t in (existing.transactions if existing else [])
    }

    alias: dict[str, str] = {}

    for result in results:
        for account in result.accounts:
            accounts.setdefault(account.id, account)
        for asset in result.assets:
            match = resolve_asset(asset, assets.values())
            if match is None:
                assets[asset.id] = asset
            else:
                alias[asset.id] = match.id
                if asset.id != match.id:
                    report.merged_assets.append((asset.id, match.id))
                _enrich(match, asset)

        for holding in result.holdings:
            asset_id = alias.get(holding.asset_id, holding.asset_id)
            holding.asset_id = asset_id
            key = (holding.account_id, asset_id)
            previous = holdings.get(key)
            if previous is None:
                holdings[key] = holding
                continue
            # Same position from two sources: keep the one observed later, and
            # keep the better cost basis if the newer file did not carry one.
            report.duplicate_holdings.append(f"{holding.account_id}:{asset_id}")
            winner, loser = (
                (holding, previous) if holding.as_of >= previous.as_of else (previous, holding)
            )
            if winner.average_cost == winner.current_price and loser.average_cost != loser.current_price:
                winner.average_cost = loser.average_cost
            winner.lots = winner.lots or loser.lots
            holdings[key] = winner

        for txn in result.transactions:
            txn.asset_id = alias.get(txn.asset_id, txn.asset_id)
            if txn.id in transactions:
                report.duplicate_transactions += 1
                continue
            # A second import of the same statement produces new ids for
            # identical rows, so identity is also checked on meaning.
            signature = (txn.account_id, txn.asset_id, txn.trade_date, txn.txn_type,
                         str(txn.units), str(txn.amount))
            if any(
                (t.account_id, t.asset_id, t.trade_date, t.txn_type, str(t.units), str(t.amount))
                == signature
                for t in transactions.values()
            ):
                report.duplicate_transactions += 1
                continue
            transactions[txn.id] = txn

    for correction in corrections:
        if correction.target == "holding":
            for holding in holdings.values():
                if holding.id == correction.target_id and hasattr(holding, correction.field):
                    setattr(holding, correction.field, correction.value)
                    holding.provenance = Provenance(
                        kind=holding.provenance.kind,
                        provider="user:correction",
                        observed_at=holding.provenance.observed_at,
                        reference=holding.provenance.reference,
                        transformation=f"user corrected {correction.field}: {correction.note}",
                        confidence=1.0,
                    )
                    report.corrections_applied += 1
        elif correction.target == "asset":
            asset = assets.get(correction.target_id)
            if asset is not None and hasattr(asset, correction.field):
                setattr(asset, correction.field, correction.value)
                report.corrections_applied += 1

    for holding in holdings.values():
        if holding.asset_id not in assets:
            report.unresolved.append(holding.asset_id)

    portfolio = Portfolio(
        user_id=user_id,
        as_of=as_of,
        accounts=list(accounts.values()),
        assets=assets,
        holdings=[h for h in holdings.values() if h.asset_id in assets],
        transactions=list(transactions.values()),
        sips=list(sips) if sips else list(existing.sips if existing else []),
        cash=money(cash) if cash else (existing.cash if existing else ZERO),
        external_liabilities=existing.external_liabilities if existing else ZERO,
    )
    return portfolio, report


def _enrich(target: Asset, other: Asset) -> None:
    """Fill blanks on the surviving asset from the duplicate.

    Only blanks: a broker export that says ``sector=""`` must not erase a
    sector a reference-data provider already established.
    """
    for field_name in ("isin", "scheme_code", "ticker", "issuer", "category",
                       "benchmark", "sector", "geography"):
        if not getattr(target, field_name) and getattr(other, field_name):
            setattr(target, field_name, getattr(other, field_name))
    if target.expense_ratio is None and other.expense_ratio is not None:
        target.expense_ratio = other.expense_ratio
    if not target.holdings_lookthrough and other.holdings_lookthrough:
        target.holdings_lookthrough = dict(other.holdings_lookthrough)
