"""Money parsing, arithmetic and the Indian numbering convention."""

from __future__ import annotations

from decimal import Decimal

import pytest

from aicio.money import (
    MoneyError, as_float, format_money, money, pct, quantity, total,
)


@pytest.mark.parametrize("raw,expected", [
    ("1,23,456.78", "123456.78"),
    ("₹1,23,456.78", "123456.78"),
    ("Rs. 5,000", "5000"),
    ("(1,500.00)", "-1500"),          # accountancy negative
    ("2500-", "-2500"),               # trailing-sign export
    ("  42  ", "42"),
    (1234.5, "1234.5"),
    (Decimal("7.25"), "7.25"),
])
def test_money_parses_the_forms_statements_actually_use(raw, expected):
    assert money(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", ["", "abc", None, True, float("nan")])
def test_money_refuses_what_it_cannot_read(raw):
    with pytest.raises(MoneyError):
        money(raw)


def test_quantity_keeps_fractional_units():
    """Mutual funds trade in fractions; rounding to whole units loses money."""
    assert quantity("1234.56789") == Decimal("1234.5679")


def test_total_stays_in_the_decimal_domain():
    amounts = [money("0.1")] * 10
    assert total(amounts) == Decimal("1.0000")


def test_indian_grouping():
    assert format_money(12345678.91) == "₹1,23,45,678.91"
    assert format_money(1234.5) == "₹1,234.50"
    assert format_money(-1234.5) == "-₹1,234.50"


def test_compact_uses_crores_and_lakhs_for_rupees():
    assert format_money(12345678, compact=True) == "₹1.23Cr"
    assert format_money(250000, compact=True) == "₹2.5L"


def test_western_grouping_for_other_currencies():
    assert format_money(1234567.5, "USD") == "$1,234,567.50"
    assert format_money(1234567.5, "USD", compact=True) == "$1.23M"


def test_unsupported_currency_fails_loudly():
    with pytest.raises(MoneyError):
        format_money(100, "XYZ")


def test_percentages_always_carry_their_sign():
    assert pct(-0.0423) == "-4.23%"
    assert pct(0.0423) == "+4.23%"


def test_float_crossing_is_one_way():
    assert as_float(money("100.25")) == 100.25
