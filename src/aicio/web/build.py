"""Render the dashboard from an analysis.

The page is built and reviewed, then committed and shipped as-is. Regenerating
it at deploy time would make what a user sees depend on whatever the build
container happened to have, which for a page full of someone's net worth is the
wrong trade.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from .. import __version__
from ..ai import AIBanker
from ..ai.gateway import OfflineGateway
from ..analysis import PortfolioAnalysis, analyse
from ..decisions import generate
from ..decisions.engine import RecommendationSet
from ..money import as_float
from ..provenance import utcnow

TEMPLATE = Path(__file__).with_name("template.html")

#: Simulation trials behind the published page. Pinned rather than left to the
#: caller's default, because the committed dashboard is checked against a
#: rebuild in CI and a different trial count moves a goal probability by a
#: tenth of a point -- enough to fail a strict comparison for no real reason.
DASHBOARD_TRIALS = 2000

#: Questions the page answers up front. Chosen because they are the four a
#: client actually opens the app to ask.
DEFAULT_QUESTIONS = [
    "How am I doing?",
    "What do I actually own?",
    "What should I do now?",
    "What happens if the market falls?",
]


def build_payload(
    analysis: PortfolioAnalysis,
    recommendations: RecommendationSet,
    *,
    questions: Sequence[str] = DEFAULT_QUESTIONS,
    include_chat: bool = True,
) -> dict[str, Any]:
    """Assemble everything the page renders.

    The chat answers are generated at build time through the offline gateway,
    so the published page carries real, grounded answers rather than a text box
    that needs a backend. Each one records whether it passed the grounding gate,
    which is the point: a reader can see the check ran.
    """
    chat: list[dict[str, Any]] = []
    if include_chat:
        banker = AIBanker(analysis, recommendations, gateway=OfflineGateway())
        for question in questions:
            reply = banker.ask(question)
            chat.append({
                "question": question,
                "answer": reply.text,
                "grounded": bool(reply.grounding and reply.grounding.grounded),
                "tools": reply.tools_used,
                "provider": f"{reply.provider}/{reply.model}",
                "prompt_id": reply.prompt_id,
            })

    return {
        "version": __version__,
        "engine_version": analysis.engine_version,
        "generated_at": utcnow().isoformat(timespec="seconds"),
        "as_of": analysis.as_of.isoformat(),
        "fingerprint": analysis.fingerprint,
        "net_worth": round(analysis.net_worth, 2),
        "market_value": round(as_float(analysis.portfolio.market_value), 2),
        "invested": round(as_float(analysis.portfolio.invested), 2),
        "cash": round(as_float(analysis.portfolio.cash), 2),
        "unrealised_gain": round(as_float(analysis.portfolio.unrealised_gain), 2),
        "xirr": analysis.portfolio_xirr,
        "liquid_months": analysis.liquid_months,
        "health": analysis.health.to_dict(),
        "drift": analysis.drift.to_dict(),
        "allocation": analysis.breakdown.to_dict(),
        "goals": [p.to_dict() for p in analysis.projections],
        "scenarios": [s.to_dict() for s in analysis.scenarios],
        "holdings": [h.to_dict() for h in analysis.holdings],
        "xray": analysis.xray.to_dict(),
        "overlaps": [o.to_dict() for o in analysis.overlaps],
        "single_names": [s.to_dict() for s in analysis.single_names],
        "tax": analysis.tax.to_dict(),
        "sip_plan": analysis.sip_plan.to_dict(),
        "policy": analysis.policy.to_dict(),
        "actions": [r.to_dict() for r in recommendations.recommendations],
        "do_nothing": recommendations.do_nothing,
        "chat": chat,
    }


def render(payload: dict[str, Any], *, template: Path = TEMPLATE) -> str:
    text = template.read_text()
    if "__DATA__" not in text:
        raise ValueError("template has no __DATA__ placeholder")
    data = json.dumps(payload, default=str, separators=(",", ":"))
    # The payload sits inside a <script type="application/json">, so the only
    # sequence that can break out of it is a literal closing script tag.
    return text.replace("__DATA__", data.replace("</", "<\\/"))


def build(
    out_dir: Path,
    *,
    db: Path | None = None,
    user: str = "user_demo",
    seed: bool = False,
    questions: Sequence[str] = DEFAULT_QUESTIONS,
) -> list[Path]:
    """Build the dashboard for one user. Returns the paths written."""
    from ..crypto import CryptoError, SealedBox
    from ..seed import demo_bundle
    from ..store import Store

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if db is None:
        bundle = demo_bundle()
        analysis = analyse(
            bundle["portfolio"], bundle["profile"], bundle["policy"], bundle["goals"],
            today=bundle["as_of"], quality=bundle["quality"], behaviour=bundle["behaviour"],
            monte_carlo_trials=DASHBOARD_TRIALS,
        )
        recommendations = generate(analysis, today=bundle["as_of"], limit=0)
    else:
        try:
            box = SealedBox.from_environment("documents")
        except CryptoError:
            box = None
        store = Store(db, actor="dashboard", box=box)
        if seed:
            bundle = demo_bundle()
            store.save_user(bundle["user"])
            store.save_profile(bundle["profile"])
            store.save_policy(bundle["policy"])
            store.save_goals(bundle["goals"])
            store.save_portfolio(bundle["portfolio"])
        from ..api import _context
        analysis, recommendations, *_ = _context(store, user)
        store.close()

    payload = build_payload(analysis, recommendations, questions=questions)
    index = out_dir / "index.html"
    index.write_text(render(payload))
    data = out_dir / "data.json"
    data.write_text(json.dumps(payload, indent=2, default=str))
    return [index, data]
