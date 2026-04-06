from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from flask_htmx_template.models import base

if TYPE_CHECKING:
    from collections.abc import Mapping


class Derived(base.BaseEnum):
    RED = 1
    BLUE = 2
    SEAFOAM_GREEN = 3

    @classmethod
    def lut(cls) -> Mapping[str, Derived]:
        return {"r": cls.RED, "b": cls.BLUE}


def test_hasable() -> None:
    d = {
        Derived.RED: "red",
        Derived.BLUE: "blue",
    }
    assert isinstance(d, dict)


def test_missing_none() -> None:
    with pytest.raises(ValueError, match="None is not a valid Derived"):
        Derived(None)


def test_missing_empty() -> None:
    with pytest.raises(ValueError, match="'' is not a valid Derived"):
        Derived("")


def test_missing_fake() -> None:
    with pytest.raises(ValueError, match="'FAKE' is not a valid Derived"):
        Derived("FAKE")


@pytest.mark.parametrize("e", Derived)
def test_missing_each_enum(e: Derived) -> None:
    assert Derived(e) == e
    assert Derived(e.name) == e
    assert Derived(e.value) == e


@pytest.mark.parametrize(("s", "e"), Derived.lut().items())
def test_missing_each_lut(s: str, e: Derived) -> None:
    assert Derived(s.upper()) == e


@pytest.mark.parametrize("other", [Derived.RED, "RED"])
def test_comparators_eq(other: Derived | str) -> None:
    assert Derived.RED == other  # noqa: SIM300
    assert other == Derived.RED


@pytest.mark.parametrize("other", [Derived.BLUE, "BLUE"])
def test_comparators_ne(other: Derived | str) -> None:
    assert Derived.RED != other  # noqa: SIM300
    assert other != Derived.RED


@pytest.mark.parametrize(
    ("e", "s"),
    [
        (Derived.RED, "Derived.RED"),
        (Derived.SEAFOAM_GREEN, "Derived.SEAFOAM_GREEN"),
    ],
)
def test_str(e: Derived, s: str) -> None:
    assert str(e) == s


@pytest.mark.parametrize(
    ("e", "s"),
    [
        (Derived.RED, "Red"),
        (Derived.SEAFOAM_GREEN, "Seafoam Green"),
    ],
)
def test_pretty(e: Derived, s: str) -> None:
    assert e.pretty == s
