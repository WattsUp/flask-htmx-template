from __future__ import annotations

import datetime
import re
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import flask
import pytest

import flask_htmx_template
from flask_htmx_template import exceptions as exc
from flask_htmx_template import utils
from flask_htmx_template.controllers import base
from flask_htmx_template.models.item import Item
from flask_htmx_template.version import __version__
from tests import conftest

if TYPE_CHECKING:
    from collections.abc import Callable

    import werkzeug.test

    from tests.conftest import RandomStringGenerator
    from tests.controllers.conftest import HTMLValidator, WebClient


def test_find(item: Item) -> None:
    assert base.find(Item, item.uri) == item


def test_find_404() -> None:
    with pytest.raises(exc.http.NotFound):
        base.find(Item, Item.id_to_uri(0))


def test_find_400() -> None:
    with pytest.raises(exc.http.BadRequest):
        base.find(Item, "fake")


@pytest.mark.parametrize(
    ("period", "months"),
    [
        ("1m", -1),
        ("6m", -6),
        ("1yr", -12),
        ("max", None),
    ],
)
def test_parse_period(today: datetime.date, period: str, months: int | None) -> None:
    start = None if months is None else utils.date_add_months(today, months)
    assert base.parse_period(period, today) == (start, today)


def test_parse_period_ytd(today: datetime.date) -> None:
    start = datetime.date(today.year, 1, 1)
    assert base.parse_period("ytd", today) == (start, today)


def test_parse_period_400(today: datetime.date) -> None:
    with pytest.raises(exc.http.BadRequest):
        base.parse_period("", today)


def test_ctx_to_json(flask_app: flask.Flask) -> None:
    with flask_app.app_context():
        ctx: dict[str, object] = {"number": Decimal("1234.1234")}
        assert base.ctx_to_json(ctx) == '{"number":1234.12}'


def test_ctx_to_json_unknown_type(flask_app: flask.Flask) -> None:
    class Fake:
        pass

    with flask_app.app_context(), pytest.raises(TypeError):
        base.ctx_to_json({"fake": Fake()})


@pytest.mark.parametrize(
    "func",
    [
        base.validate_string,
        base.validate_real,
        base.validate_int,
    ],
    ids=conftest.id_func,
)
def test_validate_required(func: Callable[..., object]) -> None:
    assert func("", is_required=True) == "Required"


def test_validate_required_date(today: datetime.date) -> None:
    assert base.validate_date("", today, is_required=True) == "Required"


@pytest.mark.parametrize("s", ["", "abc"])
def test_validate_string(s: str) -> None:
    assert not base.validate_string(s)


def test_validate_string_short() -> None:
    assert base.validate_string("a", check_length=True) == "2 characters required"


def test_validate_string_duplicate(item: Item) -> None:
    err = base.validate_string(
        item.name,
        duplicate=base.DuplicateCheck(cls=Item, column=Item.name),
    )
    assert err == "Must be unique"


def test_validate_string_duplicate_self(item: Item) -> None:
    err = base.validate_string(
        item.name,
        duplicate=base.DuplicateCheck(
            cls=Item,
            column=Item.name,
            extra_wheres=[Item.id_ != item.id_],
        ),
    )
    assert not err


@pytest.mark.parametrize("s", ["", "2025-01-01"])
@pytest.mark.parametrize("max_future", [7, 0, None])
def test_validate_date(today: datetime.date, s: str, max_future: int | None) -> None:
    assert not base.validate_date(s, today, max_future=max_future)


@pytest.mark.parametrize(
    "func",
    [
        base.validate_real,
        base.validate_int,
    ],
    ids=conftest.id_func,
)
def test_validate_unable_to_parse(func: Callable[..., object]) -> None:
    assert func("a") == "Unable to parse"


def test_validate_unable_to_parse_date(today: datetime.date) -> None:
    assert base.validate_date("a", today) == "Unable to parse"


@pytest.mark.parametrize(
    ("max_future", "target"),
    [
        (7, "Only up to 7 days in advance"),
        (0, "Cannot be in advance"),
        (None, ""),
    ],
)
def test_validate_date_future(
    today: datetime.date,
    max_future: int | None,
    target: str,
) -> None:
    assert base.validate_date("2190-01-01", today, max_future=max_future) == target


@pytest.mark.parametrize(
    ("s", "target"),
    [
        ("123", "Expected xxx.xxx.xxx.xxx format"),
        ("256.256.256.256", "Could not parse"),
        ("192.168.1.2", ""),
        ("", ""),
    ],
)
def test_validate_ip(
    s: str,
    target: str,
) -> None:
    assert base.validate_ip(s) == target


@pytest.mark.parametrize(
    ("s", "target"),
    [
        ("123", "Expected xxx.xxx.xxx.xxx/xx format"),
        ("192.168.1.2", "Expected xxx.xxx.xxx.xxx/xx format"),
        ("192.168.1.2/1", ""),
        ("192.168.1.2/33", "'33' is not a valid netmask"),
        ("256.256.256.256/24", "Could not parse"),
        ("192.168.1.2/24", ""),
        ("", ""),
    ],
)
def test_validate_ip_cidr(
    s: str,
    target: str,
) -> None:
    assert base.validate_ip_cidr(s) == target


def test_validate_ip_cidr_local() -> None:
    assert base.validate_ip_cidr("10.0.0.0/1", is_local=True) == "Subnet is not local"


@pytest.mark.parametrize(
    ("s", "max_future", "target"),
    [
        ("a", 7, "Unable to parse"),
        ("", 7, "Date must not be empty"),
        ("2190-01-01", 7, "Only up to 7 days in advance"),
        ("2190-01-01", 0, "Cannot be in advance"),
        ("2190-01-01", None, None),
        ("2000-01-01", 7, None),
        ("2000-01-01", 0, None),
    ],
)
def test_parse_date(
    today: datetime.date,
    s: str,
    max_future: int | None,
    target: str | None,
) -> None:
    if target:
        with pytest.raises(ValueError, match=target):
            base.parse_date(s, today, max_future=max_future)
    else:
        date = base.parse_date(s, today, max_future=max_future)
        assert isinstance(date, datetime.date)


def test_validate_date_duplicate(today: datetime.date, item: Item) -> None:
    err = base.validate_date(
        item.date.isoformat(),
        today,
        duplicate=base.DuplicateCheck(cls=Item, column=Item.date_ord),
    )
    assert err == "Must be unique"


@pytest.mark.parametrize("s", ["0.1", "1.0", "-1*(-2)"])
@pytest.mark.parametrize("is_positive", [True, False])
def test_validate_real(s: str, is_positive: bool) -> None:
    assert not base.validate_real(s, is_positive=is_positive)


@pytest.mark.parametrize("s", ["0", "-1.0", "-1*2"])
def test_validate_real_not_positive(s: str) -> None:
    assert base.validate_real(s, is_positive=True) == "Must be positive"


@pytest.mark.parametrize("is_positive", [True, False])
def test_validate_int(is_positive: bool) -> None:
    assert not base.validate_int("1", is_positive=is_positive)


@pytest.mark.parametrize("s", ["0", "-1"])
def test_validate_int_not_positive(s: str) -> None:
    assert base.validate_int(s, is_positive=True) == "Must be positive"


def test_ctx_base_page(today: datetime.date) -> None:
    base.PAGES.clear()
    base.TEMPLATES.clear()
    templates = Path(flask_htmx_template.__file__).with_name("templates")

    ctx = base.ctx_base_page(templates, today, is_encrypted=False, debug=True)

    assert isinstance(ctx["nav_items"], list)
    for group in ctx["nav_items"]:
        assert isinstance(group, base.PageGroup)
        assert group.pages
        for name, d in group.pages.items():
            assert isinstance(d, base.Page)
            assert d
            assert name == name.capitalize()

    assert isinstance(ctx["icons"], str)
    assert ctx["icons"].count(",") > 10
    assert ctx["version"] == __version__
    assert ctx["current_year"] == today.year

    assert base.PAGES
    assert base.TEMPLATES


def test_dialog_swap_empty(
    flask_app: flask.Flask,
    valid_html: HTMLValidator,
) -> None:
    with flask_app.app_context():
        response = base.dialog_swap()

    data: bytes = response.data
    html = valid_html.clean(data.decode())
    assert valid_html(html)
    assert "snackbar" not in html
    assert "HX-Trigger" not in response.headers


def test_dialog_swap(
    flask_app: flask.Flask,
    valid_html: HTMLValidator,
    rand_str_generator: RandomStringGenerator,
) -> None:
    content = rand_str_generator()
    event = rand_str_generator()
    snackbar = rand_str_generator()

    with flask_app.app_context():
        response = base.dialog_swap(content, event, snackbar)

    data: bytes = response.data
    html = valid_html.clean(data.decode())
    assert valid_html(html)
    assert content in html
    assert "snackbar" in html
    assert snackbar in html
    assert event in response.headers["HX-Trigger"]


def test_error_str(
    valid_html: HTMLValidator,
    rand_str: str,
) -> None:
    html = base.error(rand_str)
    assert valid_html(html)
    assert rand_str in html


def test_error_empty_field(
    valid_html: HTMLValidator,
) -> None:
    try:
        Item.create()
    except exc.IntegrityError as e:
        html = base.error(e)
        assert valid_html(html)
        assert "Item name must not be empty" in html
    else:
        pytest.fail("did not create exception to test with")


def test_error_unique(
    item: Item,
    valid_html: HTMLValidator,
) -> None:
    try:
        Item.create(
            name=item.name,
            date_ord=item.date_ord,
        )
    except exc.IntegrityError as e:
        html = base.error(e)
        assert valid_html(html)
        assert "Item name must be unique" in html
    else:
        pytest.fail("did not create exception to test with")


def test_error_check(
    item: Item,
    valid_html: HTMLValidator,
) -> None:
    try:
        Item.query().update({"name": "a"})
    except exc.IntegrityError as e:
        html = base.error(e)
        assert valid_html(html)
        assert "Name must be at least 2 characters long" in html
    else:
        pytest.fail("did not create exception to test with")


def test_page(web_client: WebClient) -> None:
    result, headers = web_client.GET("common.page_dashboard", headers={})
    assert "<title>" in result
    assert "<html" in result
    assert "HX-Request" in headers["Vary"]


def test_page_hx(web_client: WebClient) -> None:
    result, headers = web_client.GET("common.page_dashboard")
    assert "<title>" in result
    assert "<html" not in result
    assert "HX-Request" in headers["Vary"]


def test_metrics(web_client: WebClient, item: Item) -> None:
    # Visit item page
    web_client.GET(("items.page", {"uri": item.uri}))
    web_client.GET("items.page_all")

    result, _ = web_client.GET(
        "prometheus_metrics",
        content_type="text/plain; version=0.0.4; charset=utf-8",
    )
    if isinstance(result, bytes):
        result = result.decode()
    assert "flask_exporter_info" in result
    assert "flask_htmx_template_info" in result
    assert "flask_http_request_duration_seconds_count" in result
    assert 'endpoint="items.page"' in result
    assert 'endpoint="items.page_all"' in result


def test_follow_links(web_client: WebClient) -> None:
    # Recursively click on every link checking that it is a valid link and valid
    # method
    visited: set[str] = set()

    # Save hx-delete for the end in case it does successfully delete something
    deletes: set[str] = set()

    def visit_all_links(url: str, method: str, *, hx: bool = False) -> None:
        request = f"{method} {url}"
        if request in visited or "validation" in url:
            return
        visited.add(request)
        response: werkzeug.test.TestResponse | None = None
        try:
            print(f"Visiting: {request}")
            response = web_client.raw_open(
                url,
                method=method,
                buffered=False,
                follow_redirects=False,
                headers={"HX-Request": "true"} if hx else None,
            )
            page = response.text
            assert response.status_code == base.HTTP_CODE_OK
            assert response.content_type == "text/html; charset=utf-8"

        except exc.http.BadRequest:
            # Better than a 404
            # Probably missing args/form
            return
        finally:
            if response is not None:
                response.close()
        hrefs = list(re.findall(r'href="([\w\d/\-]+)"', page))
        hx_gets = list(re.findall(r'hx-get="([\w\d/\-]+)"', page))
        hx_puts = list(re.findall(r'hx-put="([\w\d/\-]+)"', page))
        hx_posts = list(re.findall(r'hx-post="([\w\d/\-]+)"', page))
        hx_deletes = list(re.findall(r'hx-delete="([\w\d/\-]+)"', page))
        page = ""  # Clear page so --locals isn't too noisy

        for link in hrefs:
            visit_all_links(link, "GET")
        # With hx requests, add HX-Request header
        for link in hx_gets:
            visit_all_links(link, "GET", hx=True)
        for link in hx_puts:
            visit_all_links(link, "PUT", hx=True)
        for link in hx_posts:
            visit_all_links(link, "POST", hx=True)
        deletes.update(hx_deletes)

    visit_all_links("/", "GET")
    for link in deletes:
        visit_all_links(link, "DELETE", hx=True)


def test_change_redirect_no_changes() -> None:
    resp = flask.Response()
    result = base.change_redirect_to_htmx(resp)
    assert "HX-Redirect" not in result.headers


def test_change_redirect(web_client: WebClient) -> None:
    _, headers = web_client.GET("redirect")
    assert headers["HX-Redirect"] == "/"


def test_change_redirect_no_htmx(web_client: WebClient) -> None:
    _, headers = web_client.GET("redirect", headers={}, rc=base.HTTP_CODE_REDIRECT)
    assert "HX-Redirect" not in headers


@pytest.mark.parametrize(
    "path",
    sorted(
        Path(flask_htmx_template.__file__).with_name("templates").glob("**/*.jinja"),
    ),
    ids=conftest.id_func,
)
def test_template(valid_html: HTMLValidator, path: Path) -> None:
    buf = path.read_text("utf-8")

    re_jinja_template = re.compile(r'"\{\{ (.+?) \}\}"')
    for endpoint in re_jinja_template.findall(buf):
        assert '"' not in endpoint

    re_jinja = re.compile(r"(\{[{%#]).+?([#%}]\})")
    buf = valid_html.clean(re_jinja.sub("", buf))
    # Since each template is tested, it ensures any HX actions require local targets
    assert valid_html(buf, is_page="page" in path.name)
