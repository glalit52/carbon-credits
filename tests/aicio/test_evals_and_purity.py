"""The two structural guarantees: the engine is pure, and the suite gates CI."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from aicio.analysis import analyse
from aicio.decisions import generate
from aicio.evals import SCENARIOS, run_suite
from aicio.evals.suite import CRITICAL

ENGINE = Path(__file__).resolve().parents[2] / "src" / "aicio" / "engine"

#: Modules the engine must never reach for. Network, clocks and the AI layer
#: would each make a calculation depend on something other than its arguments.
FORBIDDEN_IMPORTS = {
    "urllib", "http", "socket", "requests", "httpx", "asyncio", "subprocess",
    "aicio.ai", "aicio.market", "aicio.decisions", "aicio.store", "aicio.api",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
            if node.level == 0:
                found.add(node.module)
    return found


@pytest.mark.parametrize("path", sorted(ENGINE.glob("*.py")), ids=lambda p: p.name)
def test_the_engine_has_no_network_and_no_model(path):
    """The rule that holds the package together: financial calculations live
    somewhere a language model cannot reach."""
    assert not (_imports(path) & FORBIDDEN_IMPORTS), path.name


@pytest.mark.parametrize("path", sorted(ENGINE.glob("*.py")), ids=lambda p: p.name)
def test_the_engine_does_not_read_the_clock(path):
    """A hidden ``date.today()`` makes a calculation irreproducible, which
    breaks 'explain the recommendation you made in March'."""
    source = path.read_text()
    for banned in ("datetime.now(", "time.time(", "date.today()"):
        # Default arguments are the one place a clock read is acceptable, and
        # the engine does not use any.
        assert banned not in source, f"{path.name} reads the clock via {banned}"


def test_the_analysis_is_reproducible(bundle):
    """Same inputs, same numbers -- the property every stored recommendation
    depends on."""
    args = dict(today=bundle["as_of"], quality=bundle["quality"],
                behaviour=bundle["behaviour"], monte_carlo_trials=200)
    first = analyse(bundle["portfolio"], bundle["profile"], bundle["policy"],
                    bundle["goals"], **args)
    second = analyse(bundle["portfolio"], bundle["profile"], bundle["policy"],
                     bundle["goals"], **args)
    assert first.fingerprint == second.fingerprint
    assert first.health.score == second.health.score
    assert [p.probability for p in first.projections] == \
        [p.probability for p in second.projections]
    assert [r.id for r in generate(first, today=bundle["as_of"]).recommendations] == \
        [r.id for r in generate(second, today=bundle["as_of"]).recommendations]


def test_the_fingerprint_changes_when_the_portfolio_does(bundle):
    from aicio.money import quantity

    portfolio = bundle["portfolio"]
    before = portfolio.fingerprint()
    portfolio.holdings[0].units = quantity(float(portfolio.holdings[0].units) + 1)
    assert portfolio.fingerprint() != before
    portfolio.holdings[0].units = quantity(float(portfolio.holdings[0].units) - 1)


# ---------------------------------------------------------------------------
# The suite itself
# ---------------------------------------------------------------------------

def test_the_eval_suite_passes():
    """This is the CI gate the PRD asks for: a regression in calculation,
    grounding, suitability or adversarial resistance fails the build."""
    report = run_suite()
    assert report.passed, "\n".join(r.render() for r in report.critical_failures)


def test_the_suite_covers_every_property_the_prd_names():
    categories = set(run_suite().by_category())
    assert {"calculation", "grounding", "suitability", "uncertainty",
            "no_action", "consistency", "adversarial"} <= categories


def test_the_critical_categories_are_the_financial_safety_ones():
    assert {"calculation", "suitability", "adversarial", "grounding"} <= CRITICAL


def test_every_scenario_is_distinct_and_documented():
    keys = [s.key for s in SCENARIOS]
    assert len(keys) == len(set(keys))
    assert all(s.description for s in SCENARIOS)


def test_the_suite_reports_rather_than_hiding_a_warning():
    report = run_suite()
    assert report.render().strip().endswith("OK")
    assert len(report.results) > 50
