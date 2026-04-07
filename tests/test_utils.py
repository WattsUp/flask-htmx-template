from __future__ import annotations

import ast
import datetime
import textwrap
from decimal import Decimal
from types import NoneType
from typing import TYPE_CHECKING, TypedDict

import pytest

from flask_htmx_template import exceptions as exc
from flask_htmx_template import utils
from flask_htmx_template.models.base import BaseEnum
from tests import conftest

if TYPE_CHECKING:
    from tests.conftest import RandomStringGenerator


class Derived(BaseEnum):
    RED = 1
    BLUE = 2
    SEAFOAM_GREEN = 3


@pytest.mark.parametrize(
    ("s", "c"),
    [
        ("CamelCase", "camel_case"),
        ("Camel", "camel"),
        ("camel", "camel"),
        ("HTTPClass", "http_class"),
        ("HTTPClassXYZ", "http_class_xyz"),
    ],
)
def test_camel_to_snake(s: str, c: str) -> None:
    assert utils.camel_to_snake(s) == c


def test_get_input_insecure(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    rand_str_generator: RandomStringGenerator,
) -> None:
    prompt = rand_str_generator()
    prompt_input = rand_str_generator()

    def mock_input(to_print: str) -> str | None:
        print(to_print + prompt_input)
        return prompt_input

    monkeypatch.setattr("builtins.input", mock_input)
    assert utils.get_input(prompt=prompt, secure=False) == prompt_input
    assert capsys.readouterr().out == prompt + prompt_input + "\n"


def test_get_input_insecure_abort(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    rand_str_generator: RandomStringGenerator,
) -> None:
    prompt = rand_str_generator()
    prompt_input = rand_str_generator()

    def mock_input(to_print: str) -> str | None:
        print(to_print + prompt_input)
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", mock_input)
    assert utils.get_input(prompt=prompt, secure=False) is None
    assert capsys.readouterr().out == prompt + prompt_input + "\n"


def test_get_input_secure(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    rand_str_generator: RandomStringGenerator,
) -> None:
    prompt = rand_str_generator()
    prompt_input = rand_str_generator()

    def mock_get_pass(to_print: str) -> str | None:
        print(to_print)
        return prompt_input

    monkeypatch.setattr("getpass.getpass", mock_get_pass)
    assert utils.get_input(prompt=prompt, secure=True, print_key=False) == prompt_input
    assert capsys.readouterr().out == prompt + "\n"


def test_get_input_secure_abort(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    rand_str: str,
) -> None:
    def mock_get_pass(to_print: str) -> str | None:
        print(to_print)
        raise EOFError

    monkeypatch.setattr("getpass.getpass", mock_get_pass)
    assert utils.get_input(prompt=rand_str, secure=True, print_key=False) is None
    assert capsys.readouterr().out == rand_str + "\n"


def test_get_input_secure_with_icon(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    rand_str_generator: RandomStringGenerator,
) -> None:
    prompt = rand_str_generator()
    prompt_input = rand_str_generator()

    def mock_get_pass(to_print: str) -> str | None:
        print(to_print)
        return prompt_input

    monkeypatch.setattr("getpass.getpass", mock_get_pass)
    assert utils.get_input(prompt=prompt, secure=True, print_key=True) == prompt_input
    assert capsys.readouterr().out == "\u26bf  " + prompt + "\n"


@pytest.mark.parametrize(
    ("queue", "target"),
    [
        (["password", "password"], "password"),
        (["short", "password", "typo", "password", "password"], "password"),
        ([None], None),
        (["password", None], None),
    ],
)
def test_get_password(
    monkeypatch: pytest.MonkeyPatch,
    queue: list[str | None],
    target: str,
) -> None:

    def mock_input(to_print: str, *, secure: bool) -> str | None:
        assert secure
        print(to_print)
        return queue.pop(0)

    monkeypatch.setattr(utils, "get_input", mock_input)

    assert utils.get_password() == target


@pytest.mark.parametrize(
    ("queue", "default", "target"),
    [
        ([None], False, False),
        ([None], True, True),
        (["Y"], False, True),
        (["N"], False, False),
        (["bad", "y"], False, True),
    ],
)
def test_confirm(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    rand_str: str,
    queue: list[str | None],
    default: bool,
    target: bool | None,
) -> None:
    retries = len(queue) > 1

    def mock_input(to_print: str) -> str | None:
        print(to_print)
        if len(queue) == 1:
            return queue[0]
        return queue.pop(0)

    monkeypatch.setattr("builtins.input", mock_input)
    assert utils.confirm(prompt=rand_str, default=default) == target

    out = capsys.readouterr().out
    assert rand_str in out
    if default:
        assert "[Y/n]" in out
    else:
        assert "[y/N]" in out

    assert ("Please enter y or n" in out) == retries


@pytest.mark.parametrize(
    ("s", "target"),
    [
        (None, None),
        ("(+21.3e-5*-.1234e5/81.7)*100", Decimal("-3.22")),
        ("-1*2", Decimal(-2)),
        ("1*2", Decimal(2)),
        ("-1*-2", Decimal(2)),
        ("-1*(-2)", Decimal(2)),
        ("2>3", None),
        ("2+5j", None),
        ("(+21.3e-5*-.1234e5/81.7)*", None),
        ("__import__('os').system('rm -rf /')", None),
    ],
)
def test_evaluate_real_statement(s: str | None, target: Decimal | None) -> None:
    assert utils.evaluate_real_statement(s) == target


def test_eval_node_unknown() -> None:
    with pytest.raises(exc.EvaluationError):
        utils._eval_node(ast.expr())


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
    ],
)
def test_parse_real(s: str | None, precision: int, target: Decimal | None) -> None:
    assert utils.parse_real(s, precision=precision) == target


@pytest.mark.parametrize(
    ("s", "target"),
    [
        ("", None),
        ("TRUE", True),
        ("FALSE", False),
        ("t", True),
        ("f", False),
        ("1", True),
        ("0", False),
    ],
)
def test_parse_bool(s: str, target: bool | None) -> None:
    assert utils.parse_bool(s) == target


@pytest.mark.parametrize(
    ("s", "target"),
    [
        ("", None),
        ("2024-01-01", datetime.date(2024, 1, 1)),
    ],
)
def test_parse_date(s: str, target: datetime.date | None) -> None:
    assert utils.parse_date(s) == target


@pytest.mark.parametrize(
    ("d", "target"),
    [
        (0, "0 days"),
        (10, "10 days"),
        (11, "2 weeks"),
        (8 * 7, "8 weeks"),
        (8 * 7 + 1, "2 months"),
        (int(18 * 365.25 / 12), "18 months"),
        (int(18 * 365.25 / 12 + 1), "2 years"),
    ],
)
def test_format_days(d: int, target: str) -> None:
    assert utils.format_days(d) == target


def test_format_days_custom_labels(rand_str_generator: RandomStringGenerator) -> None:
    labels = [rand_str_generator() for _ in range(4)]
    assert utils.format_days(2, labels=labels) == f"2 {labels[0]}"


@pytest.mark.parametrize(
    ("s", "target"),
    [
        (0, "0.0 seconds"),
        (60, "60.0 seconds"),
        (90.1, "1.5 minutes"),
        (5400.1, "1.5 hours"),
        (86400, "24.0 hours"),
        (86400 * 4, "96.0 hours"),
        (86400 * 4.1, "4 days"),
    ],
)
def test_format_seconds(s: float, target: str) -> None:
    assert utils.format_seconds(s) == target


@pytest.mark.parametrize(
    ("include_end", "n"),
    [
        (True, 8),
        (False, 7),
    ],
)
def test_range_date(today: datetime.date, include_end: bool, n: int) -> None:
    end = today + datetime.timedelta(days=7)

    result = utils.range_date(today, end, include_end=include_end)
    assert len(result) == n
    assert result[0] == today
    if include_end:
        assert result[-1] == end
    else:
        assert result[-1] == end - datetime.timedelta(days=1)


@pytest.mark.parametrize(
    ("include_end", "n"),
    [
        (True, 8),
        (False, 7),
    ],
)
def test_range_date_ordinal_input(
    today: datetime.date,
    include_end: bool,
    n: int,
) -> None:
    end = today + datetime.timedelta(days=7)

    result = utils.range_date(
        today.toordinal(),
        end.toordinal(),
        include_end=include_end,
    )
    assert len(result) == n
    assert result[0] == today
    if include_end:
        assert result[-1] == end
    else:
        assert result[-1] == end - datetime.timedelta(days=1)


@pytest.mark.parametrize(
    ("start", "n", "target"),
    [
        (datetime.date(2023, 1, 1), 0, datetime.date(2023, 1, 1)),
        (datetime.date(2023, 1, 1), 1, datetime.date(2023, 2, 1)),
        (datetime.date(2023, 1, 1), 12, datetime.date(2024, 1, 1)),
        (datetime.date(2023, 1, 1), 11, datetime.date(2023, 12, 1)),
        (datetime.date(2023, 1, 1), -1, datetime.date(2022, 12, 1)),
        (datetime.date(2023, 1, 1), -12, datetime.date(2022, 1, 1)),
        (datetime.date(2023, 1, 1), -11, datetime.date(2022, 2, 1)),
        (datetime.date(2023, 6, 30), 0, datetime.date(2023, 6, 30)),
        (datetime.date(2023, 6, 30), 1, datetime.date(2023, 7, 30)),
        (datetime.date(2023, 6, 30), 12, datetime.date(2024, 6, 30)),
        (datetime.date(2023, 6, 30), 23, datetime.date(2025, 5, 30)),
        (datetime.date(2023, 6, 30), -4, datetime.date(2023, 2, 28)),
        (datetime.date(2020, 1, 31), 1, datetime.date(2020, 2, 29)),
    ],
    ids=conftest.id_func,
)
def test_date_add_months(start: datetime.date, n: int, target: datetime.date) -> None:
    assert utils.date_add_months(start, n) == target


def test_period_months_single() -> None:
    start = datetime.date(2023, 1, 10)
    start_ord = start.toordinal()
    end = datetime.date(2023, 1, 28)
    end_ord = end.toordinal()
    target = {
        "2023-01": (start_ord, end_ord),
    }
    assert utils.period_months(start_ord, end_ord) == target


def test_period_months_multiple() -> None:
    start = datetime.date(2023, 1, 10)
    start_ord = start.toordinal()
    end = datetime.date(2023, 2, 14)
    end_ord = end.toordinal()
    target = {
        "2023-01": (start_ord, datetime.date(2023, 1, 31).toordinal()),
        "2023-02": (datetime.date(2023, 2, 1).toordinal(), end_ord),
    }
    assert utils.period_months(start_ord, end_ord) == target


def test_period_years_single_month() -> None:
    start = datetime.date(2023, 1, 10)
    start_ord = start.toordinal()
    end = datetime.date(2023, 1, 28)
    end_ord = end.toordinal()
    target = {
        "2023": (start_ord, end_ord),
    }
    assert utils.period_years(start_ord, end_ord) == target


def test_period_years_two_months() -> None:
    start = datetime.date(2023, 1, 10)
    start_ord = start.toordinal()
    end = datetime.date(2023, 2, 14)
    end_ord = end.toordinal()
    target = {
        "2023": (start_ord, end_ord),
    }
    assert utils.period_years(start_ord, end_ord) == target


def test_period_years_two_years() -> None:
    start = datetime.date(2023, 1, 10)
    start_ord = start.toordinal()
    end = datetime.date(2025, 2, 14)
    end_ord = end.toordinal()
    target = {
        "2023": (start_ord, datetime.date(2023, 12, 31).toordinal()),
        "2024": (
            datetime.date(2024, 1, 1).toordinal(),
            datetime.date(2024, 12, 31).toordinal(),
        ),
        "2025": (datetime.date(2025, 1, 1).toordinal(), end_ord),
    }
    assert utils.period_years(start_ord, end_ord) == target


def test_round_list() -> None:
    n = 9
    list_ = [1 / Decimal(n) for _ in range(n)]
    assert sum(list_) != 1

    l_round = utils.round_list(list_)
    assert sum(l_round) == 1
    assert l_round[0] != list_[0]
    assert l_round[0] == round(list_[0], 6)


@pytest.mark.parametrize(
    ("deltas", "target"),
    [
        pytest.param([], [], id="empty"),
        pytest.param([Decimal()] * 5, [Decimal()] * 5, id="zeros"),
        pytest.param([None] * 5, [Decimal()] * 5, id="nones"),
        pytest.param(
            [None, None, Decimal(20), None, None],
            [Decimal(), Decimal(), Decimal(20), Decimal(20), Decimal(20)],
            id="one sample",
        ),
        pytest.param(
            [Decimal(1), Decimal(3), Decimal(5)],
            [Decimal(1), Decimal(4), Decimal(9)],
            id="all samples",
        ),
    ],
)
def test_integrate(deltas: list[Decimal | None], target: list[Decimal]) -> None:
    assert utils.integrate(deltas) == target


@pytest.mark.parametrize(
    ("values", "target"),
    [
        pytest.param([], [Decimal()] * 5, id="empty"),
        pytest.param([(-3, Decimal(-1))], [Decimal(-1)] * 5, id="past"),
        pytest.param(
            [(-3, Decimal(-1)), (1, Decimal(1))],
            [Decimal(-1)] + [Decimal(1)] * 4,
            id="one in range",
        ),
        pytest.param(
            [(-3, Decimal(-1)), (1, Decimal(1)), (3, Decimal(3))],
            [Decimal(-1), Decimal(1), Decimal(1), Decimal(3), Decimal(3)],
            id="two in range",
        ),
    ],
)
def test_interpolate_step(
    values: list[tuple[int, Decimal]],
    target: list[Decimal],
) -> None:
    assert utils.interpolate_step(values, 5) == target


@pytest.mark.parametrize(
    ("values", "target"),
    [
        pytest.param([], [Decimal()] * 5, id="empty"),
        pytest.param([(-3, Decimal(-1))], [Decimal(-1)] * 5, id="past"),
        pytest.param([(1, Decimal())], [Decimal()] * 5, id="zero"),
        pytest.param(
            [(-3, Decimal(-1)), (1, Decimal(1))],
            [Decimal("0.5"), Decimal(1), Decimal(1), Decimal(1), Decimal(1)],
            id="one in range",
        ),
        pytest.param(
            [(-3, Decimal(-1)), (1, Decimal(1)), (3, Decimal(3))],
            [Decimal("0.5"), Decimal(1), Decimal(2), Decimal(3), Decimal(3)],
            id="two in range",
        ),
    ],
)
def test_interpolate_linear(
    values: list[tuple[int, Decimal]],
    target: list[Decimal],
) -> None:
    assert utils.interpolate_linear(values, 5) == target


def test_pretty_table_no_rows() -> None:
    with pytest.raises(ValueError, match="Table has no rows"):
        utils.pretty_table([])


def test_pretty_table_no_header() -> None:
    with pytest.raises(ValueError, match="First row cannot be None"):
        utils.pretty_table([None])


@pytest.fixture
def fixed_terminal(
    monkeypatch: pytest.MonkeyPatch,
    width: int,
    height: int,
) -> None:
    def mock_terminal_size(**_: object) -> tuple[int, int]:
        return width, height

    monkeypatch.setattr("shutil.get_terminal_size", mock_terminal_size)


@pytest.mark.parametrize(("width", "height"), [(80, 24)])
def test_pretty_table_only_header(fixed_terminal: None) -> None:
    table: list[list[str] | None] = [
        ["H1", ">H2", "<H3", "^H4", "H5.", "H6/"],
    ]
    target = textwrap.dedent(
        """\
    ╭────┬────┬────┬────┬────┬────╮
    │ H1 │ H2 │ H3 │ H4 │ H5 │ H6 │
    ╰────┴────┴────┴────┴────┴────╯""",
    )
    assert "\n".join(utils.pretty_table(table)) == target


@pytest.mark.parametrize(("width", "height"), [(80, 24)])
def test_pretty_table_only_separator(fixed_terminal: None) -> None:
    table: list[list[str] | None] = [
        ["H1", ">H2", "<H3", "^H4", "H5.", "H6/"],
        None,
    ]
    target = textwrap.dedent(
        """\
    ╭────┬────┬────┬────┬────┬────╮
    │ H1 │ H2 │ H3 │ H4 │ H5 │ H6 │
    ╞════╪════╪════╪════╪════╪════╡
    ╰────┴────┴────┴────┴────┴────╯""",
    )
    assert "\n".join(utils.pretty_table(table)) == target


@pytest.fixture
def table() -> list[list[str] | None]:
    return [
        ["H1", ">H2", "<H3", "^H4", "H5.", "H6/"],
        None,
        ["Short"] * 6,
        None,
        ["Long word"] * 6,
    ]


@pytest.mark.parametrize(("width", "height"), [(80, 24)])
def test_pretty_table_width_80(
    fixed_terminal: None,
    table: list[list[str] | None],
) -> None:
    target = textwrap.dedent(
        """\
    ╭───────────┬───────────┬───────────┬───────────┬───────────┬───────────╮
    │    H1     │    H2     │    H3     │    H4     │    H5     │    H6     │
    ╞═══════════╪═══════════╪═══════════╪═══════════╪═══════════╪═══════════╡
    │ Short     │     Short │ Short     │   Short   │ Short     │ Short     │
    ╞═══════════╪═══════════╪═══════════╪═══════════╪═══════════╪═══════════╡
    │ Long word │ Long word │ Long word │ Long word │ Long word │ Long word │
    ╰───────────┴───────────┴───────────┴───────────┴───────────┴───────────╯""",
    )
    assert "\n".join(utils.pretty_table(table)) == target


@pytest.mark.parametrize(("width", "height"), [(70, 24)])
def test_pretty_table_width_70(
    fixed_terminal: None,
    table: list[list[str] | None],
) -> None:
    target = textwrap.dedent(
        """\
    ╭───────────┬───────────┬───────────┬───────────┬─────────┬─────────╮
    │    H1     │    H2     │    H3     │    H4     │   H5    │   H6    │
    ╞═══════════╪═══════════╪═══════════╪═══════════╪═════════╪═════════╡
    │ Short     │     Short │ Short     │   Short   │Short    │Short    │
    ╞═══════════╪═══════════╪═══════════╪═══════════╪═════════╪═════════╡
    │ Long word │ Long word │ Long word │ Long word │Long word│Long word│
    ╰───────────┴───────────┴───────────┴───────────┴─────────┴─────────╯""",
    )
    assert "\n".join(utils.pretty_table(table)) == target


@pytest.mark.parametrize(("width", "height"), [(60, 24)])
def test_pretty_table_width_60(
    fixed_terminal: None,
    table: list[list[str] | None],
) -> None:
    target = textwrap.dedent(
        """\
    ╭─────────┬─────────┬─────────┬─────────┬───────┬─────────╮
    │   H1    │   H2    │   H3    │   H4    │  H5   │   H6    │
    ╞═════════╪═════════╪═════════╪═════════╪═══════╪═════════╡
    │Short    │    Short│Short    │  Short  │Short  │Short    │
    ╞═════════╪═════════╪═════════╪═════════╪═══════╪═════════╡
    │Long word│Long word│Long word│Long word│Long w…│Long word│
    ╰─────────┴─────────┴─────────┴─────────┴───────┴─────────╯""",
    )
    assert "\n".join(utils.pretty_table(table)) == target


@pytest.mark.parametrize(("width", "height"), [(50, 24)])
def test_pretty_table_width_50(
    fixed_terminal: None,
    table: list[list[str] | None],
) -> None:
    target = textwrap.dedent(
        """\
    ╭───────┬───────┬───────┬────────┬────┬─────────╮
    │  H1   │  H2   │  H3   │   H4   │ H5 │   H6    │
    ╞═══════╪═══════╪═══════╪════════╪════╪═════════╡
    │Short  │  Short│Short  │ Short  │Sho…│Short    │
    ╞═══════╪═══════╪═══════╪════════╪════╪═════════╡
    │Long w…│Long w…│Long w…│Long wo…│Lon…│Long word│
    ╰───────┴───────┴───────┴────────┴────┴─────────╯""",
    )
    assert "\n".join(utils.pretty_table(table)) == target


@pytest.mark.parametrize(("width", "height"), [(10, 24)])
def test_pretty_table_width_10(
    fixed_terminal: None,
    table: list[list[str] | None],
) -> None:
    target = textwrap.dedent(
        """\
    ╭────┬────┬────┬────┬────┬─────────╮
    │ H1 │ H2 │ H3 │ H4 │ H5 │   H6    │
    ╞════╪════╪════╪════╪════╪═════════╡
    │Sho…│Sho…│Sho…│Sho…│Sho…│Short    │
    ╞════╪════╪════╪════╪════╪═════════╡
    │Lon…│Lon…│Lon…│Lon…│Lon…│Long word│
    ╰────┴────┴────┴────┴────┴─────────╯""",
    )
    assert "\n".join(utils.pretty_table(table)) == target


@pytest.mark.parametrize(
    ("start", "end", "n"),
    [
        (datetime.date(2024, 11, 1), datetime.date(2024, 11, 1), 0),
        (datetime.date(2024, 11, 1), datetime.date(2024, 11, 30), 0),
        (datetime.date(2024, 11, 1), datetime.date(2024, 12, 31), 1),
        (datetime.date(2023, 11, 1), datetime.date(2024, 10, 15), 11),
        (datetime.date(2024, 11, 1), datetime.date(2023, 10, 15), -13),
    ],
)
def test_date_months_between(start: datetime.date, end: datetime.date, n: int) -> None:
    assert utils.date_months_between(start, end) == n
    assert utils.date_months_between(end, start) == -n


@pytest.mark.parametrize(
    ("weekday", "n"),
    [
        (0, 4),
        (1, 4),
        (2, 4),
        (3, 4),
        (4, 5),
        (5, 5),
        (6, 4),
    ],
)
def test_weekdays_in_month(weekday: int, n: int) -> None:
    date = datetime.date(2024, 11, 1)
    assert utils.weekdays_in_month(weekday, date) == n


def test_start_of_month() -> None:
    date = datetime.date(2024, 2, 20)
    assert utils.start_of_month(date) == datetime.date(2024, 2, 1)


def test_end_of_month() -> None:
    date = datetime.date(2024, 2, 20)
    assert utils.end_of_month(date) == datetime.date(2024, 2, 29)


@pytest.mark.parametrize(
    ("x", "target"),
    [
        (Decimal("0.5"), Decimal("0.5")),
        (Decimal("-0.5"), Decimal()),
        (Decimal("1.5"), Decimal(1)),
    ],
)
def test_clamp(x: Decimal, target: Decimal) -> None:
    assert utils.clamp(x) == target


def test_clamp_custom_max() -> None:
    assert utils.clamp(Decimal(150), c_max=Decimal(100)) == Decimal(100)


def test_clamp_custom_min() -> None:
    assert utils.clamp(Decimal(-150), c_min=Decimal(-100)) == Decimal(-100)


def test_element_multiply() -> None:
    a = [Decimal(1), None, Decimal(3)]
    b = [Decimal(2), Decimal(3), Decimal(4)]
    target = [Decimal(2), None, Decimal(12)]
    assert utils.element_multiply(a, b) == target


def test_set_sub_keys() -> None:
    d: dict[int | str, dict[int | str, int]] = {
        1: {
            "a": 0,
            "b": 1,
        },
        "2": {
            "b": 2,
            3: 4,
        },
    }
    target = {"a", "b", 3}
    assert utils.set_sub_keys(d) == target


class Top(TypedDict):
    bool: bool
    list: list[bool]
    none: None
    object: Top | None


@pytest.mark.parametrize(
    ("obj", "type_", "target"),
    [
        (True, NoneType, ["json should be null, not a boolean"]),
        ([], NoneType, ["json should be null, not an array"]),
        ({}, NoneType, ["json should be null, not an object"]),
        (
            {},
            Top,
            [
                "json.bool is missing",
                "json.list is missing",
                "json.none is missing",
                "json.object is missing",
            ],
        ),
        (None, NoneType, []),
        (None, bool, ["json should be a boolean, not null"]),
        (True, bool, []),
        (None, int, ["json should be an integer, not null"]),
        (0.0, int, ["json should be an integer, not a number"]),
        (0, int, []),
        (None, float, ["json should be a number, not null"]),
        (0, float, []),
        (0.0, float, []),
        (None, list, ["json should be an array, not null"]),
        # Generic typing won't check contents
        ([None], list, []),
        ([None], list[bool], ["json[0] should be a boolean, not null"]),
        (None, list[bool] | None, []),
        ([True], list[bool] | None, []),
        ([None], list[bool] | None, ["json[0] should be a boolean, not null"]),
        (
            [0, None, True],
            list[bool | int],
            ["json[1] should be a boolean or an integer, not null"],
        ),
        (None, dict, ["json should be an object, not null"]),
        # Generic typing won't check contents
        ({"k": None}, dict, []),
        ({"k": None}, dict[str, bool], ["json.k should be a boolean, not null"]),
        ({"k": None}, dict[str, bool] | None, ["json.k should be a boolean, not null"]),
        ({"k": None}, dict[str, bool | None] | None, []),
        (
            {"k": None},
            dict[str, bool | int],
            ["json.k should be a boolean or an integer, not null"],
        ),
        (None, str, ["json should be a string, not null"]),
        ("", str, []),
        (None, int | float, ["json should be an integer or a number, not null"]),
        (None, int | float | None, []),
        (
            {},
            int | float | None,
            ["json should be an integer or a number or null, not an object"],
        ),
    ],
    ids=conftest.id_func,
)
def test_validate_json(obj: object, type_: type, target: list[str]) -> None:
    obj_upgraded, errors = utils.validate_json(obj, type_)
    assert errors == target
    if not target:
        assert obj_upgraded == obj


@pytest.mark.parametrize(
    ("obj", "type_", "target"),
    [
        (datetime.date(2026, 4, 6), datetime.date, []),
        (datetime.date(2026, 4, 6), datetime.date | None, []),
        (
            0,
            datetime.date | None,
            ["json should be an ISO 8601 date string or null, not an integer"],
        ),
        (
            "4/6/2026",
            datetime.date,
            ["json should be an ISO 8601 date string, not a string"],
        ),
        (
            datetime.datetime(2026, 4, 6, 15, 47, 1, tzinfo=datetime.UTC),
            datetime.datetime,
            [],
        ),
        (
            datetime.datetime(2026, 4, 6, 15, 47, 1),  # noqa: DTZ001
            datetime.datetime,
            ["json should be an ISO 8601 date time string with TZ, not a string"],
        ),
        (Derived.SEAFOAM_GREEN, Derived, []),
        (
            "1",
            Derived,
            ['json should be "red" or "blue" or "seafoam_green", not a string'],
        ),
        (
            1,
            Derived,
            ['json should be "red" or "blue" or "seafoam_green", not an integer'],
        ),
        (Decimal(), Decimal, []),
        (Decimal("1234.5"), Decimal, []),
        ("abc", Decimal, ["json should be a number, not a string"]),
    ],
    ids=conftest.id_func,
)
def test_validate_json_upgrade(obj: object, type_: type, target: list[str]) -> None:
    obj_upgraded, errors = utils.validate_json(utils.json_mutate(obj), type_)
    assert errors == target
    if not target:
        assert obj_upgraded == obj


def test_validate_json_nested() -> None:
    j: dict[str, object] = {
        "bool": False,
        "none": None,
        "list": [],
        "object": {
            "bool": False,
            "none": None,
            "list": [True, False],
            "object": None,
        },
    }
    assert not utils.validate_json(j, Top)[1]


def test_validate_json_nested_error() -> None:
    j: dict[str, object] = {
        "list": [None],
        "none": True,
        "object": {
            "bool": None,
            "list": [True, {}],
            "object": [True, False],
        },
        "fake": None,
    }
    assert utils.validate_json(j, Top)[1] == [
        "json.bool is missing",
        "json.list[0] should be a boolean, not null",
        "json.none should be null, not a boolean",
        "json.object.bool should be a boolean, not null",
        "json.object.list[1] should be a boolean, not an object",
        "json.object.none is missing",
        "json.object.object should be an object or null, not an array",
        "json.fake is not recognized",
    ]
