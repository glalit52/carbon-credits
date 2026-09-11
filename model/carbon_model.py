#!/usr/bin/env python3
"""
Bottom-up cashflow model for a two-track carbon project portfolio.

Track A ("bridge")  - cropland agriculture. Fast credit cycle, funds years 1-4.
Track B ("estate")  - reforestation / agroforestry under VM0047. Slow, durable.

The question this model exists to answer is not "is the project profitable".
It is "how much working capital do we have to raise before the portfolio turns
cash positive, and in which year". That number sets the financing strategy.

Every default below is sourced in docs/research/, and every one of them is
wrong for your specific landscape. Override them in a Scenario and re-run.

    python3 model/carbon_model.py                 # default scenario
    python3 model/carbon_model.py --csv out.csv   # also write the annual table
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass, field, replace


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

@dataclass
class Track:
    """One crediting pathway inside the portfolio."""

    name: str

    # Enrolment. Hectares brought under contract in each project year.
    # Index 0 is year 1. The last value repeats for remaining years.
    enrolment_ha: list[float]
    ha_per_farmer: float

    # Crediting.
    first_issuance_year: int          # project year of the first credit issuance
    peak_t_per_ha_yr: float           # steady-state gross sequestration/avoidance
    ramp_midpoint_yr: float           # years after planting to reach half of peak
    ramp_steepness: float             # logistic k; higher = faster to peak
    buffer_pct: float                 # non-permanence buffer pool withholding
    uncertainty_pct: float            # methodology uncertainty deduction

    # Money.
    price_per_credit: float
    farmer_share_pct: float           # share of gross credit revenue to farmers

    # Cost.
    setup_cost_per_farmer: float      # enrolment, training, inputs; one-off
    mrv_cost_per_ha_yr: float         # recurring dMRV + field verification
    fixed_cost_per_yr: float          # project management attributable to track
    validation_cost: float            # one-off, paid the year before issuance
    verification_cost_per_yr: float   # paid from first issuance year onward

    def ha_enrolled_in(self, year: int) -> float:
        """Hectares newly enrolled in this project year (1-indexed)."""
        if year < 1:
            return 0.0
        i = min(year - 1, len(self.enrolment_ha) - 1)
        return self.enrolment_ha[i]

    def cumulative_ha(self, year: int) -> float:
        return sum(self.ha_enrolled_in(y) for y in range(1, year + 1))

    def yield_at_age(self, age_yrs: float) -> float:
        """Gross tCO2e/ha in a year, for a cohort of the given age.

        Logistic ramp: ~0 while trees establish, rising to peak. For cropland
        tracks set ramp_midpoint_yr near 0 so the curve is effectively flat.
        """
        if age_yrs <= 0:
            return 0.0
        k = self.ramp_steepness
        x = k * (age_yrs - self.ramp_midpoint_yr)
        # guard against overflow on extreme parameters
        x = max(-60.0, min(60.0, x))
        return self.peak_t_per_ha_yr / (1.0 + math.exp(-x))

    def gross_credits_in(self, year: int) -> float:
        """Sum over cohorts of (cohort ha x yield at that cohort's age)."""
        if year < self.first_issuance_year:
            return 0.0
        total = 0.0
        for planted in range(1, year + 1):
            ha = self.ha_enrolled_in(planted)
            if ha:
                total += ha * self.yield_at_age(year - planted + 1)
        return total

    def issued_credits_in(self, year: int) -> float:
        """Credits that are actually sellable, after deductions."""
        gross = self.gross_credits_in(year)
        return gross * (1 - self.buffer_pct) * (1 - self.uncertainty_pct)


@dataclass
class Scenario:
    name: str
    horizon_yrs: int
    tracks: list[Track]
    # Portfolio-level overheads not attributable to a single track.
    corporate_cost_yr1: float
    corporate_cost_growth: float      # annual multiplier
    registry_fee_per_credit: float


# ---------------------------------------------------------------------------
# Defaults
#
# Sources, all in docs/research/01-mitti-labs-and-varaha.md unless noted:
#   - Grow Indigo Aadi (VCS 2590), Jan 2026: first VM0042 issuance in India,
#     ~30,000 acres -> 50,000+ credits, i.e. ~4.1 credits/ha in that issuance.
#     Modelled conservatively at 1.5 t/ha/yr steady state.
#   - Gold Standard rice AWD: baseline 20-100 kg CH4/ha/season, 20-50% cut.
#     At 28x GWP and two seasons this spans ~0.3-2.8 tCO2e/ha/yr.
#   - Indian agroforestry: tree component 0.25-76 Mg C/ha/yr across systems;
#     a planted system at 2 Mg C/ha/yr is ~7.3 tCO2e/ha/yr. Peak set to 8.
#   - VM0047 buffer pool: 10-25% by project risk. 20% assumed.
#   - Smallholder programme cost: ~$150/farmer setup, $150-200/farmer MRV.
#     MRV restated per hectare here, since dMRV scales with area not headcount.
#   - Prices: ARR ~$22/t average, BBB+ ~EUR 28.55; cropland credits $5-15/t.
#   - Aggregator share of credit revenue 30-60%, i.e. farmer share 40-70%.
# ---------------------------------------------------------------------------

BRIDGE = Track(
    name="Track A - cropland (VM0042 / rice AWD)",
    enrolment_ha=[4_000, 8_000, 8_000, 5_000, 0],
    ha_per_farmer=1.5,
    first_issuance_year=2,
    peak_t_per_ha_yr=1.5,
    ramp_midpoint_yr=0.0,        # effectively flat from the first season
    ramp_steepness=3.0,
    buffer_pct=0.15,
    uncertainty_pct=0.10,
    price_per_credit=12.0,
    farmer_share_pct=0.55,
    setup_cost_per_farmer=150.0,
    mrv_cost_per_ha_yr=18.0,
    fixed_cost_per_yr=120_000.0,
    validation_cost=90_000.0,
    verification_cost_per_yr=70_000.0,
)

ESTATE = Track(
    name="Track B - agroforestry / ARR (VM0047)",
    enrolment_ha=[500, 1_500, 1_500, 1_500, 0],
    ha_per_farmer=1.0,
    first_issuance_year=4,
    peak_t_per_ha_yr=8.0,
    ramp_midpoint_yr=6.0,
    ramp_steepness=0.6,
    buffer_pct=0.20,
    uncertainty_pct=0.10,
    price_per_credit=26.0,       # priced as a CCP-labelled, well-rated credit
    farmer_share_pct=0.60,
    setup_cost_per_farmer=320.0,  # includes seedlings and establishment
    mrv_cost_per_ha_yr=26.0,
    fixed_cost_per_yr=150_000.0,
    validation_cost=140_000.0,
    verification_cost_per_yr=90_000.0,
)

BASE = Scenario(
    name="Base case - bridge carries the estate",
    horizon_yrs=12,
    tracks=[BRIDGE, ESTATE],
    corporate_cost_yr1=450_000.0,
    corporate_cost_growth=1.15,
    registry_fee_per_credit=0.06,   # ~INR 5/credit
)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

@dataclass
class YearRow:
    year: int
    credits: float = 0.0
    gross_revenue: float = 0.0
    farmer_payments: float = 0.0
    opex: float = 0.0
    net: float = 0.0
    cumulative: float = 0.0
    by_track: dict[str, float] = field(default_factory=dict)


def run(scn: Scenario) -> list[YearRow]:
    rows: list[YearRow] = []
    cumulative = 0.0

    for year in range(1, scn.horizon_yrs + 1):
        row = YearRow(year=year)

        for tr in scn.tracks:
            credits = tr.issued_credits_in(year)
            revenue = credits * tr.price_per_credit

            new_ha = tr.ha_enrolled_in(year)
            new_farmers = new_ha / tr.ha_per_farmer if tr.ha_per_farmer else 0.0
            live_ha = tr.cumulative_ha(year)

            cost = (
                new_farmers * tr.setup_cost_per_farmer
                + live_ha * tr.mrv_cost_per_ha_yr
                + tr.fixed_cost_per_yr
                + credits * scn.registry_fee_per_credit
            )
            if year == tr.first_issuance_year - 1:
                cost += tr.validation_cost
            if year >= tr.first_issuance_year:
                cost += tr.verification_cost_per_yr

            farmers_paid = revenue * tr.farmer_share_pct

            row.credits += credits
            row.gross_revenue += revenue
            row.farmer_payments += farmers_paid
            row.opex += cost
            row.by_track[tr.name] = credits

        row.opex += scn.corporate_cost_yr1 * (scn.corporate_cost_growth ** (year - 1))
        row.net = row.gross_revenue - row.farmer_payments - row.opex
        cumulative += row.net
        row.cumulative = cumulative
        rows.append(row)

    return rows


def summarise(scn: Scenario, rows: list[YearRow]) -> dict[str, float | int | None]:
    trough = min(r.cumulative for r in rows)
    trough_year = next(r.year for r in rows if r.cumulative == trough)
    breakeven_yr = next((r.year for r in rows if r.net > 0), None)
    cash_positive_yr = next((r.year for r in rows if r.cumulative > 0), None)
    return {
        "peak_funding_need": -trough if trough < 0 else 0.0,
        "trough_year": trough_year,
        "first_profitable_year": breakeven_yr,
        "cumulative_positive_year": cash_positive_yr,
        "total_credits": sum(r.credits for r in rows),
        "final_cumulative": rows[-1].cumulative,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def money(x: float) -> str:
    sign = "-" if x < 0 else " "
    a = abs(x)
    if a >= 1_000_000:
        return f"{sign}{a/1_000_000:>6.2f}M"
    return f"{sign}{a/1_000:>6.0f}k"


def report(scn: Scenario, rows: list[YearRow]) -> None:
    print()
    print(scn.name)
    print("=" * 78)
    print(f"{'Yr':>3} {'Credits':>9} {'Revenue':>9} {'Farmers':>9} "
          f"{'Opex':>9} {'Net':>9} {'Cumulative':>11}")
    print("-" * 78)
    for r in rows:
        print(f"{r.year:>3} {r.credits:>9,.0f} {money(r.gross_revenue):>9} "
              f"{money(-r.farmer_payments):>9} {money(-r.opex):>9} "
              f"{money(r.net):>9} {money(r.cumulative):>11}")
    print("-" * 78)

    s = summarise(scn, rows)
    print()
    print("The number that decides the financing strategy")
    print("-" * 78)
    print(f"  Peak funding need          {money(s['peak_funding_need'])}"
          f"   (deepest in year {s['trough_year']})")
    print(f"  First profitable year      "
          f"{s['first_profitable_year'] or 'not within horizon'}")
    print(f"  Cumulative turns positive  "
          f"{s['cumulative_positive_year'] or 'not within horizon'}")
    print(f"  Credits over {scn.horizon_yrs} years      {s['total_credits']:,.0f}")
    print()
    print("  Read the peak funding need as the minimum raise - equity, grant, or")
    print("  a Mirova-style credit prepay - required before the portfolio is")
    print("  self-funding. If that number is uncomfortable, the lever with the")
    print("  most leverage is Track A enrolment, not Track B price.")
    print()


def sensitivity(scn: Scenario) -> None:
    """Which assumption actually moves the peak funding need?"""
    base = summarise(scn, run(scn))["peak_funding_need"]
    print("Sensitivity of peak funding need (-20% / +20% on each assumption)")
    print("-" * 78)

    def variant(label: str, mutate) -> None:
        lo = summarise(s_lo := mutate(0.8), run(s_lo))["peak_funding_need"]
        hi = summarise(s_hi := mutate(1.2), run(s_hi))["peak_funding_need"]
        print(f"  {label:<34} {money(lo):>9}  <- {money(base)} ->  {money(hi):>9}")

    def scale_track(idx: int, attr: str):
        def f(mult: float) -> Scenario:
            tracks = list(scn.tracks)
            tracks[idx] = replace(tracks[idx], **{attr: getattr(tracks[idx], attr) * mult})
            return replace(scn, tracks=tracks)
        return f

    def scale_enrolment(idx: int):
        def f(mult: float) -> Scenario:
            tracks = list(scn.tracks)
            t = tracks[idx]
            tracks[idx] = replace(t, enrolment_ha=[h * mult for h in t.enrolment_ha])
            return replace(scn, tracks=tracks)
        return f

    variant("Track A hectares enrolled", scale_enrolment(0))
    variant("Track A credit price", scale_track(0, "price_per_credit"))
    variant("Track A yield t/ha/yr", scale_track(0, "peak_t_per_ha_yr"))
    variant("Track B hectares enrolled", scale_enrolment(1))
    variant("Track B credit price", scale_track(1, "price_per_credit"))
    variant("Track B peak yield t/ha/yr", scale_track(1, "peak_t_per_ha_yr"))
    variant("MRV cost per ha (both tracks)",
            lambda m: replace(scn, tracks=[
                replace(t, mrv_cost_per_ha_yr=t.mrv_cost_per_ha_yr * m) for t in scn.tracks]))
    variant("Farmer share of revenue",
            lambda m: replace(scn, tracks=[
                replace(t, farmer_share_pct=min(0.95, t.farmer_share_pct * m))
                for t in scn.tracks]))
    variant("Corporate overhead",
            lambda m: replace(scn, corporate_cost_yr1=scn.corporate_cost_yr1 * m))
    print()


def write_csv(rows: list[YearRow], path: str) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "credits", "gross_revenue", "farmer_payments",
                    "opex", "net", "cumulative"])
        for r in rows:
            w.writerow([r.year, round(r.credits), round(r.gross_revenue),
                        round(r.farmer_payments), round(r.opex),
                        round(r.net), round(r.cumulative)])


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", help="write the annual table to this path")
    ap.add_argument("--no-sensitivity", action="store_true")
    args = ap.parse_args(argv)

    rows = run(BASE)
    report(BASE, rows)
    if not args.no_sensitivity:
        sensitivity(BASE)
    if args.csv:
        write_csv(rows, args.csv)
        print(f"wrote {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
