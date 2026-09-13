"""The recommendation engine.

Rules, not a model. Every candidate action is produced by a named, readable
rule that consumes the deterministic analysis and nothing else, which means
each recommendation can be traced to the exact condition that fired it and to
the numbers that condition tested.

A learned ranker could plausibly order these better. It is not used because
the failure mode is asymmetric: a mis-ranked list costs a user some attention,
while an unexplainable BUY costs them their trust and possibly their money,
and a rule engine can always answer "why am I seeing this".
"""

from __future__ import annotations

from .engine import RecommendationSet, generate
from .rules import RULES, RuleContext, rule
from .scoring import priority_for, rank

__all__ = ["generate", "RecommendationSet", "RULES", "RuleContext", "rule", "priority_for", "rank"]
