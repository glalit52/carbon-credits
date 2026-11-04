"""The forward-delivery forecast as a request/response, for the web app.

`forecast.run` and friends take dataclasses; the web app has numbers from its
database. This module turns one into the other, refuses inputs that would make
the simulation meaningless, and returns everything the forecast page shows:
the per-year distribution, the safe volume, which risk costs the most, how the
safe volume grows with portfolio size, and -- if a sale is being considered --
whether that sale is signable.

Stateless, like the estimate: the Vercel deployment serves it.
"""

from __future__ import annotations

from dataclasses import fields

from .forecast import (
    DEFAULT_CONFIDENCE, RiskModel, VintageProjection, aggregation_curve,
    assess_offtake, run,
)

TRACKS = {"rice", "agroforestry", "cropland"}
RATE_FIELDS = ("dropout_per_year", "practice_lapse_per_year",
               "planting_failure_per_year", "verification_slip_per_year")
MAX_YEARS = 30
MAX_TRIALS = 4000


class ForecastError(ValueError):
    """The request cannot be forecast; the message says what to fix."""


def _number(value, name: str, lo: float, hi: float) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError) as exc:
        raise ForecastError(f"{name} must be a number") from exc
    if not lo <= x <= hi:
        raise ForecastError(f"{name} must be between {lo} and {hi}")
    return x


def forecast_request(body: dict) -> dict:
    """Run the forecast for one project. See the module docstring."""
    track = str(body.get("track", "")).lower()
    if track not in TRACKS:
        raise ForecastError(f"track must be one of {sorted(TRACKS)}")

    raw = body.get("projections") or []
    if not raw:
        raise ForecastError("give at least one year to forecast")
    if len(raw) > MAX_YEARS:
        raise ForecastError(f"forecast at most {MAX_YEARS} years")
    projections = []
    seen = set()
    for i, p in enumerate(raw):
        try:
            year = int(p["year"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ForecastError(f"projection {i + 1} needs a year") from exc
        if year in seen:
            raise ForecastError(f"year {year} appears twice")
        seen.add(year)
        projections.append(VintageProjection(
            year=year,
            net_t=_number(p.get("net_t"), f"net_t for {year}", 0, 1e9),
            relative_uncertainty=_number(p.get("relative_uncertainty", 0), f"uncertainty for {year}", 0, 5),
            track=track,
            settled=bool(p.get("settled", False)),
        ))

    overrides = body.get("risk") or {}
    risk_kwargs = {k: _number(overrides[k], k, 0, 0.95) for k in RATE_FIELDS if k in overrides}
    units = int(_number(body.get("enrolled_units", 1), "enrolled_units", 1, 1_000_000))
    risk_kwargs["enrolled_units"] = units
    if risk_kwargs.keys() - {"enrolled_units"}:
        risk_kwargs["source"] = "rates supplied by the project, not the engine's placeholders"
    known = {f.name for f in fields(RiskModel)}
    risk = RiskModel(**{k: v for k, v in risk_kwargs.items() if k in known})

    confidence = _number(body.get("confidence", DEFAULT_CONFIDENCE), "confidence", 0.5, 0.99)
    trials = int(_number(body.get("trials", MAX_TRIALS), "trials", 200, MAX_TRIALS))
    seed = int(_number(body.get("seed", 20260927), "seed", 0, 2**31))

    forecast = run(projections, project_id=str(body.get("project_id") or "project"),
                   risk=risk, trials=trials, confidence=confidence, seed=seed)
    out = {
        "forecast": forecast.to_dict(),
        "risk": {k: getattr(risk, k) for k in (*RATE_FIELDS, "enrolled_units", "source")},
        "aggregation": aggregation_curve(
            projections, risk=risk, confidence=confidence, seed=seed,
            trials=min(trials, 1500),
            units=tuple(sorted({1, 5, 25, 100, 500, 2000, units}))),
        "offtake": None,
    }
    offtake = body.get("offtake")
    if offtake:
        out["offtake"] = assess_offtake(
            forecast, projections,
            committed_t=_number(offtake.get("committed_t"), "committed_t", 0, 1e9),
            replacement_price=_number(offtake.get("replacement_price", 0), "replacement_price", 0, 1e6),
            risk=risk, seed=seed,
        ).to_dict()
    return out
