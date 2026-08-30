from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from flask_htmx_template import parsing


@pytest.mark.parametrize(
    ("s", "precision", "target"),
    [
        (None, 2, None),
        ("", 2, None),
        ("Not a number", 2, None),
        ("1000.1", 2, Decimal("1000.1")),
        ("1000", 2, Decimal(1000)),
        ("$1,000.101", 2, Decimal("1000.1")),
        ("$1,000.101", 3, Decimal("1000.101")),
        ("-$1,000.101", 2, Decimal("-1000.1")),
        ("-$1,000.101", 3, Decimal("-1000.101")),
        ("($1,000.101)", 2, Decimal("-1000.1")),
    ],
)
def test_real(s: str | None, precision: int, target: Decimal | None) -> None:
    result = parsing.real(s, precision=precision)

    assert result == target


def test_real_without_rounding() -> None:
    result = parsing.real("0.001", precision=None)

    assert result == Decimal("0.001")


@pytest.mark.parametrize(
    ("s", "target"),
    [(None, None), ("", None), ("1,234.56", 1234), ("-$1,234.56", -1234)],
)
def test_int(s: str | None, target: int | None) -> None:
    result = parsing.int_(s)

    assert result == target


@pytest.mark.parametrize(
    ("s", "target"),
    [
        (None, None),
        ("", None),
        ("TRUE", True),
        ("FALSE", False),
        ("t", True),
        ("f", False),
        ("1", True),
        ("0", False),
        ("yes", False),
    ],
)
def test_bool(s: str | None, target: bool | None) -> None:
    result = parsing.bool_(s)

    assert result == target


@pytest.mark.parametrize(
    ("s", "target"),
    [(None, None), ("", None), ("2024-01-01", datetime.date(2024, 1, 1))],
)
def test_date(s: str | None, target: datetime.date | None) -> None:
    result = parsing.date(s)

    assert result == target


def test_date_rejects_non_iso_format() -> None:
    with pytest.raises(ValueError, match="Invalid isoformat string"):
        parsing.date("01/01/2024")
