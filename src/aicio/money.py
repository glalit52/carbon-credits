"""Money, and the arithmetic that is allowed to touch it.

Currency amounts are :class:`~decimal.Decimal`, quantised to four places
internally and two for presentation. Statistical measures -- volatility,
correlation, XIRR -- are floats, because they are estimates of a distribution
and pretending otherwise with Decimal would buy nothing but slowness.

The boundary between the two is deliberate and one-way: money converts to
float for statistics via :func:`as_float`, and a statistic never converts back
into a balance. A returns series is not a ledger.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Iterable

getcontext().prec = 28

#: Internal storage precision. Four places survives unit prices (a mutual fund
#: NAV moves in fourths of a paisa) without accumulating representation dust.
CENTS = Decimal("0.0001")
DISPLAY = Decimal("0.01")
UNITS = Decimal("0.0001")

ZERO = Decimal("0")

#: ISO 4217 -> (symbol, minor units). Only what the product actually supports;
#: an unknown currency should fail loudly rather than render as a bare number.
CURRENCIES: dict[str, tuple[str, int]] = {
    "INR": ("₹", 2),
    "USD": ("$", 2),
    "EUR": ("€", 2),
    "GBP": ("£", 2),
    "SGD": ("S$", 2),
    "AED": ("د.إ", 2),
}


class MoneyError(ValueError):
    """Raised when a value cannot be interpreted as an amount of money."""


def money(value: object) -> Decimal:
    """Coerce anything sane into a quantised Decimal amount.

    Accepts Decimal, int, float and str (including the grouped forms that turn
    up in statements: ``1,23,456.78``, ``₹1,234``, ``(500)`` for negatives).
    """
    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, bool):                       # bool is an int; refuse
        raise MoneyError("bool is not an amount")
    elif isinstance(value, (int, float)):
        dec = Decimal(str(value))
    elif isinstance(value, str):
        dec = _parse(value)
    else:
        raise MoneyError(f"cannot read {value!r} as money")
    if not dec.is_finite():
        raise MoneyError(f"non-finite amount: {value!r}")
    return dec.quantize(CENTS, rounding=ROUND_HALF_UP)


def _parse(raw: str) -> Decimal:
    text = raw.strip()
    if not text:
        raise MoneyError("empty amount")
    negative = False
    if text.startswith("(") and text.endswith(")"):     # accountancy negative
        negative, text = True, text[1:-1]
    for symbol, _ in CURRENCIES.values():
        text = text.replace(symbol, "")
    text = text.replace("Rs.", "").replace("Rs", "").replace(",", "").replace(" ", "")
    text = text.replace("₹", "").replace("\xa0", "")
    if text.endswith("-"):                              # trailing-sign exports
        negative, text = True, text[:-1]
    if text.startswith("-"):
        negative, text = True, text[1:]
    if not text:
        raise MoneyError(f"no digits in {raw!r}")
    try:
        dec = Decimal(text)
    except Exception as exc:                            # noqa: BLE001 - rewrap
        raise MoneyError(f"cannot read {raw!r} as money") from exc
    return -dec if negative else dec


def quantity(value: object) -> Decimal:
    """Units of an instrument. Mutual funds trade in fractional units, so this
    keeps four places rather than rounding to whole shares."""
    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        dec = Decimal(str(value))
    elif isinstance(value, str):
        dec = _parse(value)
    else:
        raise MoneyError(f"cannot read {value!r} as a quantity")
    return dec.quantize(UNITS, rounding=ROUND_HALF_UP)


def total(amounts: Iterable[Decimal]) -> Decimal:
    """Sum amounts without leaving the Decimal domain."""
    out = ZERO
    for amount in amounts:
        out += amount
    return out.quantize(CENTS, rounding=ROUND_HALF_UP)


def as_float(amount: Decimal | float | int) -> float:
    """Cross into the statistics domain. One-way, on purpose."""
    return float(amount)


def round_display(amount: Decimal) -> Decimal:
    return Decimal(amount).quantize(DISPLAY, rounding=ROUND_HALF_UP)


def format_money(amount: Decimal | float, currency: str = "INR", *, compact: bool = False) -> str:
    """Render an amount the way the user's market writes it.

    India groups in lakhs and crores, and a mass-affluent user reading
    "₹1,23,45,678" recognises their own net worth far faster than they
    recognise "₹12,345,678".
    """
    if currency not in CURRENCIES:
        raise MoneyError(f"unsupported currency {currency!r}")
    symbol, _ = CURRENCIES[currency]
    value = Decimal(amount) if not isinstance(amount, Decimal) else amount
    negative = value < 0
    value = abs(value)

    if compact:
        body = _compact(value, currency)
    elif currency == "INR":
        body = _indian_grouping(round_display(value))
    else:
        body = f"{round_display(value):,.2f}"
    return f"{'-' if negative else ''}{symbol}{body}"


def _compact(value: Decimal, currency: str) -> str:
    if currency == "INR":
        scales = [(Decimal("1e7"), "Cr"), (Decimal("1e5"), "L"), (Decimal("1e3"), "K")]
    else:
        scales = [(Decimal("1e9"), "B"), (Decimal("1e6"), "M"), (Decimal("1e3"), "K")]
    for cut, suffix in scales:
        if value >= cut:
            scaled = (value / cut).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return f"{scaled.normalize():f}{suffix}"
    return f"{round_display(value):,.2f}"


def _indian_grouping(value: Decimal) -> str:
    whole, _, frac = f"{value:.2f}".partition(".")
    if len(whole) <= 3:
        head = whole
    else:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        head = ",".join(groups) + "," + tail
    return f"{head}.{frac}"


def pct(value: float, places: int = 2) -> str:
    """Percentages are shown with an explicit sign: a portfolio report that
    hides the minus is a portfolio report nobody trusts twice."""
    return f"{value * 100:+.{places}f}%"
