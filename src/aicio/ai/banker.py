"""The AI banker: the conversation loop, and the rails around it.

The loop is small on purpose. Build a grounded context, let the model call
tools against the engine, and then refuse to show the answer if its numbers do
not reconcile with the facts. Everything interesting is in the rails.

The offline path is a first-class citizen: with no API key configured, the same
questions are answered from the same tools with plainer prose. That is what
makes the grounding claim testable -- the eval suite runs the offline path, so
"no fabricated numbers" is enforced by code rather than by prompt discipline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..analysis import PortfolioAnalysis
from ..decisions.engine import RecommendationSet
from ..domain import Conversation
from ..money import format_money, pct
from ..provenance import utcnow
from .gateway import LLMGateway, LLMResponse, OfflineGateway, build_gateway
from .prompts import SYSTEM_BANKER, TOOL_PREAMBLE, Prompt
from .safety import GroundingReport, collect_numbers, enforce, wrap_untrusted
from .tools import Toolbox, ToolResult

#: How many tool rounds before the loop gives up. Three is enough for
#: "summary -> detail -> scenario"; more usually means the model is circling.
MAX_TOOL_ROUNDS = 3


@dataclass
class BankerReply:
    """An answer, with everything needed to audit it later."""

    text: str
    fact_ids: tuple[str, ...] = ()
    tools_used: list[str] = field(default_factory=list)
    grounding: GroundingReport | None = None
    prompt_id: str = ""
    model: str = ""
    provider: str = ""
    created_at: datetime = field(default_factory=utcnow)
    blocked: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "fact_ids": list(self.fact_ids),
            "tools_used": list(self.tools_used),
            "grounding": self.grounding.to_dict() if self.grounding else None,
            "prompt_id": self.prompt_id,
            "model": self.model,
            "provider": self.provider,
            "created_at": self.created_at.isoformat(),
            "blocked": self.blocked,
            "notes": list(self.notes),
        }


class AIBanker:
    #: Numbers the offline path saw from its own tool calls this turn. Kept so
    #: the grounding gate applies to the offline answers exactly as it does to
    #: the model's.
    _offline_values: list[float]

    def __init__(
        self,
        analysis: PortfolioAnalysis,
        recommendations: RecommendationSet | None = None,
        *,
        gateway: LLMGateway | None = None,
        prompt: Prompt = SYSTEM_BANKER,
        grounding_tolerance: float = 0.02,
    ) -> None:
        self.analysis = analysis
        self.recommendations = recommendations
        self.toolbox = Toolbox(analysis, recommendations)
        self.gateway = gateway or build_gateway()
        self.prompt = prompt
        self.grounding_tolerance = grounding_tolerance
        self._offline_values = []

    def _tool(self, name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
        """Call a tool and remember every number it returned."""
        result = self.toolbox.call(name, arguments)
        self._offline_values.extend(collect_numbers(result.payload))
        return result

    # -- context -----------------------------------------------------------

    def system_prompt(self) -> str:
        return "\n\n".join([
            self.prompt.text,
            TOOL_PREAMBLE,
            self._facts_block(),
        ])

    def _facts_block(self) -> str:
        facts = self.analysis.facts
        lines = ["FACTS (computed by the deterministic engine; the complete set of what you know)"]
        for fact in facts.facts:
            stale = " [STALE]" if fact.is_stale() else ""
            lines.append(
                f"- {fact.name} = {_render_value(fact.value)} {fact.unit}{stale}"
                + (f"  ({fact.detail})" if fact.detail else "")
            )
        if facts.notes:
            lines.append("")
            lines.append("LIMITATIONS (say these out loud when they bear on the answer)")
            lines += [f"- {note}" for note in facts.notes]
        lines.append("")
        lines.append(
            f"Engine version {self.analysis.engine_version}; portfolio fingerprint "
            f"{self.analysis.fingerprint}; as of {self.analysis.as_of.isoformat()}."
        )
        return "\n".join(lines)

    # -- conversation ------------------------------------------------------

    def ask(
        self,
        question: str,
        *,
        conversation: Conversation | None = None,
        document: str | None = None,
        max_tokens: int = 1000,
    ) -> BankerReply:
        """Answer one question, grounded and gated."""
        if isinstance(self.gateway, OfflineGateway):
            return self._offline_answer(question)

        content: list[dict[str, Any]] = [{"type": "text", "text": question}]
        if document:
            # Untrusted content is fenced and scrubbed before it can reach the
            # model. A statement is data the user handed us, not a participant.
            content.append({"type": "text", "text": wrap_untrusted(document)})

        messages: list[dict[str, Any]] = []
        if conversation is not None:
            for message in conversation.transcript():
                messages.append({"role": message.role, "content": message.content})
        messages.append({"role": "user", "content": content})

        used: list[str] = []
        fact_ids: list[str] = []
        seen_values: list[float] = []
        response: LLMResponse | None = None

        for _round in range(MAX_TOOL_ROUNDS):
            response = self.gateway.complete(
                system=self.system_prompt(),
                messages=messages,
                tools=self.toolbox.schemas(),
                max_tokens=max_tokens,
            )
            if not response.wants_tools:
                break
            messages.append({"role": "assistant", "content": _assistant_blocks(response)})
            results = [self.toolbox.call(call.name, call.arguments) for call in response.tool_calls]
            for call, result in zip(response.tool_calls, results):
                used.append(call.name)
                fact_ids.extend(result.fact_ids)
                seen_values.extend(collect_numbers(result.payload))
            messages.append({
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": call.id, "content": result.render()}
                    for call, result in zip(response.tool_calls, results)
                ],
            })

        if response is None:
            return BankerReply(
                text="I could not reach the model. The engine's own figures are still "
                     "available on the portfolio and action screens.",
                blocked=True, prompt_id=self.prompt.id,
            )

        text, report = enforce(response.text, self.analysis.facts,
                               tolerance=self.grounding_tolerance,
                               extra_values=seen_values)
        reply = BankerReply(
            text=text,
            fact_ids=tuple(dict.fromkeys(fact_ids)) or tuple(self.analysis.facts.ids[:6]),
            tools_used=used,
            grounding=report,
            prompt_id=self.prompt.id,
            model=response.model,
            provider=response.provider,
            blocked=report.failed,
        )
        if conversation is not None:
            conversation.add("user", question)
            conversation.add("assistant", reply.text, fact_ids=reply.fact_ids)
        return reply

    # -- offline -----------------------------------------------------------

    def _offline_answer(self, question: str) -> BankerReply:
        self._offline_values = []
        responder = getattr(self.gateway, "responder", None)
        if responder is not None:
            # A supplied responder stands in for a model -- used by the eval
            # suite's adversarial cases -- and is gated exactly like one.
            text, tools, fact_ids = responder(question, []), ["responder"], []
        else:
            intent, arguments = classify(question)
            handler = getattr(self, f"_answer_{intent}", self._answer_summary)
            text, tools, fact_ids = handler(**arguments)
        # The offline path is held to exactly the same grounding standard as
        # the model path. If it ever drifts, the eval suite catches it.
        checked, report = enforce(text, self.analysis.facts, tolerance=self.grounding_tolerance,
                                  extra_values=self._offline_values)
        return BankerReply(
            text=checked, fact_ids=tuple(fact_ids), tools_used=tools, grounding=report,
            prompt_id=self.prompt.id, model=self.gateway.model, provider=self.gateway.name,
            blocked=report.failed,
            notes=["Answered without a language model: no API key is configured, so this "
                   "is the engine speaking directly."],
        )

    def _answer_summary(self, **_: Any) -> tuple[str, list[str], list[str]]:
        result = self._tool("get_portfolio_summary")
        data = result.payload
        lines = [
            f"Net worth is {format_money(data['net_worth'])}: "
            f"{format_money(data['market_value'])} invested, "
            f"{format_money(data['cash'])} in cash"
            + (f", less {format_money(data['liabilities'])} of liabilities."
               if data["liabilities"] else "."),
            f"Health score {data['health_score']:.0f} out of 100 ({data['health_band']})"
            + (f", weakest on {data['weakest_dimension'].lower()}."
               if data["weakest_dimension"] else "."),
        ]
        if data["xirr"] is not None:
            lines.append(
                f"Money-weighted return since you started is {pct(data['xirr'])} a year. "
                "That reflects your timing as well as the funds'."
            )
        if data["unassessed_dimensions"]:
            lines.append(
                "Not everything could be assessed: "
                + ", ".join(data["unassessed_dimensions"])
                + ". Those dimensions are excluded from the score rather than guessed at."
            )
        return " ".join(lines), ["get_portfolio_summary"], list(result.fact_ids)

    def _answer_allocation(self, **_: Any) -> tuple[str, list[str], list[str]]:
        result = self._tool("get_allocation")
        data = result.payload
        parts = [
            "Allocation is "
            + ", ".join(f"{k} {v:.0%}" for k, v in sorted(
                data["weights"].items(), key=lambda kv: -kv[1]))
            + "."
        ]
        breaches = [d for d in data["drift"] if not d["in_band"]]
        if breaches:
            worst = max(breaches, key=lambda d: abs(d["breach"]))
            parts.append(
                f"{worst['asset_class'].title()} is outside its band at "
                f"{worst['actual']:.1%} against a target of {worst['target']:.1%}."
            )
        else:
            parts.append("Every class is inside its policy band.")
        if self.analysis.sip_plan.months_to_close_gap:
            parts.append(
                f"Redirecting contributions would close the gap in about "
                f"{self.analysis.sip_plan.months_to_close_gap:.0f} months without selling."
            )
        return " ".join(parts), ["get_allocation"], list(result.fact_ids)

    def _answer_goals(self, **_: Any) -> tuple[str, list[str], list[str]]:
        result = self._tool("get_goals")
        rows = result.payload["goals"]
        if not rows:
            return ("You have not set any goals yet, so there is nothing to project.",
                    ["get_goals"], [])
        parts = []
        for row in rows:
            parts.append(
                f"{row['goal_name']}: {row['probability']:.0%} chance on the current plan "
                f"({row['status'].replace('_', ' ')}). Target "
                f"{format_money(row['target_nominal'])} in {row['years']:.1f} years; "
                f"median outcome {format_money(row['percentiles']['p50'])}."
            )
        parts.append(
            "These are simulations, not forecasts, and they assume "
            f"{rows[0]['expected_return']:.1%} a year with "
            f"{rows[0]['expected_volatility']:.1%} volatility. Disagree with the assumption "
            "and the answer changes."
        )
        return " ".join(parts), ["get_goals"], list(result.fact_ids)

    def _answer_risk(self, **_: Any) -> tuple[str, list[str], list[str]]:
        result = self._tool("get_risk")
        scenarios = result.payload["scenarios"]
        worst = min(scenarios, key=lambda s: s["loss_pct"])
        parts = [
            f"In the worst of the standard scenarios ({worst['name']}), the portfolio falls "
            f"{abs(worst['loss_pct']):.1%}, or {format_money(abs(worst['loss']))}.",
        ]
        if worst["liquidity_months_after"] is not None:
            parts.append(
                f"Afterwards you would still have {worst['liquidity_months_after']:.0f} months "
                "of expenses in liquid assets, so nothing would have to be sold at the bottom."
            )
        conc = result.payload["concentration"]
        parts.append(
            f"Concentration is the other side of it: effectively "
            f"{conc['effective_positions']:.1f} positions."
        )
        if result.payload["risk_tolerance"] > result.payload["risk_capacity"]:
            parts.append(
                f"Your stated tolerance is {result.payload['risk_tolerance']} out of 10 but "
                f"measured capacity is {result.payload['risk_capacity']}. The policy follows "
                "capacity, which is the lower of the two."
            )
        return " ".join(parts), ["get_risk"], list(result.fact_ids)

    def _answer_tax(self, **_: Any) -> tuple[str, list[str], list[str]]:
        result = self._tool("get_tax_position")
        data = result.payload
        parts = [
            f"Realised so far this year: {format_money(float(data['realised_short_term']))} "
            f"short term and {format_money(float(data['realised_long_term']))} long term, "
            f"for an estimated {format_money(float(data['estimated_tax']))} of tax.",
            f"{format_money(float(data['ltcg_exemption_left']))} of the annual long-term "
            "exemption is unused.",
        ]
        if data["near_long_term"]:
            nearest = data["near_long_term"][0]
            parts.append(
                f"One lot turns long-term in {nearest['days_to_long_term']} days; selling "
                "before then costs more tax for no other reason."
            )
        parts.append("This is an estimate, not a tax filing. Confirm it with your adviser.")
        return " ".join(parts), ["get_tax_position"], list(result.fact_ids)

    def _answer_xray(self, **_: Any) -> tuple[str, list[str], list[str]]:
        result = self._tool("get_xray")
        data = result.payload
        parts = []
        if data["top_companies"]:
            top = data["top_companies"][0]
            count = len(top["contributors"])
            parts.append(
                f"Your largest single-company exposure is {top['label']} at "
                f"{top['weight']:.1%} of the portfolio"
                + (f", reaching you through {count} separate holdings." if count > 1
                   else ", held directly.")
            )
        real = [s for s in data["sectors"] if s["key"] not in {"diversified", "cash"}]
        if real:
            parts.append(
                "By sector: " + ", ".join(f"{s['label']} {s['weight']:.0%}" for s in real[:4]) + "."
            )
        if data["fund_overlaps"]:
            worst = data["fund_overlaps"][0]
            parts.append(
                f"{worst['left_name']} and {worst['right_name']} overlap "
                f"{worst['overlap']:.0%} of their disclosed holdings, so you are paying two "
                "expense ratios for close to one exposure."
            )
        parts.append(
            f"Look-through covers {data['coverage']:.0%} of your portfolio; the remainder "
            "sits in funds that publish only their largest positions."
        )
        return " ".join(parts), ["get_xray"], list(result.fact_ids)

    def _answer_actions(self, **_: Any) -> tuple[str, list[str], list[str]]:
        result = self._tool("get_recommendations")
        rows = result.payload.get("recommendations", [])
        if result.payload.get("do_nothing") or not rows:
            return (
                "Nothing needs doing. The portfolio was checked against your policy, your "
                "goals and your tax position, and none of them calls for a change this month.",
                ["get_recommendations"], [],
            )
        parts = []
        for row in rows[:3]:
            parts.append(f"{row['headline']} ({row['priority']} priority). {row['reasons'][0]}")
        suppressed = result.payload.get("suppressed", [])
        if suppressed:
            parts.append(
                f"{len(suppressed)} further item(s) were held back: {suppressed[0]['reason']}."
            )
        return " ".join(parts), ["get_recommendations"], []

    def _answer_holdings(self, **_: Any) -> tuple[str, list[str], list[str]]:
        result = self._tool("get_holdings", {"limit": 5})
        rows = result.payload["holdings"]
        parts = [f"You hold {result.payload['total_holdings']} positions. The largest five:"]
        for row in rows:
            parts.append(
                f"{row['label']} at {row['weight']:.1%} "
                f"({format_money(row['market_value'])}, {pct(row['gain_pct'])})."
            )
        return " ".join(parts), ["get_holdings"], list(result.fact_ids)


#: Question shapes the offline path recognises. Ordered most specific first.
_INTENTS: list[tuple[str, re.Pattern]] = [
    ("xray", re.compile(r"x[- ]?ray|look[- ]?through|overlap|sector|really own|actually own", re.I)),
    ("tax", re.compile(r"\btax|ltcg|stcg|capital gain|harvest|exemption", re.I)),
    ("goals", re.compile(r"goal|retire|retirement|education|on track|afford|children|college", re.I)),
    ("risk", re.compile(r"\brisk|crash|fall|drawdown|scenario|volatil|lose|downside", re.I)),
    ("allocation", re.compile(r"alloc|rebalanc|drift|equity|debt|asset mix|weight", re.I)),
    ("actions", re.compile(r"what should i do|should i (buy|sell|switch)|recommend|action|advice", re.I)),
    ("holdings", re.compile(r"holding|position|fund|stock|what do i own|portfolio list", re.I)),
    ("summary", re.compile(r"net worth|how am i doing|summary|overall|health|total", re.I)),
]


def classify(question: str) -> tuple[str, dict[str, Any]]:
    """Route a question to an offline handler.

    Deliberately simple pattern matching. It is a fallback, not a language
    model, and pretending otherwise would be how the offline path starts
    inventing answers instead of admitting it does not understand.
    """
    for intent, pattern in _INTENTS:
        if pattern.search(question):
            return intent, {}
    return "summary", {}


def _assistant_blocks(response: LLMResponse) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if response.text:
        blocks.append({"type": "text", "text": response.text})
    for call in response.tool_calls:
        blocks.append({
            "type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments,
        })
    return blocks


def _render_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k}: {v}" for k, v in list(value.items())[:6]) + "}"
    return str(value)
