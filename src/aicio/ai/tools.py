"""The tool surface the model reasons through.

Every tool reads from an already-computed :class:`~aicio.analysis.PortfolioAnalysis`.
None of them computes anything, calls a provider, or touches the network, and
none of them can place a trade -- recommending and executing are separate
systems, and the model lives entirely on the recommending side.

Tool results carry the fact ids they came from, which is what lets a reply be
traced back through the model to the engine output that justified it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from ..analysis import PortfolioAnalysis
from ..decisions.engine import RecommendationSet
from ..engine.goals import scenario_compare
from ..money import as_float

ToolFn = Callable[..., dict[str, Any]]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: ToolFn

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name, "description": self.description, "parameters": self.parameters,
        }


@dataclass
class ToolResult:
    name: str
    payload: dict[str, Any]
    fact_ids: tuple[str, ...] = ()

    def render(self) -> str:
        return json.dumps(self.payload, default=str, indent=None)


def _schema(properties: dict[str, Any], required: Sequence[str] = ()) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


class Toolbox:
    """The tools bound to one user's analysis."""

    def __init__(
        self,
        analysis: PortfolioAnalysis,
        recommendations: RecommendationSet | None = None,
    ) -> None:
        self.analysis = analysis
        self.recommendations = recommendations
        self._tools: dict[str, Tool] = {}
        self._register()

    # -- registration ------------------------------------------------------

    def _add(self, name: str, description: str, parameters: dict[str, Any], fn: ToolFn) -> None:
        self._tools[name] = Tool(name, description, parameters, fn)

    def _register(self) -> None:
        self._add(
            "get_portfolio_summary",
            "Net worth, invested value, cash, gains, XIRR and health score. Call this "
            "before any question about the portfolio as a whole.",
            _schema({}), self._summary,
        )
        self._add(
            "get_allocation",
            "Asset allocation against the user's policy bands, including drift and "
            "what it would take to correct it.",
            _schema({}), self._allocation,
        )
        self._add(
            "get_holdings",
            "The user's positions, largest first, with weight, gain and tax status.",
            _schema({
                "limit": {"type": "integer", "description": "How many to return (default 10)"},
                "asset_class": {"type": "string",
                                "description": "Optional filter: equity, debt, gold, cash"},
            }),
            self._holdings,
        )
        self._add(
            "get_holding_detail",
            "Everything known about one holding: cost basis, gain, tax lots, quality, "
            "lock-in and look-through sector.",
            _schema({"asset_id_or_name": {"type": "string"}}, ["asset_id_or_name"]),
            self._holding_detail,
        )
        self._add(
            "get_xray",
            "Look-through exposure: which companies and sectors the user actually owns "
            "once funds are opened up, and which funds overlap.",
            _schema({}), self._xray,
        )
        self._add(
            "get_goals",
            "Goal projections: probability, target, median outcome and required "
            "contribution for each goal.",
            _schema({}), self._goals,
        )
        self._add(
            "run_goal_scenario",
            "Compare goal outcomes under different contributions and target dates. Use "
            "this for any 'what if' about a goal rather than estimating.",
            _schema({
                "goal_id": {"type": "string"},
                "extra_monthly": {"type": "number",
                                  "description": "Additional monthly contribution in rupees"},
                "year_delta": {"type": "integer",
                               "description": "Years to move the target date by, + or -"},
            }, ["goal_id"]),
            self._goal_scenario,
        )
        self._add(
            "get_risk",
            "Scenario results: what the portfolio is worth after standard market shocks, "
            "and how many months of expenses remain liquid afterwards.",
            _schema({}), self._risk,
        )
        self._add(
            "get_tax_position",
            "Realised and unrealised gains, estimated tax, remaining exemption and lots "
            "approaching long-term treatment.",
            _schema({}), self._tax,
        )
        self._add(
            "get_recommendations",
            "The current recommendations with their reasons, evidence, risks and "
            "counterarguments, including any that were suppressed and why.",
            _schema({}), self._recommendations,
        )
        self._add(
            "get_policy",
            "The user's Investment Policy Statement: targets, bands and constraints.",
            _schema({}), self._policy,
        )
        self._add(
            "get_sip_plan",
            "Current contributions and the proposed redirection, with the months needed "
            "to correct allocation without selling.",
            _schema({}), self._sip,
        )

    # -- exposure ----------------------------------------------------------

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(name, {"error": f"unknown tool {name!r}",
                                     "available": self.names()})
        try:
            payload = tool.fn(**(arguments or {}))
        except TypeError as exc:
            return ToolResult(name, {"error": f"bad arguments for {name}: {exc}"})
        except Exception as exc:                      # noqa: BLE001 - surfaced, not raised
            return ToolResult(name, {"error": f"{name} failed: {exc}"})
        return ToolResult(name, payload, tuple(payload.pop("_fact_ids", ())))

    # -- implementations ---------------------------------------------------

    def _facts(self, *names: str) -> list[str]:
        out = []
        for name in names:
            fact = self.analysis.facts.get(name)
            if fact is not None:
                out.append(fact.id)
        return out

    def _summary(self) -> dict[str, Any]:
        a = self.analysis
        return {
            "as_of": a.as_of.isoformat(),
            "currency": "INR",
            "net_worth": round(a.net_worth, 2),
            "market_value": round(as_float(a.portfolio.market_value), 2),
            "invested": round(as_float(a.portfolio.invested), 2),
            "cash": round(as_float(a.portfolio.cash), 2),
            "liabilities": round(as_float(a.portfolio.external_liabilities), 2),
            "unrealised_gain": round(as_float(a.portfolio.unrealised_gain), 2),
            "xirr": None if a.portfolio_xirr is None else round(a.portfolio_xirr, 4),
            "health_score": a.health.score,
            "health_band": a.health.band,
            "weakest_dimension": a.health.weakest.label if a.health.weakest else None,
            "liquid_months": None if a.liquid_months is None else round(a.liquid_months, 1),
            "holdings_count": len(a.portfolio.holdings),
            "unassessed_dimensions": a.health.unassessed,
            "_fact_ids": self._facts("net_worth", "market_value", "cash", "health_score",
                                     "portfolio_xirr", "liquid_months"),
        }

    def _allocation(self) -> dict[str, Any]:
        a = self.analysis
        return {
            "weights": {k.value: round(v, 4) for k, v in a.breakdown.weights.items()},
            "drift": a.drift.to_dict()["drifts"],
            "total_absolute_drift": round(a.drift.total_absolute_drift, 4),
            "rebalance_moves": a.rebalance,
            "_fact_ids": self._facts(*[f"allocation.{k.value}" for k in a.breakdown.weights]),
        }

    def _holdings(self, limit: int = 10, asset_class: str = "") -> dict[str, Any]:
        views = self.analysis.holdings
        if asset_class:
            views = [v for v in views if v.asset_class.value == asset_class.lower()]
        rows = [v.to_dict() for v in views[:max(1, limit)]]
        return {
            "holdings": rows,
            "total_holdings": len(self.analysis.holdings),
            "_fact_ids": self._facts("market_value"),
        }

    def _holding_detail(self, asset_id_or_name: str) -> dict[str, Any]:
        needle = asset_id_or_name.lower().strip()
        for view in self.analysis.holdings:
            if needle in view.holding.asset_id.lower() or needle in view.label.lower():
                asset = self.analysis.portfolio.asset(view.holding.asset_id)
                return {
                    **view.to_dict(),
                    "isin": asset.isin,
                    "category": asset.category,
                    "benchmark": asset.benchmark,
                    "expense_ratio": asset.expense_ratio,
                    "lock_in": asset.lock_in,
                    "tax_lots": [p.to_dict() for p in view.unrealised],
                    "provenance": view.holding.provenance.to_dict(),
                    "_fact_ids": self._facts(f"position_weight.{view.holding.asset_id}"),
                }
        return {
            "error": f"no holding matching {asset_id_or_name!r}",
            "available": [v.label for v in self.analysis.holdings],
        }

    def _xray(self) -> dict[str, Any]:
        x = self.analysis.xray
        return {
            "coverage": round(x.coverage, 4),
            "top_companies": [e.to_dict() for e in x.by_company[:10]],
            "sectors": [e.to_dict() for e in x.by_sector[:8]],
            "geographies": [e.to_dict() for e in x.by_geography],
            "fund_overlaps": [o.to_dict() for o in self.analysis.overlaps[:5]],
            "_fact_ids": self._facts("lookthrough.top_company"),
        }

    def _goals(self) -> dict[str, Any]:
        return {
            "goals": [p.to_dict() for p in self.analysis.projections],
            "_fact_ids": self._facts(
                *[f"goal.{p.goal_id}.probability" for p in self.analysis.projections]
            ),
        }

    def _goal_scenario(
        self, goal_id: str, extra_monthly: float = 0.0, year_delta: int = 0
    ) -> dict[str, Any]:
        goal = next(
            (g for g in _goals_of(self.analysis) if g.id == goal_id or goal_id in g.name.lower()),
            None,
        )
        if goal is None:
            return {"error": f"no goal {goal_id!r}",
                    "available": [p.goal_id for p in self.analysis.projections]}
        projection = next(
            (p for p in self.analysis.projections if p.goal_id == goal.id), None
        )
        if projection is None:
            return {"error": "no projection for that goal"}
        rows = scenario_compare(
            goal,
            current_value=projection.current_value,
            monthly_contribution=projection.monthly_contribution,
            weights=self.analysis.breakdown.weights,
            today=self.analysis.as_of,
            contribution_deltas=(0.0, float(extra_monthly)) if extra_monthly else (0.0, 5000.0, 15000.0),
            year_deltas=(0, int(year_delta)) if year_delta else (0, 2, -2),
            trials=1200,
        )
        return {
            "goal_id": goal.id, "goal_name": goal.name,
            "current_probability": round(projection.probability, 4),
            "scenarios": rows,
            "assumptions": projection.assumptions,
        }

    def _risk(self) -> dict[str, Any]:
        return {
            "scenarios": [s.to_dict() for s in self.analysis.scenarios],
            "concentration": self.analysis.concentration.to_dict(),
            "risk_capacity": self.analysis.profile.risk_capacity,
            "risk_tolerance": self.analysis.profile.risk_tolerance,
            "_fact_ids": self._facts(*[f"scenario.{s.name}" for s in self.analysis.scenarios]),
        }

    def _tax(self) -> dict[str, Any]:
        return {
            **self.analysis.tax.to_dict(),
            "marginal_rate": self.analysis.profile.marginal_tax_rate,
            "_fact_ids": self._facts("tax.estimated", "tax.ltcg_exemption_left"),
        }

    def _recommendations(self) -> dict[str, Any]:
        if self.recommendations is None:
            return {"recommendations": [], "note": "no recommendation run attached"}
        return {
            "recommendations": [r.to_dict() for r in self.recommendations.recommendations],
            "suppressed": [
                {"headline": r.headline, "reason": r.suppressed_reason}
                for r in self.recommendations.suppressed
            ],
            "do_nothing": self.recommendations.do_nothing,
        }

    def _policy(self) -> dict[str, Any]:
        return self.analysis.policy.to_dict()

    def _sip(self) -> dict[str, Any]:
        return self.analysis.sip_plan.to_dict()


def _goals_of(analysis: PortfolioAnalysis):
    """Goals are not stored on the analysis, only their projections. Rebuild
    the minimum a scenario needs from the projection itself."""
    from ..domain import Goal, GoalType
    from ..money import money
    from datetime import timedelta

    out = []
    for projection in analysis.projections:
        out.append(Goal(
            id=projection.goal_id,
            user_id=analysis.user_id,
            name=projection.goal_name,
            goal_type=GoalType.OTHER,
            target_amount=money(
                projection.target_nominal
                / ((1 + projection.assumptions.get("inflation", 0.06)) ** projection.years)
            ),
            target_date=analysis.as_of + timedelta(days=int(projection.years * 365.25)),
            current_funding=money(projection.current_value),
            monthly_contribution=money(projection.monthly_contribution),
            inflation_rate=projection.assumptions.get("inflation", 0.06),
        ))
    return out
