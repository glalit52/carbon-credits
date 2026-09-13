"""The entities a personal balance sheet is actually made of.

Modelled around the questions a private banker asks a client, not around what
is convenient to store. Three modelling choices are worth defending because
they cost more than the obvious alternative:

*   **Risk tolerance and risk capacity are separate fields.** Willingness to
    watch a portfolio fall and ability to survive it falling are different
    quantities, and every product that collapses them into one "risk profile"
    slider ends up recommending equity to someone who cannot afford it.
*   **Tax lots are first class, not derived at report time.** Realised gain in
    India depends on which units you sell, and a system that computes lots
    lazily will eventually compute them two different ways.
*   **Every holding keeps its provenance.** A position parsed from a PDF with
    0.7 confidence is a different thing from one pulled from a broker API, and
    the difference has to survive all the way to the recommendation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from .money import ZERO, as_float, money, quantity, total
from .provenance import Provenance, SourceKind, user_input, utcnow


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

class AssetClass(str, Enum):
    """The level at which allocation policy is written."""

    EQUITY = "equity"
    DEBT = "debt"
    CASH = "cash"
    GOLD = "gold"
    REAL_ESTATE = "real_estate"
    ALTERNATIVE = "alternative"
    CRYPTO = "crypto"
    OTHER = "other"


class AssetType(str, Enum):
    """The instrument itself. Several types map to one class -- an ELSS fund
    and a direct share are both equity, but only one of them has a lock-in."""

    EQUITY_FUND = "equity_fund"
    DEBT_FUND = "debt_fund"
    HYBRID_FUND = "hybrid_fund"
    INDEX_FUND = "index_fund"
    ELSS = "elss"
    LIQUID_FUND = "liquid_fund"
    STOCK = "stock"
    ETF = "etf"
    BOND = "bond"
    FIXED_DEPOSIT = "fixed_deposit"
    PPF = "ppf"
    EPF = "epf"
    NPS = "nps"
    SGB = "sgb"
    GOLD_ETF = "gold_etf"
    REIT = "reit"
    SAVINGS = "savings"
    CRYPTO = "crypto"
    PROPERTY = "property"
    OTHER = "other"


#: The class each instrument type contributes to. Hybrids are split at
#: look-through time by their actual equity share, so the static map only
#: records where an instrument starts.
ASSET_CLASS_OF: dict[AssetType, AssetClass] = {
    AssetType.EQUITY_FUND: AssetClass.EQUITY,
    AssetType.INDEX_FUND: AssetClass.EQUITY,
    AssetType.ELSS: AssetClass.EQUITY,
    AssetType.STOCK: AssetClass.EQUITY,
    AssetType.ETF: AssetClass.EQUITY,
    AssetType.HYBRID_FUND: AssetClass.EQUITY,
    AssetType.DEBT_FUND: AssetClass.DEBT,
    AssetType.LIQUID_FUND: AssetClass.DEBT,
    AssetType.BOND: AssetClass.DEBT,
    AssetType.FIXED_DEPOSIT: AssetClass.DEBT,
    AssetType.PPF: AssetClass.DEBT,
    AssetType.EPF: AssetClass.DEBT,
    AssetType.NPS: AssetClass.DEBT,
    AssetType.SGB: AssetClass.GOLD,
    AssetType.GOLD_ETF: AssetClass.GOLD,
    AssetType.REIT: AssetClass.REAL_ESTATE,
    AssetType.PROPERTY: AssetClass.REAL_ESTATE,
    AssetType.SAVINGS: AssetClass.CASH,
    AssetType.CRYPTO: AssetClass.CRYPTO,
    AssetType.OTHER: AssetClass.OTHER,
}

#: Instruments the user cannot simply sell. A recommendation that ignores this
#: is not a recommendation, it is a trap.
LOCKED_TYPES: dict[AssetType, str] = {
    AssetType.ELSS: "3-year lock-in per instalment",
    AssetType.PPF: "15-year term with limited partial withdrawal",
    AssetType.EPF: "withdrawal restricted to statutory conditions",
    AssetType.NPS: "locked to retirement with limited exit",
    AssetType.SGB: "8-year term, exit window from year 5",
    AssetType.PROPERTY: "illiquid; sale takes months",
}


class AccountType(str, Enum):
    DEMAT = "demat"
    MF_FOLIO = "mf_folio"
    BANK = "bank"
    RETIREMENT = "retirement"
    BROKERAGE = "brokerage"
    NPS_ACCOUNT = "nps_account"
    OTHER = "other"


class TxnType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    SIP = "sip"
    SWITCH_IN = "switch_in"
    SWITCH_OUT = "switch_out"
    DIVIDEND = "dividend"
    INTEREST = "interest"
    BONUS = "bonus"
    SPLIT = "split"
    FEE = "fee"
    TAX = "tax"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"


#: Transactions that add units to a position, and so open a tax lot.
INFLOW_TYPES = {TxnType.BUY, TxnType.SIP, TxnType.SWITCH_IN, TxnType.BONUS, TxnType.TRANSFER_IN}
OUTFLOW_TYPES = {TxnType.SELL, TxnType.SWITCH_OUT, TxnType.TRANSFER_OUT}


class Action(str, Enum):
    """The complete set of things the product is willing to say.

    DO_NOTHING is not a fallback for an empty result -- it is a first-class
    conclusion that the portfolio was examined and warrants no change.
    """

    BUY_INCREASE = "BUY_INCREASE"
    HOLD = "HOLD"
    REVIEW = "REVIEW"
    REDUCE = "REDUCE"
    EXIT_SWITCH = "EXIT_SWITCH"
    DO_NOTHING = "DO_NOTHING"


#: Actions that move money and therefore need a suitability check and explicit
#: user approval before anything is presented as executable.
MATERIAL_ACTIONS = {Action.BUY_INCREASE, Action.REDUCE, Action.EXIT_SWITCH}


class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


PRIORITY_RANK = {Priority.CRITICAL: 0, Priority.HIGH: 1, Priority.MEDIUM: 2, Priority.LOW: 3}


class GoalType(str, Enum):
    RETIREMENT = "retirement"
    EDUCATION = "education"
    HOME = "home"
    EMERGENCY = "emergency"
    WEALTH = "wealth"
    VEHICLE = "vehicle"
    TRAVEL = "travel"
    OTHER = "other"


class Frequency(str, Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    WEEKLY = "weekly"
    ANNUAL = "annual"
    ONE_TIME = "one_time"


PER_YEAR = {
    Frequency.MONTHLY: 12,
    Frequency.QUARTERLY: 4,
    Frequency.WEEKLY: 52,
    Frequency.ANNUAL: 1,
    Frequency.ONE_TIME: 0,
}


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------

@dataclass
class User:
    id: str
    email: str
    name: str = ""
    country: str = "IN"
    base_currency: str = "INR"
    timezone: str = "Asia/Kolkata"
    locale: str = "en-IN"
    created_at: datetime = field(default_factory=utcnow)
    #: Consent is per-purpose and revocable; one global "I agree" is not a
    #: lawful basis for pulling someone's bank feed.
    consents: dict[str, datetime] = field(default_factory=dict)
    quiet_hours: tuple[int, int] = (22, 7)
    notification_channels: tuple[str, ...] = ("in_app",)

    def has_consent(self, purpose: str) -> bool:
        return purpose in self.consents

    def grant(self, purpose: str, *, at: datetime | None = None) -> None:
        self.consents[purpose] = at or utcnow()

    def revoke(self, purpose: str) -> None:
        self.consents.pop(purpose, None)

    def in_quiet_hours(self, when: datetime) -> bool:
        start, end = self.quiet_hours
        hour = when.hour
        if start <= end:
            return start <= hour < end
        return hour >= start or hour < end


@dataclass
class FinancialProfile:
    """Financial DNA. The inputs that make a recommendation personal."""

    user_id: str
    age_band: str = "35-44"
    dependents: int = 0
    annual_income: Decimal = ZERO
    annual_expenses: Decimal = ZERO
    monthly_surplus: Decimal = ZERO
    liabilities: Decimal = ZERO
    emergency_reserve: Decimal = ZERO
    #: 1-10. Willingness to tolerate a fall. Self-reported, behavioural.
    risk_tolerance: int = 5
    #: 1-10. Ability to absorb a fall without damaging the plan. Derived from
    #: income stability, horizon, dependents and reserves -- not self-reported.
    risk_capacity: int = 5
    income_stability: str = "stable"        # stable | variable | concentrated
    tax_regime: str = "new"                 # India: old | new
    marginal_tax_rate: float = 0.30
    horizon_years: int = 20
    liquidity_need_months: int = 6
    excluded_sectors: tuple[str, ...] = ()
    preferred_geographies: tuple[str, ...] = ("IN",)
    max_single_holding_pct: float = 0.10
    max_sector_pct: float = 0.30
    updated_at: datetime = field(default_factory=utcnow)
    provenance: Provenance = field(default_factory=lambda: user_input("onboarding"))

    def __post_init__(self) -> None:
        for name in ("risk_tolerance", "risk_capacity"):
            value = getattr(self, name)
            if not 1 <= value <= 10:
                raise ValueError(f"{name} must be 1-10, got {value}")

    @property
    def effective_risk(self) -> int:
        """Policy is written to the lower of the two.

        A client who wants aggressive equity but cannot survive a drawdown gets
        the portfolio they can survive. Going the other way -- capacity high,
        tolerance low -- would build a portfolio the client abandons at the
        first fall, which is worse than a conservative one they keep.
        """
        return min(self.risk_tolerance, self.risk_capacity)

    @property
    def risk_gap(self) -> int:
        """Positive when the user wants more risk than they can afford. Worth
        surfacing in onboarding, because it predicts panic-selling."""
        return self.risk_tolerance - self.risk_capacity

    @property
    def emergency_months_covered(self) -> float:
        monthly = as_float(self.annual_expenses) / 12
        if monthly <= 0:
            return 0.0
        return as_float(self.emergency_reserve) / monthly

    @property
    def savings_rate(self) -> float:
        income = as_float(self.annual_income)
        if income <= 0:
            return 0.0
        return max(0.0, (income - as_float(self.annual_expenses)) / income)


@dataclass
class Goal:
    id: str
    user_id: str
    name: str
    goal_type: GoalType
    target_amount: Decimal
    target_date: date
    priority: int = 3                        # 1 highest
    current_funding: Decimal = ZERO
    monthly_contribution: Decimal = ZERO
    inflation_rate: float = 0.06
    #: Goals a user cannot postpone (a child's fees, a retirement date already
    #: committed to) get treated as constraints rather than aspirations.
    flexible: bool = True
    linked_account_ids: tuple[str, ...] = ()
    assumptions: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)

    def years_remaining(self, *, today: date | None = None) -> float:
        delta = (self.target_date - (today or date.today())).days
        return max(0.0, delta / 365.25)

    def inflated_target(self, *, today: date | None = None) -> Decimal:
        """A goal quoted in today's money is a goal that will be missed."""
        years = self.years_remaining(today=today)
        return money(as_float(self.target_amount) * (1 + self.inflation_rate) ** years)

    @property
    def horizon_bucket(self) -> str:
        years = self.years_remaining()
        if years < 3:
            return "short"
        if years < 7:
            return "medium"
        return "long"


# ---------------------------------------------------------------------------
# Instruments and positions
# ---------------------------------------------------------------------------

@dataclass
class Asset:
    """An instrument. ``id`` is the resolved internal identifier; ``isin`` and
    ``scheme_code`` are how the outside world names the same thing."""

    id: str
    name: str
    asset_type: AssetType
    isin: str = ""
    scheme_code: str = ""
    ticker: str = ""
    issuer: str = ""                        # AMC or company
    currency: str = "INR"
    category: str = ""                      # "large cap", "flexi cap", "banking"
    benchmark: str = ""
    sector: str = ""
    geography: str = "IN"
    expense_ratio: float | None = None
    aum_cr: float | None = None
    #: For funds: the look-through portfolio, ticker -> weight (0..1). This is
    #: what makes hidden concentration visible.
    holdings_lookthrough: dict[str, float] = field(default_factory=dict)
    #: For hybrids: the true equity share, used to split the position across
    #: asset classes instead of miscounting a balanced fund as pure equity.
    equity_share: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def asset_class(self) -> AssetClass:
        if self.asset_type == AssetType.HYBRID_FUND and self.equity_share is not None:
            return AssetClass.EQUITY if self.equity_share >= 0.5 else AssetClass.DEBT
        return ASSET_CLASS_OF.get(self.asset_type, AssetClass.OTHER)

    @property
    def is_fund(self) -> bool:
        return self.asset_type in {
            AssetType.EQUITY_FUND, AssetType.DEBT_FUND, AssetType.HYBRID_FUND,
            AssetType.INDEX_FUND, AssetType.ELSS, AssetType.LIQUID_FUND,
        }

    @property
    def lock_in(self) -> str:
        return LOCKED_TYPES.get(self.asset_type, "")

    def class_split(self) -> dict[AssetClass, float]:
        """How one rupee in this instrument divides across asset classes."""
        if self.asset_type == AssetType.HYBRID_FUND and self.equity_share is not None:
            share = max(0.0, min(1.0, self.equity_share))
            return {AssetClass.EQUITY: share, AssetClass.DEBT: 1 - share}
        return {ASSET_CLASS_OF.get(self.asset_type, AssetClass.OTHER): 1.0}


@dataclass
class Account:
    id: str
    user_id: str
    institution: str
    account_type: AccountType
    currency: str = "INR"
    identifier_masked: str = ""             # never store a full account number
    source: SourceKind = SourceKind.USER_UPLOAD
    connected_at: datetime | None = None
    last_synced_at: datetime | None = None
    active: bool = True


@dataclass
class Transaction:
    id: str
    account_id: str
    asset_id: str
    txn_type: TxnType
    trade_date: date
    units: Decimal = ZERO
    price: Decimal = ZERO
    amount: Decimal = ZERO
    fees: Decimal = ZERO
    provenance: Provenance = field(default_factory=lambda: user_input("import"))
    note: str = ""

    def __post_init__(self) -> None:
        self.units = quantity(self.units)
        self.price = money(self.price)
        self.amount = money(self.amount)
        self.fees = money(self.fees)
        if self.amount == ZERO and self.units and self.price:
            self.amount = money(self.units * self.price)

    @property
    def signed_units(self) -> Decimal:
        if self.txn_type in INFLOW_TYPES:
            return self.units
        if self.txn_type in OUTFLOW_TYPES:
            return -self.units
        return ZERO

    @property
    def cash_flow(self) -> Decimal:
        """Cash leaving (negative) or reaching (positive) the user's pocket.

        The sign convention is the investor's, not the portfolio's: money spent
        on a purchase is negative, a redemption or dividend is positive. XIRR
        depends on this being consistent, so it lives here rather than in each
        caller.
        """
        if self.txn_type in {TxnType.BUY, TxnType.SIP, TxnType.SWITCH_IN, TxnType.TRANSFER_IN}:
            return -(self.amount + self.fees)
        if self.txn_type in {TxnType.SELL, TxnType.SWITCH_OUT, TxnType.TRANSFER_OUT}:
            return self.amount - self.fees
        if self.txn_type in {TxnType.DIVIDEND, TxnType.INTEREST}:
            return self.amount
        if self.txn_type in {TxnType.FEE, TxnType.TAX}:
            return -self.amount
        return ZERO


@dataclass
class TaxLot:
    """One purchase, tracked to its sale.

    Indian capital-gains tax turns on holding period per lot, so lots are
    tracked individually rather than netted. FIFO is the statutory default for
    both equity and mutual funds; :mod:`aicio.engine.taxlots` implements it.
    """

    id: str
    asset_id: str
    account_id: str
    acquired_on: date
    units: Decimal
    cost_per_unit: Decimal
    closed_units: Decimal = ZERO
    txn_id: str = ""

    def __post_init__(self) -> None:
        self.units = quantity(self.units)
        self.closed_units = quantity(self.closed_units)
        self.cost_per_unit = money(self.cost_per_unit)

    @property
    def open_units(self) -> Decimal:
        return quantity(self.units - self.closed_units)

    @property
    def cost_basis(self) -> Decimal:
        return money(self.open_units * self.cost_per_unit)

    def holding_days(self, *, on: date | None = None) -> int:
        return ((on or date.today()) - self.acquired_on).days


@dataclass
class Holding:
    """A position: units of one asset inside one account."""

    id: str
    account_id: str
    asset_id: str
    units: Decimal
    average_cost: Decimal
    current_price: Decimal
    as_of: date
    provenance: Provenance = field(default_factory=lambda: user_input("import"))
    lots: list[TaxLot] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.units = quantity(self.units)
        self.average_cost = money(self.average_cost)
        self.current_price = money(self.current_price)

    @property
    def market_value(self) -> Decimal:
        return money(self.units * self.current_price)

    @property
    def invested(self) -> Decimal:
        return money(self.units * self.average_cost)

    @property
    def unrealised_gain(self) -> Decimal:
        return money(self.market_value - self.invested)

    @property
    def unrealised_pct(self) -> float:
        invested = as_float(self.invested)
        if invested == 0:
            return 0.0
        return as_float(self.unrealised_gain) / invested


@dataclass
class SIP:
    id: str
    user_id: str
    account_id: str
    asset_id: str
    amount: Decimal
    frequency: Frequency = Frequency.MONTHLY
    start_date: date = field(default_factory=date.today)
    end_date: date | None = None
    active: bool = True
    goal_id: str = ""
    day_of_month: int = 5

    @property
    def annual_amount(self) -> Decimal:
        return money(as_float(self.amount) * PER_YEAR[self.frequency])


@dataclass
class Portfolio:
    """Everything the user owns, assembled for one point in time.

    Deliberately a value object: the engine takes one of these and returns
    numbers, so any analysis can be re-run later from a stored snapshot and
    produce the same answer. That reproducibility is what lets us explain a
    recommendation made three months ago.
    """

    user_id: str
    as_of: date
    accounts: list[Account] = field(default_factory=list)
    assets: dict[str, Asset] = field(default_factory=dict)
    holdings: list[Holding] = field(default_factory=list)
    transactions: list[Transaction] = field(default_factory=list)
    sips: list[SIP] = field(default_factory=list)
    cash: Decimal = ZERO
    external_liabilities: Decimal = ZERO

    def asset(self, asset_id: str) -> Asset:
        try:
            return self.assets[asset_id]
        except KeyError:
            raise KeyError(f"unknown asset {asset_id!r}; normalise before analysing") from None

    def account(self, account_id: str) -> Account | None:
        for account in self.accounts:
            if account.id == account_id:
                return account
        return None

    @property
    def market_value(self) -> Decimal:
        return total(h.market_value for h in self.holdings)

    @property
    def invested(self) -> Decimal:
        return total(h.invested for h in self.holdings)

    @property
    def net_worth(self) -> Decimal:
        return money(self.market_value + self.cash - self.external_liabilities)

    @property
    def unrealised_gain(self) -> Decimal:
        return money(self.market_value - self.invested)

    def holdings_of(self, asset_id: str) -> list[Holding]:
        return [h for h in self.holdings if h.asset_id == asset_id]

    def transactions_for(self, asset_id: str) -> list[Transaction]:
        return sorted(
            (t for t in self.transactions if t.asset_id == asset_id),
            key=lambda t: t.trade_date,
        )

    def active_sips(self) -> list[SIP]:
        return [s for s in self.sips if s.active]

    @property
    def monthly_sip_total(self) -> Decimal:
        return total(money(as_float(s.annual_amount) / 12) for s in self.active_sips())

    def stale_holdings(self, *, now: datetime | None = None) -> list[Holding]:
        return [h for h in self.holdings if h.provenance.is_stale(now=now)]

    def fingerprint(self) -> str:
        """Content hash of the inputs an analysis depends on.

        Stored on every recommendation so that "re-run the engine on exactly
        what it saw" is a single lookup rather than an archaeology project.
        """
        parts = [self.user_id, self.as_of.isoformat(), str(self.cash)]
        for holding in sorted(self.holdings, key=lambda h: (h.account_id, h.asset_id)):
            parts.append(f"{holding.account_id}|{holding.asset_id}|{holding.units}|{holding.current_price}")
        for sip in sorted(self.active_sips(), key=lambda s: s.id):
            parts.append(f"sip|{sip.asset_id}|{sip.amount}|{sip.frequency.value}")
        return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

@dataclass
class Evidence:
    """A pointer from a recommendation back to what justified it."""

    label: str
    fact_ids: tuple[str, ...] = ()
    detail: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "fact_ids": list(self.fact_ids),
            "detail": self.detail,
            "source": self.source,
        }


@dataclass
class Recommendation:
    """The product's unit of output.

    Every field below is required by the PRD's recommendation schema, and the
    engine refuses to emit a material action missing evidence, risks or
    counterarguments -- see :func:`validate`.
    """

    id: str
    user_id: str
    action: Action
    subject_id: str                      # asset id, account id or "portfolio"
    subject_label: str
    priority: Priority
    confidence: float
    headline: str
    reasons: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    portfolio_impact: str = ""
    tax_impact: str = ""
    risks: list[str] = field(default_factory=list)
    counterarguments: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    suggested_amount: Decimal | None = None
    review_by: date | None = None
    expires_on: date | None = None
    rule_id: str = ""
    engine_version: str = ""
    portfolio_fingerprint: str = ""
    created_at: datetime = field(default_factory=utcnow)
    goal_ids: tuple[str, ...] = ()
    #: Set by the suitability gate. A recommendation that fails it is stored
    #: (so we can audit what the engine wanted to say) but never shown.
    suppressed_reason: str = ""

    @property
    def material(self) -> bool:
        return self.action in MATERIAL_ACTIONS

    @property
    def presentable(self) -> bool:
        return not self.suppressed_reason

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not 0.0 <= self.confidence <= 1.0:
            problems.append("confidence must be between 0 and 1")
        if not self.headline:
            problems.append("headline is required")
        if not self.reasons:
            problems.append("a recommendation without reasons cannot be explained")
        if self.material:
            if not self.evidence:
                problems.append("material actions require evidence references")
            if not self.risks:
                problems.append("material actions must state their risks")
            if not self.counterarguments:
                problems.append("material actions must state the case against")
            if self.review_by is None:
                problems.append("material actions need a review date")
        if not self.engine_version:
            problems.append("engine version is required for reproducibility")
        return problems

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action": self.action.value,
            "subject_id": self.subject_id,
            "subject_label": self.subject_label,
            "priority": self.priority.value,
            "confidence": round(self.confidence, 4),
            "headline": self.headline,
            "reasons": list(self.reasons),
            "evidence": [e.to_dict() for e in self.evidence],
            "portfolio_impact": self.portfolio_impact,
            "tax_impact": self.tax_impact,
            "risks": list(self.risks),
            "counterarguments": list(self.counterarguments),
            "alternatives": list(self.alternatives),
            "suggested_amount": str(self.suggested_amount) if self.suggested_amount is not None else None,
            "review_by": self.review_by.isoformat() if self.review_by else None,
            "expires_on": self.expires_on.isoformat() if self.expires_on else None,
            "rule_id": self.rule_id,
            "engine_version": self.engine_version,
            "portfolio_fingerprint": self.portfolio_fingerprint,
            "created_at": self.created_at.isoformat(),
            "goal_ids": list(self.goal_ids),
            "suppressed_reason": self.suppressed_reason,
        }


class AlertStatus(str, Enum):
    OPEN = "open"
    SNOOZED = "snoozed"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"


@dataclass
class Alert:
    id: str
    user_id: str
    alert_type: str
    severity: Priority
    title: str
    body: str
    #: Identity of the underlying *state*, not of this notification. Two runs
    #: that find the same breach produce the same key, which is what makes
    #: de-duplication possible without heuristics.
    dedupe_key: str = ""
    status: AlertStatus = AlertStatus.OPEN
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    snooze_until: datetime | None = None
    recommendation_id: str = ""
    useful: bool | None = None
    fact_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.alert_type,
            "severity": self.severity.value,
            "title": self.title,
            "body": self.body,
            "dedupe_key": self.dedupe_key,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "snooze_until": self.snooze_until.isoformat() if self.snooze_until else None,
            "recommendation_id": self.recommendation_id,
            "useful": self.useful,
            "fact_ids": list(self.fact_ids),
        }


@dataclass
class PortfolioSnapshot:
    user_id: str
    as_of: date
    net_worth: Decimal
    invested: Decimal
    market_value: Decimal
    cash: Decimal
    allocation: dict[str, float]
    health_score: float
    xirr: float | None = None
    fingerprint: str = ""


@dataclass
class Message:
    role: str                                # user | assistant | system | tool
    content: str
    created_at: datetime = field(default_factory=utcnow)
    fact_ids: tuple[str, ...] = ()
    tool_name: str = ""


@dataclass
class Conversation:
    id: str
    user_id: str
    messages: list[Message] = field(default_factory=list)
    recommendation_ids: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=utcnow)

    def add(self, role: str, content: str, **kwargs: Any) -> Message:
        message = Message(role=role, content=content, **kwargs)
        self.messages.append(message)
        return message

    def transcript(self, limit: int = 12) -> list[Message]:
        return [m for m in self.messages if m.role in {"user", "assistant"}][-limit:]


class DecisionOutcome(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    EXPIRED = "expired"
    EXECUTED = "executed"


@dataclass
class DecisionRecord:
    """What the user did with a recommendation, and what happened next.

    This is the memory that makes personalisation compound: a user who has
    declined three "reduce gold" suggestions should stop being shown a fourth.
    """

    id: str
    user_id: str
    recommendation_id: str
    outcome: DecisionOutcome
    decided_at: datetime = field(default_factory=utcnow)
    note: str = ""
    outcome_value: Decimal | None = None
    reviewed_on: date | None = None


def new_id(prefix: str, *parts: Any) -> str:
    """Deterministic identifiers.

    Random UUIDs would make every re-run of the engine produce "new"
    recommendations for an unchanged portfolio, which would in turn make
    de-duplication and outcome tracking impossible. Hashing the meaning of the
    thing keeps identity stable across runs.
    """
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:16]
    return f"{prefix}_{digest}"
