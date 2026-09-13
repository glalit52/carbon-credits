"""Turning statements into structured holdings.

Import is where trust in a wealth product is won or lost. A parser that
silently drops a folio produces a portfolio that is wrong in a way nobody can
see, and every downstream number inherits the error.

So the contract here is: parse what can be parsed, refuse to guess, and hand
back every line that could not be read as a typed :class:`ParseException` the
user can correct. A statement that yields 40 holdings and 3 exceptions is a
success. One that yields 43 holdings by inventing three is a failure that will
surface months later as a recommendation nobody can explain.
"""

from __future__ import annotations

from .parser import ParseException, ParseResult, parse_statement, sniff_format
from .normalize import normalise, resolve_asset

__all__ = [
    "parse_statement", "sniff_format", "ParseResult", "ParseException",
    "normalise", "resolve_asset",
]
