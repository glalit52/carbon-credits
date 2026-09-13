"""Demo data.

A realistic Indian mass-affluent portfolio: about ₹1.1 crore across six funds,
three direct stocks, EPF, a little gold and idle cash, with the problems real
portfolios actually have -- two large-cap funds that own the same thing,
financials exposure no single holding reveals, equity that has drifted above
policy after a good run, and more cash than the plan needs.

It exists so that the dashboard, the eval suite, the CLI demo and the tests all
exercise the same portfolio, and so that anyone reading this repository can run
the whole product in one command without a data contract.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from .domain import (
    Account, AccountType, Asset, AssetType, FinancialProfile, Frequency, Goal,
    GoalType, Holding, Portfolio, SIP, Transaction, TxnType, User, new_id,
)
from .money import money, quantity
from .provenance import Provenance, SourceKind

DEMO_USER_ID = "user_demo"
DEMO_AS_OF = date(2026, 9, 12)


def _provenance(kind: SourceKind, provider: str, reference: str, *, days_old: int = 0) -> Provenance:
    return Provenance(
        kind=kind, provider=provider,
        observed_at=datetime.combine(
            DEMO_AS_OF - timedelta(days=days_old), datetime.min.time(), tzinfo=timezone.utc
        ),
        reference=reference, transformation="demo seed", confidence=1.0,
    )


def demo_user() -> User:
    user = User(
        id=DEMO_USER_ID, email="demo@aicio.local", name="Demo Investor",
        country="IN", base_currency="INR",
    )
    user.grant("portfolio_analysis")
    user.grant("ai_processing")
    return user


def demo_profile() -> FinancialProfile:
    """Risk tolerance deliberately above capacity: it is the most common real
    pattern, and it exercises the part of the policy generator that follows
    capacity rather than appetite."""
    return FinancialProfile(
        user_id=DEMO_USER_ID,
        age_band="35-44",
        dependents=2,
        annual_income=money(4_800_000),
        annual_expenses=money(2_160_000),
        monthly_surplus=money(180_000),
        liabilities=money(3_200_000),
        emergency_reserve=money(1_100_000),
        # A three-point gap: the demo exercises the disclosure that policy
        # follows capacity rather than appetite, which is the commonest real
        # pattern and the one most likely to end in panic-selling.
        risk_tolerance=9,
        risk_capacity=6,
        income_stability="stable",
        marginal_tax_rate=0.30,
        horizon_years=19,
        liquidity_need_months=6,
        max_single_holding_pct=0.10,
        max_sector_pct=0.30,
    )


def demo_goals() -> list[Goal]:
    return [
        # Targets are in today's money; the engine inflates them to the target
        # date. Stating them the other way round is the commonest way a goal
        # plan quietly under-saves by a third.
        Goal(
            id="goal_retire", user_id=DEMO_USER_ID, name="Retirement",
            goal_type=GoalType.RETIREMENT, target_amount=money(25_000_000),
            target_date=date(2045, 4, 1), priority=1,
            current_funding=money(7_800_000), monthly_contribution=money(75_000),
            inflation_rate=0.06, flexible=False,
        ),
        Goal(
            id="goal_education", user_id=DEMO_USER_ID, name="Daughter's university",
            goal_type=GoalType.EDUCATION, target_amount=money(3_200_000),
            target_date=date(2033, 6, 1), priority=2,
            current_funding=money(1_450_000), monthly_contribution=money(27_000),
            inflation_rate=0.08, flexible=False,
        ),
        Goal(
            id="goal_home", user_id=DEMO_USER_ID, name="Second home",
            goal_type=GoalType.HOME, target_amount=money(2_500_000),
            target_date=date(2031, 1, 1), priority=3,
            current_funding=money(900_000), monthly_contribution=money(18_000),
        ),
    ]


def demo_assets() -> dict[str, Asset]:
    """Look-through weights are the published top holdings of each fund.

    Two of the equity funds share most of their top names on purpose: that
    overlap is invisible on a holdings screen and is exactly what the X-ray is
    for.
    """
    large_cap_core = {
        "HDFCBANK": 0.094, "ICICIBANK": 0.081, "RELIANCE": 0.072, "INFY": 0.058,
        "TCS": 0.046, "BHARTIARTL": 0.041, "ITC": 0.033, "LT": 0.031,
        "AXISBANK": 0.028, "KOTAKBANK": 0.026,
    }
    assets = [
        Asset(
            id="ast_ppfas", name="Parag Parikh Flexi Cap Fund - Direct Growth",
            asset_type=AssetType.EQUITY_FUND, isin="INF879O01027", scheme_code="122639",
            issuer="PPFAS Mutual Fund", category="Flexi Cap",
            benchmark="NIFTY 500 TRI", sector="diversified", geography="IN",
            expense_ratio=0.0063, aum_cr=98000,
            holdings_lookthrough={
                "HDFCBANK": 0.078, "BAJAJHLDNG": 0.061, "POWERGRID": 0.055,
                "ITC": 0.046, "COALINDIA": 0.041, "MARUTI": 0.036,
                "HCLTECH": 0.031, "ICICIBANK": 0.029,
            },
        ),
        Asset(
            id="ast_nifty_index", name="UTI Nifty 50 Index Fund - Direct Growth",
            asset_type=AssetType.INDEX_FUND, isin="INF789F1AUR1", scheme_code="120716",
            issuer="UTI Mutual Fund", category="Index", benchmark="NIFTY 50 TRI",
            sector="diversified", geography="IN", expense_ratio=0.0018, aum_cr=22000,
            holdings_lookthrough=large_cap_core,
        ),
        Asset(
            id="ast_bluechip", name="Axis Bluechip Fund - Regular Growth",
            asset_type=AssetType.EQUITY_FUND, isin="INF846K01131", scheme_code="120503",
            issuer="Axis Mutual Fund", category="Large Cap", benchmark="NIFTY 100 TRI",
            sector="diversified", geography="IN", expense_ratio=0.0172, aum_cr=31000,
            holdings_lookthrough={**large_cap_core, "HDFCBANK": 0.091, "TITAN": 0.024},
        ),
        Asset(
            id="ast_smallcap", name="Nippon India Small Cap Fund - Direct Growth",
            asset_type=AssetType.EQUITY_FUND, isin="INF204KB14I5", scheme_code="118778",
            issuer="Nippon India Mutual Fund", category="Small Cap",
            benchmark="NIFTY Smallcap 250 TRI", sector="diversified", geography="IN",
            expense_ratio=0.0071, aum_cr=61000,
            holdings_lookthrough={
                "MULTICOMM": 0.021, "TUBEINVEST": 0.019, "KARURVYSYA": 0.018,
                "ELGIEQUIP": 0.017, "APARINDS": 0.016,
            },
        ),
        Asset(
            id="ast_elss", name="Mirae Asset ELSS Tax Saver - Direct Growth",
            asset_type=AssetType.ELSS, isin="INF769K01DP7", scheme_code="135781",
            issuer="Mirae Asset Mutual Fund", category="ELSS", benchmark="NIFTY 500 TRI",
            sector="diversified", geography="IN", expense_ratio=0.0057,
            holdings_lookthrough=large_cap_core,
        ),
        Asset(
            id="ast_shortdebt", name="HDFC Short Term Debt Fund - Direct Growth",
            asset_type=AssetType.DEBT_FUND, isin="INF179K01XQ0", scheme_code="119063",
            issuer="HDFC Mutual Fund", category="Short Duration",
            benchmark="NIFTY Short Duration Debt Index", sector="fixed income",
            geography="IN", expense_ratio=0.0030,
        ),
        Asset(
            id="ast_reliance", name="Reliance Industries", asset_type=AssetType.STOCK,
            isin="INE002A01018", ticker="RELIANCE", sector="energy", geography="IN",
        ),
        Asset(
            id="ast_hdfcbank", name="HDFC Bank", asset_type=AssetType.STOCK,
            isin="INE040A01034", ticker="HDFCBANK", sector="financials", geography="IN",
        ),
        Asset(
            id="ast_tatamotors", name="Tata Motors", asset_type=AssetType.STOCK,
            isin="INE155A01022", ticker="TATAMOTORS", sector="automobiles", geography="IN",
        ),
        Asset(
            id="ast_goldetf", name="Nippon India Gold BeES", asset_type=AssetType.GOLD_ETF,
            isin="INF204KB17I5", ticker="GOLDBEES", sector="gold", geography="IN",
        ),
        Asset(
            id="ast_epf", name="Employees' Provident Fund", asset_type=AssetType.EPF,
            issuer="EPFO", sector="fixed income", geography="IN",
        ),
    ]
    return {asset.id: asset for asset in assets}


def demo_accounts() -> list[Account]:
    return [
        Account(id="acc_mf", user_id=DEMO_USER_ID, institution="CAMS/KFintech folios",
                account_type=AccountType.MF_FOLIO, identifier_masked="****3391",
                source=SourceKind.USER_UPLOAD),
        Account(id="acc_demat", user_id=DEMO_USER_ID, institution="Zerodha",
                account_type=AccountType.DEMAT, identifier_masked="****4210",
                source=SourceKind.CONNECTED_ACCOUNT,
                connected_at=datetime(2026, 6, 1, tzinfo=timezone.utc)),
        Account(id="acc_epf", user_id=DEMO_USER_ID, institution="EPFO",
                account_type=AccountType.RETIREMENT, identifier_masked="****7781",
                source=SourceKind.USER_INPUT),
    ]


#: (asset id, account, units, average cost, price, days since last refresh)
_POSITIONS: list[tuple[str, str, float, float, float, int]] = [
    ("ast_ppfas",       "acc_mf",    32_000.0,  52.40,  78.12, 0),
    ("ast_nifty_index", "acc_mf",    46_000.0,  21.10,  29.64, 0),
    ("ast_bluechip",    "acc_mf",    38_500.0,  44.90,  52.18, 0),
    ("ast_smallcap",    "acc_mf",     8_600.0, 118.30, 196.44, 0),
    ("ast_elss",        "acc_mf",    18_400.0,  33.20,  47.85, 0),
    ("ast_shortdebt",   "acc_mf",    42_000.0,  24.10,  28.74, 0),
    ("ast_reliance",    "acc_demat",    240.0, 2_280.0, 2_960.50, 0),
    ("ast_hdfcbank",    "acc_demat",    420.0, 1_480.0, 1_702.30, 0),
    ("ast_tatamotors",  "acc_demat",    600.0,   840.0,   712.60, 0),
    ("ast_goldetf",     "acc_demat",  4_200.0,    58.4,    83.15, 0),
    ("ast_epf",         "acc_epf",  1_420_000.0,   1.0,     1.0, 95),
]


def demo_portfolio(*, as_of: date = DEMO_AS_OF) -> Portfolio:
    assets = demo_assets()
    holdings: list[Holding] = []
    transactions: list[Transaction] = []

    for asset_id, account_id, units, cost, price, stale_days in _POSITIONS:
        source = (
            SourceKind.CONNECTED_ACCOUNT if account_id == "acc_demat"
            else SourceKind.USER_INPUT if account_id == "acc_epf"
            else SourceKind.USER_UPLOAD
        )
        holdings.append(Holding(
            id=new_id("hld", account_id, asset_id),
            account_id=account_id, asset_id=asset_id,
            units=quantity(units), average_cost=money(cost), current_price=money(price),
            as_of=as_of,
            provenance=_provenance(source, "demo", asset_id, days_old=stale_days),
        ))
        transactions.extend(_purchase_history(asset_id, account_id, units, cost, as_of))

    sips = [
        SIP(id="sip_ppfas", user_id=DEMO_USER_ID, account_id="acc_mf", asset_id="ast_ppfas",
            amount=money(45_000), frequency=Frequency.MONTHLY,
            start_date=date(2021, 4, 5), goal_id="goal_retire"),
        SIP(id="sip_index", user_id=DEMO_USER_ID, account_id="acc_mf",
            asset_id="ast_nifty_index", amount=money(30_000), frequency=Frequency.MONTHLY,
            start_date=date(2022, 1, 5), goal_id="goal_retire"),
        SIP(id="sip_smallcap", user_id=DEMO_USER_ID, account_id="acc_mf",
            asset_id="ast_smallcap", amount=money(15_000), frequency=Frequency.MONTHLY,
            start_date=date(2023, 6, 5), goal_id="goal_education"),
        SIP(id="sip_elss", user_id=DEMO_USER_ID, account_id="acc_mf",
            asset_id="ast_elss", amount=money(12_000), frequency=Frequency.MONTHLY,
            start_date=date(2022, 4, 5), goal_id="goal_education"),
        SIP(id="sip_debt", user_id=DEMO_USER_ID, account_id="acc_mf",
            asset_id="ast_shortdebt", amount=money(18_000), frequency=Frequency.MONTHLY,
            start_date=date(2024, 2, 5), goal_id="goal_home"),
    ]

    return Portfolio(
        user_id=DEMO_USER_ID,
        as_of=as_of,
        accounts=demo_accounts(),
        assets=assets,
        holdings=holdings,
        transactions=transactions,
        sips=sips,
        cash=money(1_850_000),
        external_liabilities=money(3_200_000),
    )


def _purchase_history(
    asset_id: str, account_id: str, units: float, cost: float, as_of: date
) -> list[Transaction]:
    """Six instalments spread over three years.

    Enough history for XIRR and FIFO lots to be meaningful, and it deliberately
    leaves the most recent instalment inside the twelve-month short-term
    window so the tax rules have something real to work on.
    """
    out: list[Transaction] = []
    slices = 6
    per_slice = units / slices
    # 40, 32, 24, 16, 8 and 2 months ago: the last one is short-term.
    offsets = [40, 32, 24, 16, 8, 2]
    for index, months in enumerate(offsets):
        trade_date = _months_before(as_of, months)
        # Cost rises through the series, so the oldest lots hold the largest
        # gains -- the ordinary shape of a portfolio built by SIP.
        price = cost * (0.82 + 0.06 * index)
        out.append(Transaction(
            id=new_id("txn", account_id, asset_id, trade_date.isoformat(), index),
            account_id=account_id, asset_id=asset_id,
            txn_type=TxnType.SIP if index < slices - 1 else TxnType.BUY,
            trade_date=trade_date,
            units=quantity(per_slice), price=money(price), amount=money(per_slice * price),
            provenance=_provenance(SourceKind.USER_UPLOAD, "demo", f"{asset_id}:{index}"),
        ))
    return out


def _months_before(anchor: date, months: int) -> date:
    year = anchor.year - (months // 12)
    month = anchor.month - (months % 12)
    if month <= 0:
        month += 12
        year -= 1
    day = min(anchor.day, 28)
    return date(year, month, day)


#: Quality scores as the research layer would produce them. Axis Bluechip is
#: the weak one -- high expense ratio, persistent underperformance -- which is
#: what gives the fund-quality rule something to find.
DEMO_QUALITY: dict[str, float] = {
    "ast_ppfas": 82.0,
    "ast_nifty_index": 74.0,
    "ast_bluechip": 38.0,
    "ast_smallcap": 66.0,
    "ast_elss": 71.0,
    "ast_shortdebt": 69.0,
}

DEMO_BEHAVIOUR: dict[str, float] = {
    "annual_turnover": 0.18,
    "months_since_review": 11,
    "ignored_high_priority": 1,
}


def demo_bundle(*, as_of: date = DEMO_AS_OF) -> dict[str, Any]:
    """Everything needed to run the product end to end."""
    from .ips import generate_policy

    profile = demo_profile()
    goals = demo_goals()
    return {
        "user": demo_user(),
        "profile": profile,
        "goals": goals,
        "portfolio": demo_portfolio(as_of=as_of),
        "policy": generate_policy(profile, goals, today=as_of),
        "quality": DEMO_QUALITY,
        "behaviour": DEMO_BEHAVIOUR,
        "as_of": as_of,
    }
