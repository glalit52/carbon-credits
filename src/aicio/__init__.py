"""Personal AI CIO -- an AI-native private investment banker.

The product thesis, in one line: continuously turn a person's whole financial
picture into a small number of explainable decisions, and be willing to say
that no decision is needed.

The architecture follows from that thesis rather than from the usual "app with
an LLM bolted on" shape:

    data -> normalisation -> deterministic calculation -> decision engine
         -> evidence retrieval -> LLM explanation -> safety gate -> user

Two rules hold the whole package together and are enforced by tests:

1.  The language model is never the calculator. Every number a user sees comes
    out of :mod:`aicio.engine`, which has no network and no LLM calls in it at
    all, and arrives carrying a :class:`~aicio.provenance.Provenance` record.
2.  Recommending and executing are separate systems. Nothing in this package
    places a trade; :mod:`aicio.decisions` produces typed proposals and the
    approval trail lives in the store.

Layout
------
``domain``      entities -- user, profile, goals, accounts, holdings, lots
``ips``         Financial DNA -> Investment Policy Statement and suitability
``engine``      deterministic finance: returns, risk, allocation, tax, goals
``ingest``      statement parsing (CSV/XLSX/PDF/CAS) with exceptions
``market``      provider-abstracted market and reference data, with freshness
``decisions``   rule-driven recommendation engine
``alerts``      proactive monitoring with de-duplication and quiet hours
``reports``     daily brief, weekly report, monthly investment committee
``ai``          grounded AI banker: gateway, tools, prompts, safety
``evals``       synthetic-portfolio evaluation suite that gates CI
``store``       SQLite persistence with a hash-chained audit log
``api``         stdlib HTTP API
"""

from __future__ import annotations

__version__ = "1.0.0"

#: Bumped whenever a change alters the numbers the engine produces. Stored on
#: every recommendation so an old decision can be explained with the code that
#: actually made it, rather than with today's code.
ENGINE_VERSION = "engine-2026.09.1"

__all__ = ["__version__", "ENGINE_VERSION"]
