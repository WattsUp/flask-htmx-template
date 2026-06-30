"""Base web controller functions."""

from __future__ import annotations

import datetime
import ipaddress
import json
import re
import textwrap
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple, TYPE_CHECKING, TypedDict

import flask
from flask.typing import RouteCallable

from flask_htmx_template import exceptions as exc
from flask_htmx_template import sql, utils
from flask_htmx_template.models.base import BaseEnum
from flask_htmx_template.version import __version__

if TYPE_CHECKING:
    from flask_htmx_template.models.base import (
        Base,
    )


class DuplicateCheck(NamedTuple):
    """Parameters for checking duplicate values in the database."""

    cls: type[Base]
    column: sql.Column
    extra_wheres: list[sql.ColumnClause] | None = None

    def test(self, value: object) -> str:
        """Test for duplicates.

        Args:
            value: value to test

        Returns:
            Error message or ""

        """
        query = self.cls.query().where(
            self.column == value,  # type: ignore[attr-defined]
            *(self.extra_wheres or []),
        )
        if sql.any_(query):
            return "Must be unique"
        return ""


type Routes = dict[str, tuple[RouteCallable, list[str]]]

type JSONResponse = dict[str, object] | tuple[ErrorJSON, int]


class ErrorJSON(TypedDict):
    """Type definition for a errors in JSON API."""

    errors: list[str]


class LinkType(BaseEnum):
    """Header link type."""

    PAGE = 1
    DIALOG = 2
    HX_POST = 3


class Page(NamedTuple):
    """Page specification."""

    icon: str
    endpoint: str
    type_: LinkType = LinkType.PAGE


class PageGroup(NamedTuple):
    """Group of pages specification."""

    name: str
    pages: dict[str, Page]


class BasePageContext(TypedDict):
    """Base full page context type."""

    nav_items: list[PageGroup]
    icons: str
    version: str
    current_year: int


class NamePair(NamedTuple):
    """Key & name pair."""

    key: str
    name: str


class NamePairState(NamedTuple):
    """Key & name pair plus state."""

    key: str
    name: str
    state: bool


HTTP_CODE_OK = 200
HTTP_CODE_REDIRECT = 302
HTTP_CODE_BAD_REQUEST = 400
HTTP_CODE_FORBIDDEN = 403
HTTP_CODE_NOT_FOUND = 404
HTTP_CODE_UNSUPPORTED_MEDIA_TYPE = 415
HTTP_CODE_INTERNAL_ERROR = 500

RE_JINJA = re.compile(r"(\{[{%#]).+?([#%}]\})")
RE_ICON_VAR = re.compile(r'set icon = "([\w\-]+)"')
RE_ICONS = re.compile(r"<icon[^>]*>([\w\-]+)</icon>")
TEMPLATES: dict[Path, tuple[int, set[str]]] = {}
PAGES: list[PageGroup] = []


def ctx_base() -> dict[str, object]:
    """Get the context to build the base response.

    Returns:
        BaseContext

    """
    now = datetime.datetime.now(datetime.UTC).astimezone()
    return {
        "date": now.date().isoformat(),
        "time": now.time().isoformat("seconds"),
    }


def ctx_base_page(
    templates: Path,
    today: datetime.date,
    *,
    debug: bool,
) -> BasePageContext:
    """Get the context to build the base page.

    Args:
        templates: Path to templates
        today: Today's date
        debug: Flask app debug status

    Returns:
        BasePageContext

    """
    if not PAGES:
        nav_items: list[tuple[str, dict[str, Page | None]]] = [
            (
                "",
                {
                    "Dashboard": Page("dashboard", "common.page_dashboard"),
                    "Items": Page("stacks", "items.page_all"),
                    "API": Page("api", "api_docs.page"),
                },
            ),
            (
                "Utilities",
                {
                    "Logout": Page("logout", "auth.logout", LinkType.HX_POST),
                    "Style test": (
                        Page("style", "common.page_style_test") if debug else None
                    ),
                },
            ),
        ]

        # Filter out empty subpages
        no_blanks = [
            PageGroup(
                name,
                {page_name: page for page_name, page in pages.items() if page},
            )
            for name, pages in nav_items
        ]
        # Filter out empty groups
        no_blanks = [group for group in no_blanks if group.pages]
        PAGES.extend(no_blanks)

    # From jinja filters
    icons: set[str] = set()

    for group in PAGES:
        icons.update(page.icon for page in group.pages.values())

    if not TEMPLATES:
        TEMPLATES.update(dict.fromkeys(templates.glob("**/*.jinja"), (0, set())))
    for path, (last_modified_ns, path_icons) in TEMPLATES.items():
        mtime_ns = path.stat().st_mtime_ns
        if mtime_ns == last_modified_ns:
            icons.update(path_icons)
            continue
        buf = path.read_text("utf-8")
        # Look for icon = "" in jinja
        path_icons_new = set(RE_ICON_VAR.findall(buf))

        # Clean out jinja and look for <icon>
        buf = RE_JINJA.sub("", buf)
        path_icons_new.update(RE_ICONS.findall(buf))
        icons.update(path_icons_new)
        TEMPLATES[path] = (mtime_ns, path_icons_new)

    return {
        "nav_items": PAGES,
        "icons": ",".join(sorted(icons)),
        "version": __version__,
        "current_year": today.year,
    }


def dialog_swap(
    content: str | None = None,
    event: str | None = None,
    snackbar: str | None = None,
) -> flask.Response:
    """Create a response to close the dialog and trigger listeners.

    Args:
        content: Content of dialog to swap to, None will close dialog
        event: Event to trigger
        snackbar: Snackbar message to display

    Returns:
        Response that updates dialog OOB and triggers events

    """
    html = flask.render_template(
        "shared/dialog.jinja",
        oob=True,
        content=content or "",
        snackbar=snackbar,
    )
    response = flask.make_response(html)
    if event:
        # # Triggering events should reset dialog & clear history
        events = ["reset-dialog", "clear-history", event]
        response.headers["HX-Trigger"] = ",".join(events)
    return response


def error(e: str | Exception) -> str:
    """Convert exception into an readable error string.

    Args:
        e: Exception to parse

    Returns:
        HTML string response

    """
    icon = "<icon>error</icon>"
    if isinstance(e, exc.IntegrityError):
        # Get the line that starts with (...IntegrityError)
        orig = str(e.orig)
        m = re.match(r"([\w ]+) constraint failed: (\w+).(\w+)(.*)", orig)
        if m is not None:
            constraint = m.group(1)
            table = m.group(2).replace("_", " ").capitalize()
            field = m.group(3)
            additional = m.group(4)
            constraints = {
                "UNIQUE": "be unique",
                "NOT NULL": "not be empty",
            }
            if constraint == "CHECK":
                msg = f"{table} {field}{additional}"
            else:
                s = constraints.get(constraint, "be " + constraint)
                msg = f"{table} {field} must {s}"
        else:  # pragma: no cover
            # Don't need to test fallback
            msg = orig
        return icon + msg

    # Default return exception's string
    return icon + str(e)


def page(content_template: str, title: str, **context: object) -> flask.Response:
    """Render a page with a given content template.

    Args:
        content_template: Path to content template
        title: Title of the page
        context: context passed to render_template

    Returns:
        Whole page or just main body

    """
    if flask.request.headers.get("HX-Request", "false") == "true":
        # Send just the content
        html_title = f"<title>{title} - template</title>\n"
        nav_trigger = "<script>onLoad(nav.update)</script>\n"
        content = flask.render_template(content_template, **context)
        html = html_title + nav_trigger + content
    else:
        templates = Path(flask.current_app.root_path) / (
            flask.current_app.template_folder or "templates"
        )
        html = flask.render_template_string(
            textwrap.dedent(
                f"""\
                {{% extends "shared/base.jinja" %}}
                {{% block content %}}
                {{% include "{content_template}" %}}
                {{% endblock content %}}
                """,
            ),
            title=f"{title} - template",
            **ctx_base_page(
                templates,
                datetime.datetime.now(datetime.UTC),
                debug=flask.current_app.debug,
            ),
            **context,
        )

    # Create response and add Vary: HX-Request
    # Since the cache needs to cache both
    res = flask.make_response(html)
    res.headers["Vary"] = "HX-Request"
    return res


def append_json_newline(res: flask.Response) -> flask.Response:
    """Append a trailing newline to JSON responses for CLI friendliness.

    Args:
        res: HTTP response

    Returns:
        Modified HTTP response

    """
    if res.content_type.startswith("application/json") and not res.data.endswith(b"\n"):
        res.data += b"\n"
    return res


def change_redirect_to_htmx(res: flask.Response) -> flask.Response:
    """Change redirect responses to HX-Redirect.

    Args:
        res: HTTP response

    Returns:
        Modified HTTP response

    """
    if (
        res.status_code == HTTP_CODE_REDIRECT
        and flask.request.headers.get("HX-Request", "false") == "true"
    ):
        # If a redirect is issued to a HX-Request, send OK and HX-Redirect
        res.headers["HX-Redirect"] = res.headers.pop("Location")
        res.status_code = HTTP_CODE_OK
        # werkzeug redirect doesn't have close tags
        # clear body
        res.data = ""

    return res


def find[T: Base](cls: type[T], uri: str) -> T:
    """Find the matching object by URI.

    Args:
        cls: Type of object to find
        uri: URI to find

    Returns:
        Object

    Raises:
        BadRequest: If URI is malformed
        NotFound: If object is not found

    """
    try:
        id_ = cls.uri_to_id(uri)
    except (exc.InvalidURIError, exc.WrongURITypeError) as e:
        raise exc.http.BadRequest(str(e)) from e
    try:
        obj = sql.one(cls.query().where(cls.id_ == id_))
    except exc.NoResultFound as e:
        msg = f"{cls.__name__} {uri} not found in Database"
        raise exc.http.NotFound(msg) from e
    return obj


def parse_period(
    period: str,
    today: datetime.date,
) -> tuple[datetime.date | None, datetime.date]:
    """Parse time period from arguments.

    Args:
        period: Name of period
        today: Today's date

    Returns:
        start, end dates
        start is None for "all"

    Raises:
        BadRequest: If period is unknown

    """
    if period == "ytd":
        start = datetime.date(today.year, 1, 1)
    elif period == "max":
        start = None
    elif m := re.match(r"(\d)yr", period):
        n = max(0, int(m.group(1)))
        start = datetime.date(today.year - n, today.month, today.day)
    elif m := re.match(r"(\d)m", period):
        n = min(0, -int(m.group(1)))
        start = utils.date_add_months(today, n)
    else:
        msg = f"Unknown period '{period}'"
        raise exc.http.BadRequest(msg)

    return start, today


def ctx_to_json(d: dict[str, object], precision: int = 2) -> str:
    """Convert web context to JSON.

    Args:
        d: Object to serialize
        precision: Precision to round real numbers to

    Returns:
        JSON object

    """

    def default(obj: object) -> str | float:
        if isinstance(obj, Decimal):
            return float(round(obj, precision))
        msg = f"Unknown type {type(obj)}"
        raise TypeError(msg)

    return json.dumps(
        utils.json_mutate(d, skip_decimal=True),
        default=default,
        separators=(",", ":"),
    ).replace("'", "\\'")


def validate_string(
    value: str,
    *,
    is_required: bool = False,
    check_length: bool = True,
    duplicate: DuplicateCheck | None = None,
) -> str:
    """Validate a string matches requirements.

    Args:
        value: String to test
        is_required: True will require the value be non-empty
        check_length: True will require value to be MIN_STR_LEN long
        duplicate: Duplicate check parameters

    Returns:
        Error message or ""

    """
    value = value.strip()
    if not value:
        return "Required" if is_required else ""
    if check_length and len(value) < utils.MIN_STR_LEN:
        # Ticker can be short
        return f"{utils.MIN_STR_LEN} characters required"
    if duplicate is None:
        return ""
    return duplicate.test(value)


def validate_date(
    value: str,
    today: datetime.date,
    *,
    is_required: bool = False,
    max_future: int | None = utils.DAYS_IN_WEEK,
    duplicate: DuplicateCheck | None = None,
) -> str:
    """Validate a date string matches requirements.

    Args:
        value: Date string to test
        today: Today's date
        is_required: True will require the value be non-empty
        max_future: Maximum number of days date is allowed in the future
        duplicate: Duplicate check parameters

    Returns:
        Error message or ""

    """
    value = value.strip()
    try:
        date = utils.parse_date(value)
    except ValueError:
        return "Unable to parse"
    if date is None:
        return "Required" if is_required else ""

    if max_future == 0:
        if date > today:
            return "Cannot be in advance"
    elif max_future is not None and date > (
        today + datetime.timedelta(days=max_future)
    ):
        return f"Only up to {utils.format_days(max_future)} in advance"

    if duplicate is None:
        return ""
    return duplicate.test(date.toordinal())


def validate_real(
    value: str,
    *,
    is_required: bool = False,
    is_positive: bool = False,
) -> str:
    """Validate a number string matches requirements.

    Args:
        value: Number string to test
        is_required: True will require the value be non-empty
        is_positive: True will require the value be > 0

    Returns:
        Error message or ""

    """
    value = value.strip()
    if not value:
        return "Required" if is_required else ""
    n = utils.evaluate_real_statement(value)
    if n is None:
        return "Unable to parse"
    if is_positive and n <= 0:
        return "Must be positive"
    return ""


def validate_int(
    value: str,
    *,
    is_required: bool = False,
    is_positive: bool = False,
) -> str:
    """Validate an integer string matches requirements.

    Args:
        value: Number string to test
        is_required: True will require the value be non-empty
        is_positive: True will require the value be > 0

    Returns:
        Error message or ""

    """
    value = value.strip()
    if not value:
        return "Required" if is_required else ""
    try:
        n = int(value)
    except ValueError:
        return "Unable to parse"
    if is_positive and n <= 0:
        return "Must be positive"
    return ""


def validate_ip(
    value: str,
    *,
    is_required: bool = False,
) -> str:
    """Validate an IP matches requirements.

    Args:
        value: String to test
        is_required: True will require the value be non-empty

    Returns:
        Error message or ""

    """
    value = value.strip()
    if not value:
        return "Required" if is_required else ""
    if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", value):
        return "Expected xxx.xxx.xxx.xxx format"
    try:
        ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        return "Could not parse"
    return ""


def validate_ip_cidr(
    value: str,
    *,
    is_required: bool = False,
    is_local: bool = False,
) -> str:
    """Validate an IP matches CIDR requirements.

    Args:
        value: String to test
        is_required: True will require the value be non-empty
        is_local: True will require the value to be a local subnet

    Returns:
        Error message or ""

    """
    value = value.strip()
    if not value:
        return "Required" if is_required else ""
    if not re.match(r"^\d{1,3}(\.\d{1,3}){3}/\d\d?$", value):
        return "Expected xxx.xxx.xxx.xxx/xx format"
    try:
        net = ipaddress.IPv4Network(value, strict=False)
    except ipaddress.AddressValueError:
        return "Could not parse"
    except ipaddress.NetmaskValueError as e:
        return str(e)
    if is_local and net.is_global:
        return "Subnet is not local"
    return ""


def parse_date(
    value: str,
    today: datetime.date,
    *,
    max_future: int | None = utils.DAYS_IN_WEEK,
) -> datetime.date:
    """Parse a date string.

    Args:
        value: Raw string to parse
        today: Today's date
        max_future: Maximum number of days date is allowed in the future

    Returns:
        date object

    Raises:
        ValueError: if failed to parse, empty, or in advance

    """
    try:
        date = utils.parse_date(value)
    except ValueError as e:
        msg = "Unable to parse date"
        raise ValueError(msg) from e
    if date is None:
        msg = "Date must not be empty"
        raise ValueError(msg)
    if max_future == 0:
        if date > today:
            msg = "Cannot be in advance"
            raise ValueError(msg)
    elif max_future is not None and date > (
        today + datetime.timedelta(days=max_future)
    ):
        msg = f"Only up to {utils.format_days(max_future)} in advance"
        raise ValueError(msg)

    return date
