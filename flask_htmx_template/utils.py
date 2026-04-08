"""Miscellaneous functions and classes."""

from __future__ import annotations

import ast
import calendar
import contextlib
import datetime
import decimal
import getpass
import logging
import operator as op
import re
import shutil
import sys
from decimal import Decimal
from enum import Enum
from types import GenericAlias, NoneType, UnionType
from typing import cast, get_type_hints, NamedTuple, overload, TYPE_CHECKING

from colorama import Fore

from flask_htmx_template import exceptions as exc

if TYPE_CHECKING:
    from collections.abc import Callable


_REGEX_CC_SC_0 = re.compile(r"(.)([A-Z][a-z]+)")
_REGEX_CC_SC_1 = re.compile(r"([a-z0-9])([A-Z])")

_REGEX_REAL_CLEAN = re.compile(r"[^0-9\.]")

REAL_OPERATORS: dict[type[ast.operator], Callable[[Decimal, Decimal], Decimal]] = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
}
REAL_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[Decimal], Decimal]] = {
    ast.UAdd: op.pos,
    ast.USub: op.neg,
}

MIN_PASS_LEN = 8

MIN_STR_LEN = 2
SEARCH_THRESHOLD = 60
DUPLICATE_THRESHOLD = 80

THRESHOLD_MONTHS = 12 * 1.5
THRESHOLD_WEEKS = 4 * 2
THRESHOLD_DAYS = 7 * 1.5

MONTHS_IN_YEAR = 12
DAYS_IN_YEAR = Decimal("365.25")
DAYS_IN_WEEK = 7

DAYS_IN_QUARTER = int(DAYS_IN_YEAR // 4)

THRESHOLD_HOURS = 96
THRESHOLD_MINUTES = 90
THRESHOLD_SECONDS = 90

SECONDS_IN_MINUTE = 60
SECONDS_IN_HOUR = 60 * SECONDS_IN_MINUTE
SECONDS_IN_DAY = 24 * SECONDS_IN_HOUR

MATCH_PERCENT = Decimal("0.05")
MATCH_ABSOLUTE = Decimal(10)

WEEKDAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


class Downsampled(NamedTuple):
    """downsample results."""

    labels: list[str]
    min: list[Decimal]
    avg: list[Decimal]
    max: list[Decimal]


class Tokens(NamedTuple):
    """tokenize_search_str results."""

    must: set[str]
    can: set[str]
    not_: set[str]


def camel_to_snake(s: str) -> str:
    """Transform CamelCase to snake_case.

    Args:
        s: CamelCase to transform

    Returns:
        snake_case

    """
    s = _REGEX_CC_SC_0.sub(r"\1_\2", s)  # _ at the start of Words
    return _REGEX_CC_SC_1.sub(r"\1_\2", s).lower()  # _ at then end of Words


def get_input(
    prompt: str = "",
    *,
    secure: bool = False,
    print_key: bool | None = None,
) -> str | None:
    """Get input from the user, optionally secure.

    Args:
        prompt: string to print to user
        secure: True will prompt for a password
        print_key: True will print key symbol, False will not, None will check
            stdout.encoding

    Returns:
        str String entered by user, None if canceled

    """
    try:
        if secure:
            secure_icon = "\u26bf"
            if print_key is True or (
                print_key is None
                and sys.stdout.encoding
                and sys.stdout.encoding.lower().startswith("utf-")
            ):
                input_ = getpass.getpass(f"{secure_icon}  {prompt}")
            else:
                input_ = getpass.getpass(prompt)
        else:
            input_ = input(prompt)
    except (KeyboardInterrupt, EOFError):
        return None
    return input_


def get_password() -> str | None:
    """Get password from user input with confirmation.

    Returns:
        Password or None if canceled.

    """
    key: str | None = None
    while key is None:
        key = get_input("Please enter password: ", secure=True)
        if key is None:
            return None

        if len(key) < MIN_PASS_LEN:
            print(  # noqa: T201
                f"{Fore.RED}Password must be at least {MIN_PASS_LEN} characters",
            )
            key = None
            continue

        repeat = get_input("Please confirm password: ", secure=True)
        if repeat is None:
            return None

        if key != repeat:
            print(f"{Fore.RED}Passwords must match")  # noqa: T201
            key = None

    return key


def confirm(
    prompt: str | None = None,
    *,
    default: bool | None = False,
) -> bool | None:
    """Prompt user for yes/no confirmation.

    Args:
        prompt: string to print to user
        default: default response if only [Enter] is pressed

    Returns:
        bool True for yes, False for no

    """
    prompt = prompt or "Confirm"
    prompt += " [Y/n]: " if default else " [y/N]: "

    while True:
        input_ = (input(prompt) or "").lower()
        if not input_:
            return default
        if input_ == "y":
            return True
        if input_ == "n":
            return False
        print("\nPlease enter y or n.\n")  # noqa: T201


def _eval_node(node: ast.expr) -> Decimal:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, int | float | str):
            return Decimal(node.value)
        msg = f"Unknown constant type: {node.value}({type(node.value)})"
        raise TypeError(msg)
    if isinstance(node, ast.BinOp):
        return REAL_OPERATORS[type(node.op)](
            _eval_node(node.left),
            _eval_node(node.right),
        )
    if isinstance(node, ast.UnaryOp):
        return REAL_UNARY_OPERATORS[type(node.op)](_eval_node(node.operand))
    msg = f"Unsupported node: '{type(node)}'"
    raise exc.EvaluationError(msg)


def evaluate_real_statement(s: str | None, precision: int = 2) -> Decimal | None:
    """Evaluate statement, using Decimal for numbers.

    Args:
        s: String statement
        precision: Number of digits to round number to

    Returns:
        Evaluated statement

    """
    if s is None:
        return None
    try:
        value = _eval_node(ast.parse(s, mode="eval").body)
    except (exc.EvaluationError, SyntaxError, TypeError):
        return None
    return round(value, precision)


def parse_real(s: str | None, precision: int = 2) -> Decimal | None:
    """Parse a string into a real number.

    Args:
        s: String to parse
        precision: Number of digits to round number to

    Returns:
        String as number

    """
    if s is None:
        return None
    clean = _REGEX_REAL_CLEAN.sub("", s)
    if not clean:
        return None
    value = -Decimal(clean) if "-" in s or "(" in s else Decimal(clean)
    return round(value, precision)


def parse_bool(s: str | None) -> bool | None:
    """Parse a string into a bool.

    Args:
        s: String to parse

    Returns:
        Parsed bool

    """
    if s is None or not s:
        return None
    return s.lower() in {"true", "t", "1"}


def parse_date(s: str | None) -> datetime.date | None:
    """Parse isoformat date.

    Args:
        s: String to parse

    Returns:
        Date or None

    """
    if s is None or not s:
        return None
    return datetime.date.fromisoformat(s)


def format_days(days: int, labels: list[str] | None = None) -> str:
    """Format number of days to days, weeks, months, or years.

    Args:
        days: Number of days to format
        labels: Override labels [days, weeks, months, years]

    Returns:
        x days
        x weeks
        x months
        x years

    """
    labels = labels or ["days", "weeks", "months", "years"]
    years = days / DAYS_IN_YEAR
    months = years * MONTHS_IN_YEAR
    if months > THRESHOLD_MONTHS:
        return f"{years:.0f} {labels[3]}"
    weeks = days / DAYS_IN_WEEK
    if weeks > THRESHOLD_WEEKS:
        return f"{months:.0f} {labels[2]}"
    if days > THRESHOLD_DAYS:
        return f"{weeks:.0f} {labels[1]}"
    return f"{days} {labels[0]}"


def format_seconds(
    seconds: float,
    labels: list[str] | None = None,
    labels_days: list[str] | None = None,
) -> str:
    """Format number of seconds to seconds, minutes, or hours.

    Args:
        seconds: Number of seconds to format
        labels: Override labels [seconds, minutes, hours]
        labels_days: Override day labels, passed to format_days

    Returns:
        x seconds
        x minutes
        x hours
        x days
        x weeks
        x months
        x years

    """
    labels = labels or ["seconds", "minutes", "hours"]
    hours = seconds / SECONDS_IN_HOUR
    if hours > THRESHOLD_HOURS:
        days = int(seconds // SECONDS_IN_DAY)
        return format_days(days, labels=labels_days)
    minutes = seconds / SECONDS_IN_MINUTE
    if minutes > THRESHOLD_MINUTES:
        return f"{hours:.1f} {labels[2]}"
    if seconds > THRESHOLD_SECONDS:
        return f"{minutes:.1f} {labels[1]}"
    return f"{seconds:.1f} {labels[0]}"


def range_date(
    start: datetime.date | int,
    end: datetime.date | int,
    *,
    include_end: bool = True,
) -> list[datetime.date]:
    """Create a range of dates from start to end.

    Args:
        start: First date
        end: Last date
        include_end: True will include end date in range, False will not

    Returns:
        [start, ..., end] if include_end is True
        [start, ..., end) if include_end is False

    """
    start_ord = start if isinstance(start, int) else start.toordinal()
    end_ord = end if isinstance(end, int) else end.toordinal()
    if include_end:
        end_ord += 1
    return [datetime.date.fromordinal(i) for i in range(start_ord, end_ord)]


def date_add_months(date: datetime.date, months: int) -> datetime.date:
    """Add a number of months to a date.

    Args:
        date: Starting date
        months: Number of months to add, negative okay

    Returns:
        datetime.date(date.year, date.month + months, date.day)

    """
    m_sum = date.month + months - 1
    y = date.year + int(m_sum // 12)
    m = (m_sum % 12) + 1
    # Keep day but max out at end of month
    d = min(date.day, calendar.monthrange(y, m)[1])
    return datetime.date(y, m, d)


def date_months_between(start: datetime.date, end: datetime.date) -> int:
    """Count the numbers of months from start to end.

    Args:
        start: Starting date
        end: Ending date

    Returns:
        Number of months between, ignoring day of month

    """
    dm = end.month - start.month
    dy = end.year - start.year
    return dm + dy * 12


def weekdays_in_month(weekday: int, month: datetime.date) -> int:
    """Count the number of weekdays in a month.

    Args:
        weekday: [0, 6] matching datetime.date.weekday
        month: Month to check

    Returns:
        Number of specific weekday fall inside month

    """
    y = month.year
    m = month.month
    n, remainder = divmod(calendar.monthrange(y, m)[1], DAYS_IN_WEEK)
    if (weekday - month.weekday()) % 7 < remainder:
        return n + 1
    return n


def start_of_month(date: datetime.date) -> datetime.date:
    """Get the start of the month of a date.

    Args:
        date: Starting date

    Returns:
        datetime.date(date.year, date.month, 1)

    """
    return datetime.date(date.year, date.month, 1)


def end_of_month(date: datetime.date) -> datetime.date:
    """Get the end of the month of a date.

    Args:
        date: Starting date

    Returns:
        datetime.date(date.year, date.month, 28 to 31)

    """
    y = date.year
    m = date.month
    return datetime.date(y, m, calendar.monthrange(y, m)[1])


def period_months(start_ord: int, end_ord: int) -> dict[str, tuple[int, int]]:
    """Split a period into months.

    Args:
        start_ord: First date ordinal of period
        end_ord: Last date ordinal of period

    Returns:
        A dictionary of months and the ordinals that start and end them
        dict{"2000-01": (start_ord_0, end_ord_0), "2000-02": ...}
        Results will not fall outside of start_ord and end_ord

    """
    date = datetime.date.fromordinal(start_ord)
    y = date.year
    m = date.month
    end = datetime.date.fromordinal(end_ord)
    end_y = end.year
    end_m = end.month
    months: dict[str, tuple[int, int]] = {}
    while y < end_y or (y == end_y and m <= end_m):
        start_of_month_ = datetime.date(y, m, 1).toordinal()
        end_of_month_ = datetime.date(y, m, calendar.monthrange(y, m)[1]).toordinal()
        months[f"{y:04}-{m:02}"] = (
            max(start_ord, start_of_month_),
            min(end_ord, end_of_month_),
        )
        y += m // 12
        m = (m % 12) + 1
    return months


def period_years(start_ord: int, end_ord: int) -> dict[str, tuple[int, int]]:
    """Split a period into years.

    Args:
        start_ord: First date ordinal of period
        end_ord: Last date ordinal of period

    Returns:
        A dictionary of years and the ordinals that start and end them
        dict{"2000": (start_ord_0, end_ord_0), "2001": ...}
        Results will not fall outside of start_ord and end_ord

    """
    year = datetime.date.fromordinal(start_ord).year
    end_year = datetime.date.fromordinal(end_ord).year
    years: dict[str, tuple[int, int]] = {}
    while year <= end_year:
        jan_1 = datetime.date(year, 1, 1).toordinal()
        dec_31 = datetime.date(year, 12, 31).toordinal()
        years[str(year)] = (max(start_ord, jan_1), min(end_ord, dec_31))
        year += 1
    return years


def round_list(list_: list[Decimal], precision: int = 6) -> list[Decimal]:
    """Round a list, carrying over error such that sum(list) == sum(round_list).

    Args:
        list_: List to round
        precision: Precision to round list to

    Returns:
        List with rounded elements

    """
    residual = Decimal()
    l_rounded: list[Decimal] = []
    for item in list_:
        v = item + residual
        v_round = round(v, precision)
        residual = v - v_round
        l_rounded.append(v_round)

    return l_rounded


def integrate(deltas: list[Decimal | None] | list[Decimal]) -> list[Decimal]:
    """Integrate a list starting.

    Args:
        deltas: Change in values, use None instead of zero for faster speed

    Returns:
        list(values) where
        values[0] = sum(deltas[:1])
        values[1] = sum(deltas[:2])
        ...
        values[n] = sum(deltas[:])

    """
    n = len(deltas)
    current = Decimal()
    result = [Decimal()] * n

    for i, v in enumerate(deltas):
        if v is not None:
            current += v
        result[i] = current

    return result


def interpolate_step(values: list[tuple[int, Decimal]], n: int) -> list[Decimal]:
    """Interpolate a list of (index, value)s using a step function.

    Indices can be outside of [0, n)

    Args:
        values: List of (index, value)
        n: Length of output array

    Returns:
        list of interpolated values where result[i] = most recent values <= i

    """
    result = [Decimal()] * n
    if len(values) == 0:
        return result

    v_current = Decimal()
    values_i = 0
    i_next, v_next = values[values_i]
    for i in range(n):
        # If at a valuation, update current and prep next
        if i >= i_next:
            v_current = v_next
            values_i += 1
            try:
                i_next, v_next = values[values_i]
            except IndexError:
                # End of list, set i_v to n to never change current
                i_next = n
        result[i] = v_current

    return result


def interpolate_linear(values: list[tuple[int, Decimal]], n: int) -> list[Decimal]:
    """Interpolate a list of (index, value)s using a linear function.

    Indices can be outside of [0, n) to interpolate on the boundary

    Args:
        values: List of (index, value)
        n: Length of output array

    Returns:
        list of interpolated values

    """
    result = [Decimal()] * n
    if len(values) == 0:
        return result

    # Starting value
    i_current = 0
    v_current = Decimal()
    values_i = 0
    i_next, v_next = values[values_i]

    if i_next < 0:
        i_current = i_next
        v_current = v_next
        values_i += 1
        slope_i = -i_next

        # Compute slope to next
        try:
            i_next, v_next = values[values_i]
            slope = (v_next - v_current) / (i_next - i_current)
        except IndexError:
            # End of list, set i_v to n to never change current
            i_next = n
            slope = 0

    else:
        slope = 0
        slope_i = 0

    for i in range(n):
        # If at a valuation, update current and prep next
        if i >= i_next:
            i_current = i_next
            v_current = v_next
            values_i += 1
            slope_i = 0

            # Compute slope to next
            try:
                i_next, v_next = values[values_i]
                slope = (v_next - v_current) / (i_next - i_current)
            except IndexError:
                # End of list set i_v to n to never change current
                i_next = n
                slope = 0
            slope_i = 0
        result[i] = v_current + slope * slope_i
        slope_i += 1

    return result


def pretty_table(table: list[list[str] | None]) -> list[str]:
    """Pretty print tabular data.

    First row is header, able to configure how columns behave
    "<Header" will left align text, default
    ">Header" will right align text
    "^Header" will center align text
    "Header." will prioritize this column for truncation with ellipsis if too long
    "Header/" will prevent this column being truncated

    Args:
        table: List of table rows, None will print a horizontal line

    Returns:
        list of lines to print

    Raises:
        ValueError: If table has no rows
        ValueError: If first row is None

    """
    if len(table) < 1:
        msg = "Table has no rows"
        raise ValueError(msg)
    table = list(table)

    header_raw = table.pop(0)
    if header_raw is None:
        msg = "First row cannot be None"
        raise ValueError(msg)

    header = [c.strip("<>^./") for c in header_raw]
    label_widths = [max(4, len(c)) for c in header]
    col_widths = [
        max(len(h), *[len(row[i]) if row else 0 for row in table]) if table else len(h)
        for i, h in enumerate(header)
    ]

    # Adjust col widths if sum is over terminal width
    margin = shutil.get_terminal_size()[0] - sum(col_widths) - len(col_widths) - 2
    excess: list[int] = []
    extra = True
    has_extra: list[bool] = [False] * len(header_raw)
    for i, cell in enumerate(header_raw):
        n_label = label_widths[i]
        if extra and margin > 1:
            # If there is extra room, add some space to each column
            col_widths[i] += 2
            margin -= 2
            has_extra[i] = True
        if margin < 0 and cell[-1] == ".":
            n = max(n_label, col_widths[i] + margin)
            n_trim = col_widths[i] - n
            col_widths[i] = n
            margin += n_trim
            extra = False
        excess.append(0 if cell[-1] == "/" else max(0, col_widths[i] - n_label))

    # Distribute excess
    while margin < 0 and any(excess):
        for i, e in enumerate(excess):
            if margin < 0 and e > 0:
                col_widths[i] -= 1
                excess[i] -= 1
                margin += 1

    formats: list[str] = []
    for cell, n in zip(header_raw, col_widths, strict=True):
        align = cell[0]
        align = align if align in "<>^" else ""
        formats.append(f"{align}{n}")
    return _table_to_lines(header, table, col_widths, formats, has_extra)


def _table_to_lines(
    header: list[str],
    table: list[list[str] | None],
    col_widths: list[int],
    formats: list[str],
    has_extra: list[bool],
) -> list[str]:

    # Print the box
    lines: list[str] = []
    lines.append("╭" + "┬".join("─" * n for n in col_widths) + "╮")
    buf = "│".join(f"{c:^{n}}" for c, n in zip(header, col_widths, strict=True))
    lines.append("│" + buf + "│")
    for row in table:
        if row is None:
            lines.append("╞" + "╪".join("═" * n for n in col_widths) + "╡")
            continue
        formatted_row = [
            (
                cell[: col_widths[i] - 1] + "…"
                if len(cell) > col_widths[i]
                else f"{{:{formats[i]}}}".format(f" {cell} " if has_extra[i] else cell)
            )
            for i, cell in enumerate(row)
        ]
        lines.append("│" + "│".join(formatted_row) + "│")

    lines.append("╰" + "┴".join("─" * n for n in col_widths) + "╯")
    return lines


def clamp(
    value: Decimal,
    c_min: Decimal = Decimal(),
    c_max: Decimal = Decimal(1),
) -> Decimal:
    """Clamp value to range.

    Args:
        value: Value to clamp
        c_min: Minimum value
        c_max: Maximum value

    Returns:
        value clamped to [c_min, c_max]

    """
    if value > c_max:
        return c_max
    if value < c_min:
        return c_min
    return value


@overload
def element_multiply(
    a: list[Decimal],
    b: list[Decimal],
) -> list[Decimal]: ...


@overload
def element_multiply(
    a: list[Decimal | None],
    b: list[Decimal],
) -> list[Decimal | None]: ...


def element_multiply(
    a: list[Decimal] | list[Decimal | None],
    b: list[Decimal],
) -> list[Decimal] | list[Decimal | None]:
    """Multiply two lists element-wise.

    Args:
        a: First list
        b: Second list

    Returns:
        [a[0] * b[0], ..., a[n] * b[n]]

    """
    return [None if aa is None else (aa * bb) for aa, bb in zip(a, b, strict=True)]


def set_sub_keys[_, T, V](dicts: dict[_, dict[T, V]]) -> set[T]:
    """Create a set from the subkeys of a nested dict.

    Args:
        dicts: Dict of dicts

    Returns:
        Set{*d.keys() for d in dicts.values()}

    """
    keys: set[T] = set()
    for d in dicts.values():
        keys.update(d.keys())
    return keys


def json_mutate(obj: object, *, skip_decimal: bool = False) -> object:
    """Mutate an object into JSON representation.

    Args:
        obj: Object to mutate
        skip_decimal: True will not transform Decimal into a string

    Returns:
        JSON types only

    """
    if isinstance(obj, dict):
        obj_dict = cast("dict[object, object]", obj)
        return {
            k: json_mutate(v, skip_decimal=skip_decimal) for k, v in obj_dict.items()
        }
    if isinstance(obj, list | tuple):
        obj_seq = cast("list[object] | tuple[object, ...]", obj)
        return [json_mutate(v, skip_decimal=skip_decimal) for v in obj_seq]
    if isinstance(obj, Enum):
        return obj.name.lower()
    if not skip_decimal and isinstance(obj, Decimal):
        o_int = int(obj)
        return o_int if o_int == obj else str(obj)
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    return obj


_JSON_TYPES: dict[type, str] = {
    list: "an array",
    bool: "a boolean",
    NoneType: "null",
    int: "an integer",
    float: "a number",
    Decimal: "a number",
    dict: "an object",
    str: "a string",
    datetime.date: "an ISO 8601 date string",
    datetime.datetime: "an ISO 8601 date time string with TZ",
}


def _pretty_json_type(t: type[Enum | object]) -> str:
    if issubclass(t, Enum):
        return " or ".join(f'"{e.name.lower()}"' for e in t)
    return _JSON_TYPES.get(t, t.__name__)


def _parse_annotations(
    type_: type | UnionType | GenericAlias,
    *,
    no_typed_dict: bool = False,
) -> tuple[type, ...]:
    if isinstance(type_, UnionType):
        return tuple(
            _parse_annotations(t, no_typed_dict=no_typed_dict)[0]
            for t in type_.__args__
        )
    if isinstance(type_, GenericAlias):
        origin = type_.__origin__
        if not isinstance(origin, type):
            raise TypeError
        return _parse_annotations(origin, no_typed_dict=no_typed_dict)
    if no_typed_dict and issubclass(type_, dict):
        return (dict,)
    return (type_,)


def validate_json[T: object](
    obj: T,
    type_: type | UnionType | GenericAlias,
    *,
    key: str = "",
) -> tuple[T, list[str]]:
    """Validate json matches expected TypedDict.

    Args:
        obj: json object to test
        type_: TypedDict to compare to
        key: Name of path to sub item in json

    Returns:
        tuple(validated object, list of errors)

    """
    key = key or "json"

    to_test = _parse_annotations(type_, no_typed_dict=True)
    if Decimal in to_test and isinstance(obj, (str, float, int)):
        with contextlib.suppress(decimal.InvalidOperation):
            return cast("T", Decimal(obj)), []

    if isinstance(obj, str):
        for t in to_test:
            obj_upgrade, errors = _validate_json_str(obj, t, key=key)
            if not errors:
                return obj_upgrade, errors

    if not isinstance(obj, to_test) and not (isinstance(obj, int) and float in to_test):
        pretty_exp = " or ".join(_pretty_json_type(t) for t in to_test)
        return obj, [
            f"{key} should be {pretty_exp}, not {_pretty_json_type(type(obj))}",
        ]
    if isinstance(obj, list):
        return _validate_json_list(
            obj,  # type: ignore[attr-defined]
            type_,
            key=key,
        )
    if isinstance(obj, dict):
        return _validate_json_dict(
            obj,  # type: ignore[attr-defined]
            type_,
            key=key,
        )
    return obj, []


def _validate_json_str(
    obj: str,
    type_: type,
    *,
    key: str = "",
) -> tuple[object, list[str]]:
    if type_ == datetime.date:
        with contextlib.suppress(ValueError):
            return datetime.date.fromisoformat(obj), []
    elif type_ == datetime.datetime:
        with contextlib.suppress(ValueError):
            d = datetime.datetime.fromisoformat(obj)
            if d.tzinfo is None:
                return obj, [f"{key} is missing time zone"]
            return d, []
    elif issubclass(type_, Enum):
        with contextlib.suppress(ValueError):
            return type_(obj), []
    return obj, ["unknown"]


def _validate_json_list[V: object](
    obj: list[V],
    type_: type[list[V]] | UnionType | GenericAlias,
    *,
    key: str = "",
) -> tuple[list[V], list[str]]:
    errors: list[str] = []
    obj_upgrade: list[V] = []
    if isinstance(type_, GenericAlias):
        # Check all elements are of sub_type
        sub_type: type = type_.__args__[0]
        for i, v in enumerate(obj):
            sub_obj, sub_errors = validate_json(v, sub_type, key=f"{key}[{i}]")
            obj_upgrade.append(sub_obj)
            errors.extend(sub_errors)
        return obj_upgrade, errors
    if isinstance(type_, UnionType):
        # Check if any of them work
        for t in type_.__args__:
            if t is list or isinstance(t, GenericAlias):
                obj_upgrade, errors = _validate_json_list(obj, t, key=key)
                if not errors:
                    return obj_upgrade, []

    return obj, errors


def _validate_json_dict[V: object](
    obj: dict[str, V],
    type_: type[dict[str, V]] | UnionType | GenericAlias,
    *,
    key: str = "",
) -> tuple[dict[str, V], list[str]]:
    errors: list[str] = []
    obj_upgrade: dict[str, V] = {}
    if isinstance(type_, GenericAlias):
        # Check all elements are of sub_type
        sub_type: type = type_.__args__[1]
        for k, v in sorted(obj.items()):
            sub_obj, sub_errors = validate_json(v, sub_type, key=f"{key}.{k}")
            obj_upgrade[k] = sub_obj
            errors.extend(sub_errors)
        return obj_upgrade, errors
    if isinstance(type_, UnionType):
        # Check if any of them work
        union_errors: list[str] = []
        for t in type_.__args__:
            if (isinstance(t, type) and issubclass(t, dict)) or isinstance(
                t,
                GenericAlias,
            ):
                obj_upgrade, union_errors = _validate_json_dict(
                    obj,
                    cast("type[dict[str, V]] | GenericAlias", t),
                    key=key,
                )
                if not union_errors:
                    return obj_upgrade, errors
        errors.extend(union_errors)
        return obj, errors
    hints = get_type_hints(type_)
    if not hints:
        return obj, errors

    obj_copy: dict[str, V] = obj.copy()
    for k, sub_type in sorted(hints.items()):
        if k in obj_copy:
            v = obj_copy.pop(k)
            sub_obj, sub_errors = validate_json(v, sub_type, key=f"{key}.{k}")
            obj_upgrade[k] = sub_obj
            errors.extend(sub_errors)
        else:
            errors.append(f"{key}.{k} is missing")

    errors.extend(f"{key}.{k} is not recognized" for k in obj_copy)

    return obj_upgrade, errors


def init_logger(*, debug: bool = False) -> None:
    """Initialize logger.

    Args:
        debug: True will set the level to DEBUG

    """
    logger = logging.getLogger("flask_htmx_template")

    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    logger.setLevel(logging.DEBUG if debug else logging.INFO)
