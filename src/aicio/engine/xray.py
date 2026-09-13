"""Portfolio X-Ray: what you actually own, under the wrappers.

This is the feature the PRD calls the first visual aha moment, and the reason
is arithmetic rather than design. A user who owns four large-cap funds, an
index fund and some direct HDFC Bank shares has, in nearly every case, one
position repeated six times. Nothing in a normal holdings screen shows that.
Look-through does: it pushes each fund down into its constituents and adds up
the exposure that results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..domain import Asset, AssetClass, AssetType, Portfolio
from ..money import as_float

#: Instruments that are not claims on a company. A provident fund balance or a
#: fixed deposit belongs in the asset-class and sector views, but listing it as
#: a "company exposure" makes the single-name concentration check nonsense --
#: EPF would show up as the user's largest holding in a business.
_NON_CORPORATE = {
    AssetType.EPF, AssetType.PPF, AssetType.NPS, AssetType.FIXED_DEPOSIT,
    AssetType.SAVINGS, AssetType.PROPERTY, AssetType.SGB, AssetType.GOLD_ETF,
    AssetType.OTHER,
}


@dataclass
class Exposure:
    key: str
    label: str
    value: float
    weight: float
    #: Which of the user's holdings contribute, and how much. Without this the
    #: X-ray is a pretty chart nobody can act on.
    contributors: list[tuple[str, str, float]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "value": round(self.value, 2),
            "weight": round(self.weight, 6),
            "contributors": [
                {"asset_id": a, "label": l, "value": round(v, 2)} for a, l, v in self.contributors
            ],
        }


@dataclass
class XRay:
    total: float
    by_company: list[Exposure]
    by_sector: list[Exposure]
    by_geography: list[Exposure]
    by_asset_class: list[Exposure]
    #: Value sitting in funds whose constituents we do not have. Reported
    #: rather than silently dropped, because an X-ray with a hole in it that
    #: does not say so is worse than no X-ray.
    unresolved_value: float = 0.0

    @property
    def coverage(self) -> float:
        if self.total <= 0:
            return 0.0
        return 1.0 - self.unresolved_value / self.total

    def top_company(self) -> Exposure | None:
        return self.by_company[0] if self.by_company else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": round(self.total, 2),
            "coverage": round(self.coverage, 4),
            "unresolved_value": round(self.unresolved_value, 2),
            "by_company": [e.to_dict() for e in self.by_company],
            "by_sector": [e.to_dict() for e in self.by_sector],
            "by_geography": [e.to_dict() for e in self.by_geography],
            "by_asset_class": [e.to_dict() for e in self.by_asset_class],
        }


def _rank(
    buckets: dict[str, float],
    labels: dict[str, str],
    contributors: dict[str, list[tuple[str, str, float]]],
    total: float,
    limit: int | None,
) -> list[Exposure]:
    ordered = sorted(buckets.items(), key=lambda kv: kv[1], reverse=True)
    if limit:
        ordered = ordered[:limit]
    out = []
    for key, value in ordered:
        parts = sorted(contributors.get(key, []), key=lambda c: c[2], reverse=True)[:6]
        out.append(Exposure(key, labels.get(key, key), value, value / total if total else 0.0, parts))
    return out


def look_through(portfolio: Portfolio, *, top_companies: int = 25) -> XRay:
    """Explode every fund into its constituents and total the exposure.

    A fund whose published weights do not sum to 1 (they never do -- factsheets
    list the top 10) has its remainder assigned to an explicit "rest of fund"
    bucket for its own sector, rather than being scaled up to 100%. Scaling
    would overstate the visible names by exactly the amount we cannot see.
    """
    companies: dict[str, float] = {}
    sectors: dict[str, float] = {}
    geographies: dict[str, float] = {}
    classes: dict[str, float] = {}
    labels: dict[str, str] = {}
    company_sources: dict[str, list[tuple[str, str, float]]] = {}
    sector_sources: dict[str, list[tuple[str, str, float]]] = {}
    geo_sources: dict[str, list[tuple[str, str, float]]] = {}
    class_sources: dict[str, list[tuple[str, str, float]]] = {}

    total = 0.0
    unresolved = 0.0

    for holding in portfolio.holdings:
        asset = portfolio.asset(holding.asset_id)
        value = as_float(holding.market_value)
        if value <= 0:
            continue
        total += value

        for asset_class, share in asset.class_split().items():
            key = asset_class.value
            classes[key] = classes.get(key, 0.0) + value * share
            labels[key] = asset_class.value.replace("_", " ").title()
            class_sources.setdefault(key, []).append((asset.id, asset.name, value * share))

        geo = asset.geography or "unknown"
        geographies[geo] = geographies.get(geo, 0.0) + value
        labels[geo] = geo
        geo_sources.setdefault(geo, []).append((asset.id, asset.name, value))

        if asset.is_fund and asset.holdings_lookthrough:
            resolved = 0.0
            for ticker, weight in asset.holdings_lookthrough.items():
                slice_value = value * weight
                resolved += slice_value
                key = ticker.upper()
                companies[key] = companies.get(key, 0.0) + slice_value
                labels.setdefault(key, ticker)
                company_sources.setdefault(key, []).append((asset.id, asset.name, slice_value))
                sector = _sector_of(portfolio, ticker) or asset.sector or "diversified"
                sectors[sector] = sectors.get(sector, 0.0) + slice_value
                labels.setdefault(sector, sector.title())
                sector_sources.setdefault(sector, []).append((asset.id, asset.name, slice_value))
            remainder = max(0.0, value - resolved)
            if remainder > 0:
                sector = asset.sector or "diversified"
                sectors[sector] = sectors.get(sector, 0.0) + remainder
                labels.setdefault(sector, sector.title())
                sector_sources.setdefault(sector, []).append(
                    (asset.id, f"{asset.name} (undisclosed remainder)", remainder)
                )
                unresolved += remainder
        elif asset.is_fund:
            sector = asset.sector or "diversified"
            sectors[sector] = sectors.get(sector, 0.0) + value
            labels.setdefault(sector, sector.title())
            sector_sources.setdefault(sector, []).append((asset.id, asset.name, value))
            unresolved += value
        else:
            if asset.asset_type not in _NON_CORPORATE:
                key = (asset.ticker or asset.id).upper()
                companies[key] = companies.get(key, 0.0) + value
                labels.setdefault(key, asset.name)
                company_sources.setdefault(key, []).append((asset.id, asset.name, value))
            sector = asset.sector or _class_sector(asset)
            sectors[sector] = sectors.get(sector, 0.0) + value
            labels.setdefault(sector, sector.title())
            sector_sources.setdefault(sector, []).append((asset.id, asset.name, value))

    if portfolio.cash:
        cash = as_float(portfolio.cash)
        total += cash
        classes["cash"] = classes.get("cash", 0.0) + cash
        labels["cash"] = "Cash"
        sectors["cash"] = sectors.get("cash", 0.0) + cash
        labels.setdefault("cash", "Cash")

    return XRay(
        total=total,
        by_company=_rank(companies, labels, company_sources, total, top_companies),
        by_sector=_rank(sectors, labels, sector_sources, total, None),
        by_geography=_rank(geographies, labels, geo_sources, total, None),
        by_asset_class=_rank(classes, labels, class_sources, total, None),
        unresolved_value=unresolved,
    )


def _sector_of(portfolio: Portfolio, ticker: str) -> str:
    for asset in portfolio.assets.values():
        if asset.ticker and asset.ticker.upper() == ticker.upper() and asset.sector:
            return asset.sector
    return ""


def _class_sector(asset: Asset) -> str:
    return {
        AssetClass.DEBT: "fixed income",
        AssetClass.GOLD: "gold",
        AssetClass.REAL_ESTATE: "real estate",
        AssetClass.CASH: "cash",
        AssetClass.CRYPTO: "crypto",
    }.get(asset.asset_class, "diversified")


@dataclass
class Overlap:
    left_id: str
    right_id: str
    left_name: str
    right_name: str
    #: Shared weight as a fraction of what both funds actually disclose.
    overlap: float
    #: The same figure against total fund value. Lower, and the honest number
    #: to quote when only the top ten holdings are published.
    absolute_overlap: float = 0.0
    disclosed: float = 0.0
    shared: list[tuple[str, float]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_id": self.left_id, "right_id": self.right_id,
            "left_name": self.left_name, "right_name": self.right_name,
            "overlap": round(self.overlap, 6),
            "absolute_overlap": round(self.absolute_overlap, 6),
            "disclosed": round(self.disclosed, 6),
            "shared": [{"ticker": t, "min_weight": round(w, 6)} for t, w in self.shared[:10]],
        }


def fund_overlap(left: Asset, right: Asset) -> Overlap:
    """Portfolio overlap between two funds.

    The raw sum of shared minimum weights understates overlap badly, because
    factsheets publish only the top ten holdings -- two identical funds would
    score 0.5, not 1.0, purely because half of each is undisclosed. So the
    headline figure divides by the smaller fund's disclosed weight, which
    answers the question the user is actually asking: of what I can see, how
    much of this is the same thing? The undivided figure is kept alongside it
    so nothing is overstated silently.
    """
    shared: list[tuple[str, float]] = []
    absolute = 0.0
    for ticker, weight in left.holdings_lookthrough.items():
        other = right.holdings_lookthrough.get(ticker)
        if other:
            smaller = min(weight, other)
            absolute += smaller
            shared.append((ticker, smaller))
    shared.sort(key=lambda item: item[1], reverse=True)
    disclosed = min(
        sum(left.holdings_lookthrough.values()), sum(right.holdings_lookthrough.values())
    )
    normalised = (absolute / disclosed) if disclosed > 0 else 0.0
    return Overlap(
        left.id, right.id, left.name, right.name,
        min(1.0, normalised), absolute, disclosed, shared,
    )


def overlapping_pairs(
    portfolio: Portfolio, *, threshold: float = 0.35
) -> list[Overlap]:
    """Every fund pair above a meaningful overlap, worst first."""
    funds = [
        portfolio.asset(h.asset_id) for h in portfolio.holdings
    ]
    unique = {a.id: a for a in funds if a.is_fund and a.holdings_lookthrough}
    out: list[Overlap] = []
    ordered = sorted(unique.values(), key=lambda a: a.id)
    for index, left in enumerate(ordered):
        for right in ordered[index + 1:]:
            overlap = fund_overlap(left, right)
            if overlap.overlap >= threshold:
                out.append(overlap)
    return sorted(out, key=lambda o: o.overlap, reverse=True)


@dataclass
class SingleName:
    """One company's total exposure, however it reaches the portfolio."""

    key: str
    label: str
    weight: float
    value: float
    through: list[tuple[str, str, float]] = field(default_factory=list)

    @property
    def direct_only(self) -> bool:
        return len(self.through) == 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "label": self.label, "weight": round(self.weight, 6),
            "value": round(self.value, 2), "direct_only": self.direct_only,
            "through": [{"asset_id": a, "label": l, "value": round(v, 2)}
                        for a, l, v in self.through],
        }


def single_name_breaches(xray: XRay, *, limit: float = 0.10) -> list[SingleName]:
    """Companies above the policy's single-name limit, measured look-through.

    This is the concentration that matters, and it is not the same as "one
    fund is a big share of the portfolio". A diversified equity fund at 20% of
    a portfolio is diversification working, not concentration risk; a bank at
    12% reached through three funds and a direct holding is concentration risk
    that no holdings screen would show. Applying a 10% limit to fund positions
    instead would make a sensible five-fund portfolio look like a breach and
    push users towards owning more funds that hold the same things.
    """
    return [
        SingleName(e.key, e.label, e.weight, e.value, list(e.contributors))
        for e in xray.by_company
        if e.weight > limit
    ]
