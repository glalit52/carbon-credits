"""The financial AI evaluation suite.

The PRD asks for synthetic portfolios and adversarial cases across seven
properties, and for CI to fail when a critical financial safety test
regresses. That is what this package is, and it is wired into
``tests/aicio/test_evals.py`` so it runs on every commit.

Worth saying explicitly: most of these evals are not about the language model.
Calculation accuracy, suitability and no-action are properties of the engine
and the decision rules. Only grounding and adversarial resistance touch the AI
layer, and they run against the offline gateway so that a failure is a code
defect rather than a prompt regression -- which is the only way a safety test
means anything on a build that has no API key.
"""

from __future__ import annotations

from .scenarios import SCENARIOS, Scenario, build
from .suite import EvalReport, EvalResult, run_suite

__all__ = ["run_suite", "EvalReport", "EvalResult", "SCENARIOS", "Scenario", "build"]
