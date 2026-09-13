"""Tax lots and capital gains.

Tax rules are *data*, not code. They are held in :class:`TaxRules`, dated, and
passed in explicitly, because Indian capital-gains treatment changed materially
in July 2024 and will change again. Hard-coding a rate would mean every stored
recommendation silently re-interprets itself under next year's law.

The defaults below encode the regime applying to Indian residents for FY
2025-26 as understood at the engine version in this repository. They are a
starting point for a tax professional to confirm, not tax advice, and the
product surfaces them to the user as assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Sequence

from ..domain import (
    INFLOW_TYPES, OUTFLOW_TYPES, Asset, AssetType, TaxLot, Transaction, TxnType, new_id,
)
from ..money import ZERO, as_float, money, quantity, total


@dataclass(frozen=True)
class TaxRules:
    """One tax regime, with the date it applies from."""

    jurisdiction: str = "IN"
    effective_from: date = date(2025, 4, 1)
    #: Equity and equity-oriented funds.
    equity_long_term_months: int = 12
    equity_ltcg_rate: float = 0.125
    equity_stcg_rate: float = 0.20
    #: Annual exemption on equity LTCG, applied across the whole portfolio.
    equity_ltcg_exemption: Decimal = field(default_factory=lambda: money(125000))
    #: Debt funds bought on or after this date are taxed at slab regardless of
    #: holding period -- the rule that ended debt-fund indexation.
    debt_slab_from: date = date(2023, 4, 1)
    other_long_term_months: int = 24
    other_ltcg_rate: float = 0.125
    #: Losses of each type can offset gains; short-term losses are the more
    #: flexible of the two, which shapes which lot it pays to harvest.
    allow_loss_offset: bool = True
    note: str = "India FY2025-26 defaults; confirm with a tax professional"


INDIA_FY2526 = TaxRules()

#: Instruments treated as equity for capital-gains purposes.
_EQUITY_TYPES = {
    AssetType.EQUITY_FUND, AssetType.INDEX_FUND, AssetType.ELSS,
    AssetType.STOCK, AssetType.ETF, AssetType.HYBRID_FUND,
}
_DEBT_TYPES = {AssetType.DEBT_FUND, AssetType.LIQUID_FUND, AssetType.BOND}


class GainType(str, Enum):
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    SLAB = "slab"                  # debt funds post-Apr-2023: taxed as income


@dataclass
class RealisedGain:
    asset_id: str
    lot_id: str
    units: Decimal
    acquired_on: date
    sold_on: date
    proceeds: Decimal
    cost: Decimal
    gain_type: GainType
    holding_days: int

    @property
    def gain(self) -> Decimal:
        return money(self.proceeds - self.cost)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id, "lot_id": self.lot_id,
            "units": str(self.units), "acquired_on": self.acquired_on.isoformat(),
            "sold_on": self.sold_on.isoformat(), "proceeds": str(self.proceeds),
            "cost": str(self.cost), "gain": str(self.gain),
            "gain_type": self.gain_type.value, "holding_days": self.holding_days,
        }


@dataclass
class UnrealisedPosition:
    asset_id: str
    lot_id: str
    units: Decimal
    acquired_on: date
    cost: Decimal
    value: Decimal
    gain_type: GainType
    holding_days: int
    days_to_long_term: int

    @property
    def gain(self) -> Decimal:
        return money(self.value - self.cost)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id, "lot_id": self.lot_id, "units": str(self.units),
            "acquired_on": self.acquired_on.isoformat(), "cost": str(self.cost),
            "value": str(self.value), "gain": str(self.gain),
            "gain_type": self.gain_type.value, "holding_days": self.holding_days,
            "days_to_long_term": self.days_to_long_term,
        }


def _months_between(start: date, end: date) -> float:
    return (end - start).days / 30.44


def classify(
    asset: Asset, acquired_on: date, disposed_on: date, rules: TaxRules
) -> GainType:
    """Which bucket a disposal falls into.

    The debt-fund rule is checked on *acquisition* date, not disposal date,
    because the 2023 change grandfathered existing units -- a detail that
    changes the answer by a factor of two for a 30%-slab investor.
    """
    if asset.asset_type in _DEBT_TYPES and acquired_on >= rules.debt_slab_from:
        return GainType.SLAB
    months = _months_between(acquired_on, disposed_on)
    if asset.asset_type in _EQUITY_TYPES:
        return GainType.LONG_TERM if months >= rules.equity_long_term_months else GainType.SHORT_TERM
    return GainType.LONG_TERM if months >= rules.other_long_term_months else GainType.SHORT_TERM


def build_lots(
    transactions: Sequence[Transaction], *, account_id: str = "", asset_id: str = ""
) -> tuple[list[TaxLot], list[RealisedGain]]:
    """Replay a transaction history into FIFO lots.

    FIFO is the statutory method in India for both shares and mutual-fund
    units, so this is not a choice the product gets to make. Bonus units open a
    zero-cost lot; splits rescale open lots in place rather than opening new
    ones, because a split does not start a new holding period.
    """
    ordered = sorted(transactions, key=lambda t: (t.trade_date, t.id))
    open_lots: list[TaxLot] = []
    realised: list[RealisedGain] = []

    for txn in ordered:
        if txn.txn_type == TxnType.SPLIT:
            # `units` carries the split ratio (2.0 == 2-for-1).
            ratio = as_float(txn.units) or 1.0
            for lot in open_lots:
                lot.units = quantity(as_float(lot.units) * ratio)
                lot.closed_units = quantity(as_float(lot.closed_units) * ratio)
                lot.cost_per_unit = money(as_float(lot.cost_per_unit) / ratio)
            continue

        if txn.txn_type in INFLOW_TYPES:
            if txn.units <= 0:
                continue
            per_unit = (
                money((txn.amount + txn.fees) / txn.units)
                if txn.txn_type != TxnType.BONUS else ZERO
            )
            open_lots.append(TaxLot(
                id=new_id("lot", txn.id, txn.trade_date, txn.units),
                asset_id=txn.asset_id or asset_id,
                account_id=txn.account_id or account_id,
                acquired_on=txn.trade_date,
                units=txn.units,
                cost_per_unit=per_unit,
                txn_id=txn.id,
            ))
        elif txn.txn_type in OUTFLOW_TYPES:
            remaining = txn.units
            price = txn.price if txn.price else (
                money(txn.amount / txn.units) if txn.units else ZERO
            )
            for lot in open_lots:
                if remaining <= 0:
                    break
                available = lot.open_units
                if available <= 0:
                    continue
                take = min(available, remaining)
                lot.closed_units = quantity(lot.closed_units + take)
                remaining = quantity(remaining - take)
                realised.append(RealisedGain(
                    asset_id=lot.asset_id,
                    lot_id=lot.id,
                    units=take,
                    acquired_on=lot.acquired_on,
                    sold_on=txn.trade_date,
                    proceeds=money(take * price),
                    cost=money(take * lot.cost_per_unit),
                    gain_type=GainType.SHORT_TERM,      # refined by realised_gains()
                    holding_days=(txn.trade_date - lot.acquired_on).days,
                ))
            if remaining > 0:
                # More sold than bought: the import is incomplete. Recording a
                # zero-cost lot would invent a gain, so we leave the shortfall
                # visible to the caller instead.
                realised.append(RealisedGain(
                    asset_id=txn.asset_id or asset_id, lot_id="unmatched",
                    units=remaining, acquired_on=txn.trade_date, sold_on=txn.trade_date,
                    proceeds=money(remaining * price), cost=ZERO,
                    gain_type=GainType.SHORT_TERM, holding_days=0,
                ))
    return [lot for lot in open_lots if lot.open_units > 0], realised


def realised_gains(
    transactions: Sequence[Transaction],
    asset: Asset,
    *,
    rules: TaxRules = INDIA_FY2526,
) -> list[RealisedGain]:
    _, gains = build_lots(transactions)
    return [
        RealisedGain(
            **{**gain.__dict__, "gain_type": classify(asset, gain.acquired_on, gain.sold_on, rules)}
        )
        for gain in gains
    ]


def unrealised_gains(
    lots: Iterable[TaxLot],
    asset: Asset,
    price: Decimal,
    *,
    on: date,
    rules: TaxRules = INDIA_FY2526,
) -> list[UnrealisedPosition]:
    out: list[UnrealisedPosition] = []
    for lot in lots:
        if lot.open_units <= 0:
            continue
        gain_type = classify(asset, lot.acquired_on, on, rules)
        threshold = (
            rules.equity_long_term_months if asset.asset_type in _EQUITY_TYPES
            else rules.other_long_term_months
        )
        long_term_on_days = int(threshold * 30.44)
        held = (on - lot.acquired_on).days
        out.append(UnrealisedPosition(
            asset_id=lot.asset_id,
            lot_id=lot.id,
            units=lot.open_units,
            acquired_on=lot.acquired_on,
            cost=lot.cost_basis,
            value=money(lot.open_units * price),
            gain_type=gain_type,
            holding_days=held,
            days_to_long_term=max(0, long_term_on_days - held) if gain_type != GainType.SLAB else -1,
        ))
    return out


@dataclass
class TaxSummary:
    realised_short_term: Decimal
    realised_long_term: Decimal
    realised_slab: Decimal
    estimated_tax: Decimal
    ltcg_exemption_used: Decimal
    ltcg_exemption_left: Decimal
    harvestable_losses: Decimal
    #: Positions a few weeks short of long-term treatment. Waiting is usually
    #: worth more than any view on the next month's price.
    near_long_term: list[UnrealisedPosition] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "realised_short_term": str(self.realised_short_term),
            "realised_long_term": str(self.realised_long_term),
            "realised_slab": str(self.realised_slab),
            "estimated_tax": str(self.estimated_tax),
            "ltcg_exemption_used": str(self.ltcg_exemption_used),
            "ltcg_exemption_left": str(self.ltcg_exemption_left),
            "harvestable_losses": str(self.harvestable_losses),
            "near_long_term": [p.to_dict() for p in self.near_long_term],
            "notes": list(self.notes),
        }


def tax_summary(
    realised: Sequence[RealisedGain],
    unrealised: Sequence[UnrealisedPosition],
    *,
    marginal_rate: float,
    rules: TaxRules = INDIA_FY2526,
    near_days: int = 60,
) -> TaxSummary:
    """Position for the financial year, plus the two opportunities worth naming.

    Deliberately conservative: the estimate applies the headline rate without
    surcharge, cess or carry-forward of prior-year losses, and says so. A tax
    number that is precise and wrong is worse than one that is approximate and
    labelled.
    """
    short = total(g.gain for g in realised if g.gain_type == GainType.SHORT_TERM)
    long = total(g.gain for g in realised if g.gain_type == GainType.LONG_TERM)
    slab = total(g.gain for g in realised if g.gain_type == GainType.SLAB)

    taxable_long = max(ZERO, long - rules.equity_ltcg_exemption)
    exemption_used = min(max(long, ZERO), rules.equity_ltcg_exemption)
    tax = money(
        as_float(max(short, ZERO)) * rules.equity_stcg_rate
        + as_float(taxable_long) * rules.equity_ltcg_rate
        + as_float(max(slab, ZERO)) * marginal_rate
    )

    losses = total(-p.gain for p in unrealised if p.gain < 0)
    near = [
        p for p in unrealised
        if 0 < p.days_to_long_term <= near_days and p.gain > 0
    ]
    notes = [
        rules.note,
        "Estimate excludes surcharge, cess, carried-forward losses and any "
        "set-off across heads.",
    ]
    if exemption_used < rules.equity_ltcg_exemption:
        notes.append(
            f"{money(rules.equity_ltcg_exemption - exemption_used)} of the annual "
            "equity LTCG exemption is unused this year."
        )
    return TaxSummary(
        realised_short_term=short,
        realised_long_term=long,
        realised_slab=slab,
        estimated_tax=tax,
        ltcg_exemption_used=exemption_used,
        ltcg_exemption_left=money(max(ZERO, rules.equity_ltcg_exemption - exemption_used)),
        harvestable_losses=losses,
        near_long_term=sorted(near, key=lambda p: p.days_to_long_term),
        notes=notes,
    )


def exit_tax_cost(
    positions: Sequence[UnrealisedPosition],
    *,
    marginal_rate: float,
    rules: TaxRules = INDIA_FY2526,
    exemption_left: Decimal | None = None,
) -> Decimal:
    """What selling these positions today would cost in tax.

    The decision engine calls this before proposing any exit: an exit that is
    right on the merits and wrong after tax is still wrong, and a user who
    finds that out afterwards does not come back.
    """
    remaining_exemption = (
        rules.equity_ltcg_exemption if exemption_left is None else exemption_left
    )
    cost = 0.0
    for position in positions:
        gain = as_float(position.gain)
        if gain <= 0:
            continue
        if position.gain_type == GainType.LONG_TERM:
            shielded = min(gain, as_float(remaining_exemption))
            remaining_exemption = money(as_float(remaining_exemption) - shielded)
            cost += (gain - shielded) * rules.equity_ltcg_rate
        elif position.gain_type == GainType.SHORT_TERM:
            cost += gain * rules.equity_stcg_rate
        else:
            cost += gain * marginal_rate
    return money(cost)
