from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple, overload, TYPE_CHECKING

import flask
import flask.sessions
import pytest

import flask_htmx_template
from flask_htmx_template.controllers import base
from flask_htmx_template.controllers.base import HTTP_CODE_OK, HTTP_CODE_REDIRECT

if TYPE_CHECKING:
    import contextlib
    import datetime
    from collections.abc import Generator

    import werkzeug.datastructures

    from flask_htmx_template.database import Database

JSONValue = str | float | int | bool | list["JSONValue"] | dict[str, "JSONValue"] | None
JSON = dict[str, JSONValue]


class TreeNode(NamedTuple):
    tag: str
    attributes: str
    i_start: int
    i_end: int

    parent: TreeNode | None
    children: list[TreeNode]

    def set_parent(self, parent: TreeNode) -> TreeNode:
        return TreeNode(
            self.tag,
            self.attributes,
            self.i_start,
            self.i_end,
            parent,
            self.children,
        )

    def has_hx_target(self) -> bool:
        if "hx-target" in self.attributes:
            return True
        if self.parent is None:
            return False
        return self.parent.has_hx_target()

    def has_valid_inner_html(self, inner_html: str) -> bool:
        assert (
            "placeholder" not in self.attributes or 'placeholder=""' in self.attributes
        )
        if self.tag == "script":
            attributes = self.attributes
            assert not inner_html or "onLoad" in inner_html or "src" in attributes
            return True
        if self.tag not in {"h1", "h2", "h3", "h4", "title"}:
            return True
        if inner_html in {
            "flask_htmx_template",
            "Bad Request",
            "400 Bad Request",
            "403 Forbidden",
        }:
            return True

        # Headers should use capital case
        # strip any inner element
        inner_html = inner_html.replace(".", "")
        words = inner_html.split(" ")
        target = " ".join(
            (w if w.upper() == w else (w.capitalize() if i == 0 else w.lower()))
            for i, w in enumerate(words)
        )
        assert inner_html == target
        return True

    def _has_valid_hx_attributes_dialog(self) -> bool:
        dialog = 'hx-push-url="#dialog"'
        explicit_false = 'hx-push-url="false"'
        assert dialog in self.attributes or explicit_false in self.attributes
        top = 'hx-swap="innerHTML show:#dialog:top"'
        btm = 'hx-swap="innerHTML show:#dialog:bottom"'
        assert top in self.attributes or btm in self.attributes
        return True

    def _has_valid_hx_attributes_main(self) -> bool:
        if "hx-trigger" in self.attributes and "click consume" not in self.attributes:
            # triggered updates don't move the page or push history
            assert "hx-push-url" not in self.attributes
            assert "hx-swap" not in self.attributes
        else:
            assert 'hx-push-url="true"' in self.attributes
            assert 'hx-swap="innerHTML show:window:top"' in self.attributes
        return True

    def has_valid_hx_attributes(self) -> bool:
        if 'hx-target="#dialog"' in self.attributes:
            return self._has_valid_hx_attributes_dialog()
        if 'hx-target="#main"' in self.attributes:
            return self._has_valid_hx_attributes_main()
        if not re.search(r"hx-(get|put|post|delete)", self.attributes):
            return True

        # There's an action, check there is a target in parent
        if not self.has_hx_target():
            pytest.fail(f"no hx-target: <{self.tag} {self.attributes}>")

        has_disabled_elt = (
            'hx-disabled-elt="this"' in self.attributes
            or 'hx-disabled-elt="find' in self.attributes
        )
        if 'hx-target="next error"' in self.attributes:
            # validation request, no disable needed
            assert not has_disabled_elt
            return True

        m = re.search(r'hx-trigger="([^"]+)"', self.attributes)
        triggers = [x.strip() for x in m.group(1).split(",")] if m else ["default"]
        if all(x.startswith(("load", "every")) for x in triggers):
            if has_disabled_elt:
                pytest.fail(f"has hx-disabled-elt: <{self.tag} {self.attributes}>")
            return True

        if not has_disabled_elt:
            pytest.fail(f"bad hx-disabled-elt: <{self.tag} {self.attributes}>")

        if 'type="date"' in self.attributes:
            # Better trigger than default
            assert 'hx-trigger="blur changed"' in self.attributes

        return True

    def has_preferred_attribute_order(self) -> bool:
        s = re.sub(r'="[^"]*"|=[^ ]*', "", self.attributes).strip(" /")
        if not s:
            return True
        attributes = s.split(" ")

        preferred_order = [
            "id",
            "class",
            "style",
            "rel",
            "title",
            "label",
            "href",
            "crossorigin",
            "charset",
            "lang",
            "defer",
            # Inputs
            "name",
            "required",
            "type",
            "value",
            "checked",
            "selected",
            "list",
            "min",
            "max",
            "rows",
            "placeholder",
            "autocomplete",
            "spellcheck",
            "enterkeyhint",
            "inputmode",
            "autofocus",
            # States
            "open",
            "disabled",
            "hidden",
            # SVG, img, & canvas
            "viewbox",
            "width",
            "height",
            "x",
            "y",
            "rx",
            "ry",
            # Data
            "content",
            "src",
            "alt",
            "data-method",
            "data-path",
            # HTMX Methods
            "hx-get",
            "hx-post",
            "hx-put",
            "hx-patch",
            "hx-delete",
            # HTMX Actions
            "hx-trigger",
            "hx-disabled-elt",
            "hx-indicator",
            # HTMX Destinations
            "hx-target",
            "hx-swap",
            "hx-sync",
            "hx-swap-oob",
            "hx-push-url",
            # HTMX Data
            "hx-include",
            "hx-encoding",
            "hx-validate",
            "hx-preserve",
            "hx-history-elt",
            # HTMX Events
            "hx-on::validation:failed",
            "hx-on::history-cache-miss",
            "hx-on::history-cache-miss-load",
            "hx-on::history-cache-miss-load-error",
            # In the order the events fire
            "hx-on::config-request",
            "hx-on::before-request",
            "hx-on::before-send",
            "hx-on::send-error",
            "hx-on::xhr:loadstart",
            "hx-on::xhr:progress",
            "hx-on::xhr:loadend",
            "hx-on::response-error",
            "hx-on::before-swap",
            "hx-on::after-swap",
            "hx-on::oob-before-swap",
            "hx-on::oob-after-swap",
            "hx-on::after-request",
            "hx-on::after-settle",
            # "confirm", # No confirm, use dialog confirm instead
            # JS event
            "onchange",
            "onclick",
            "oninput",
            "onkeydown",
            "onkeyup",
            "onsubmit",
        ]
        preferred_order = [s for s in preferred_order if s in attributes]

        assert attributes == preferred_order

        return True

    def has_valid_classes(self, inner_html: str) -> bool:
        if "class" not in self.attributes:
            return True

        re_bg = re.compile(r'bg-((?:primary|secondary|tertiary|error)[^ "]*)')
        for bg in re_bg.findall(self.attributes):
            bg: str
            assert (
                f"text-on-{bg.removesuffix('-dim')}" in self.attributes
                or not inner_html
            )

        return True


ResultType = dict[str, object] | str | bytes
Queries = dict[str, str] | dict[str, str | bool | list[str] | list[str | bool]]


class HTMLValidator:

    def __init__(self) -> None:
        self._icons: set[str] = set()

    def __call__(self, s: str, *, is_page: bool = False) -> bool:
        nodes: list[TreeNode] = [
            TreeNode(m.group(1), m.group(2), m.start(0), m.end(0), None, [])
            for m in re.finditer(r"<(/?\w+)([^<>]*)>", s)
        ]

        tree = TreeNode("__root__", "", 0, len(s), None, [])
        current_node = tree
        for tmp in nodes:
            if tmp.tag[0] == "/":
                close_node = tmp
                open_node = current_node
                assert open_node is not None
                assert open_node.tag == close_node.tag[1:]

                inner_html = s[open_node.i_end : close_node.i_start]
                assert open_node.has_valid_inner_html(inner_html)
                assert open_node.has_valid_classes(inner_html)

                if open_node.tag == "icon" and inner_html:
                    self._icons.add(inner_html)

                current_node = current_node.parent
                assert current_node is not None
                continue

            node = tmp.set_parent(current_node)
            current_node.children.append(node)

            assert node.has_valid_hx_attributes()
            assert node.has_preferred_attribute_order()

            if node.tag not in {"link", "meta", "path", "input", "hr", "rect", "img"}:
                # Tags without close tags
                current_node = node

        if is_page:
            assert current_node.children
            title_div = current_node.children[0]
            assert title_div.tag == "div"
            assert "class" not in title_div.attributes or "grid" in title_div.attributes

            assert title_div.children
            title = title_div.children[0]
            assert title.tag == "h1"
            assert "class" not in title.attributes

            for child in current_node.children:
                if child.tag == "h2":
                    assert "class" not in child.attributes

        # Got back up to the root element, hopefully
        assert current_node.tag in {"__root__", "html"}  # <html> might not be closed

        # Find all DOM ids and validate no duplicates
        ids: list[str] = re.findall(r'id="([^"]+)"', s)
        id_counts: dict[str, int] = defaultdict(int)
        for e_id in ids:
            id_counts[e_id] += 1
        duplicates = {e_id for e_id, count in id_counts.items() if count != 1}
        assert not duplicates

        return True

    @classmethod
    def clean(cls, html: str) -> str:
        html = "".join(html.split("\n"))
        html = re.sub(r" +", " ", html)
        html = re.sub(r" ?> ?", ">", html)
        return re.sub(r" ?< ?", "<", html)

    def check_icons(self, today: datetime.date) -> None:
        """Check all icons seen are in ctx_base."""
        templates = Path(flask_htmx_template.__file__).with_name("templates")

        ctx = base.ctx_base_page(templates, today, is_encrypted=False, debug=True)
        icons = set(ctx["icons"].split(","))
        # All icons seen should be in ctx_base
        # Might not have seen all so extra is okay
        assert self._icons <= icons


@pytest.fixture(scope="session")
def valid_html(today: datetime.date) -> Generator[HTMLValidator]:
    """Return a HTMLValidator.

    Yields:
        HTMLValidator

    """
    html_validator = HTMLValidator()
    yield html_validator

    html_validator.check_icons(today)


class WebClient:

    def __init__(self, app: flask.Flask, valid_html: HTMLValidator) -> None:
        self._flask_app = app
        self._client = self._flask_app.test_client()
        self.valid_html = valid_html

        self.raw_open = self._client.open

    def url_for(self, endpoint: str, **url_args: object) -> str:
        """Get the URL for an endpoint.

        Returns:
            URL

        """
        with self._flask_app.test_request_context():
            return flask.url_for(
                endpoint,
                _anchor=None,
                _method=None,
                _scheme=None,
                _external=False,
                **url_args,
            )

    def session(self) -> contextlib.AbstractContextManager[flask.sessions.SessionMixin]:
        """Get the client session.

        Returns:
            Client session

        """
        return self._client.session_transaction()

    def open_(
        self,
        method: str,
        endpoint: str | tuple[str, Queries],
        *,
        rc: int = HTTP_CODE_OK,
        content_type: str | None = None,
        **kwargs: object,
    ) -> tuple[str | bytes, werkzeug.datastructures.Headers]:
        """Run a test HTTP request.

        Args:
            method: HTTP method to use
            endpoint: Route endpoint to test or (endpoint, url_for kwargs)
            rc: Expected HTTP return code
            content_type: Content type to check for
            kwargs: Passed to client.get

        Returns:
            (response.text | response.data, headers)

        """
        if isinstance(endpoint, str):
            url_args = {}
        else:
            endpoint, url_args = endpoint
        url = self.url_for(endpoint, **url_args)
        content_type = content_type or "text/html; charset=utf-8"

        kwargs["method"] = method
        kwargs["headers"] = kwargs.get("headers", {"HX-Request": "true"})
        response = self._client.open(
            url,
            buffered=False,
            follow_redirects=False,
            **kwargs,
        )
        with response:
            response: werkzeug.test.TestResponse
            assert response.status_code == rc, response.data
            assert response.content_type == content_type

            if content_type == "text/html; charset=utf-8":
                html = self.valid_html.clean(response.text)
                if response.status_code != HTTP_CODE_REDIRECT:
                    # werkzeug redirect doesn't have close tags
                    assert self.valid_html(html)
                return html, response.headers
            d = response.data
            assert isinstance(d, bytes)
            return d, response.headers

    @overload
    def GET(
        self,
        endpoint: str | tuple[str, Queries],
        *,
        rc: int = HTTP_CODE_OK,
        content_type: str,
        **kwargs: object,
    ) -> tuple[bytes, werkzeug.datastructures.Headers]: ...
    @overload
    def GET(
        self,
        endpoint: str | tuple[str, Queries],
        *,
        rc: int = HTTP_CODE_OK,
        content_type: None = None,
        **kwargs: object,
    ) -> tuple[str, werkzeug.datastructures.Headers]: ...
    def GET(
        self,
        endpoint: str | tuple[str, Queries],
        *,
        rc: int = HTTP_CODE_OK,
        content_type: str | None = None,
        **kwargs: object,
    ) -> tuple[str | bytes, werkzeug.datastructures.Headers]:
        """GET an HTTP response.

        Args:
            endpoint: Route endpoint to test or (endpoint, url_for kwargs)
            rc: Expected HTTP return code
            content_type: Content type to check for
            kwargs: Passed to client.get

        Returns:
            (response.text, headers)

        """
        return self.open_("GET", endpoint, rc=rc, content_type=content_type, **kwargs)

    def GET_J(
        self,
        endpoint: str | tuple[str, Queries],
        *,
        rc: int = HTTP_CODE_OK,
        **kwargs: object,
    ) -> tuple[JSON, werkzeug.datastructures.Headers]:
        """GET a JSON response.

        Args:
            endpoint: Route endpoint to test or (endpoint, url_for kwargs)
            rc: Expected HTTP return code
            content_type: Content type to check for
            kwargs: Passed to client.get

        Returns:
            (response.json, headers)

        """
        s, headers = self.open_(
            "GET",
            endpoint,
            rc=rc,
            content_type="application/json",
            **kwargs,
        )
        return json.loads(s), headers

    @overload
    def PUT(
        self,
        endpoint: str | tuple[str, Queries],
        *,
        rc: int,
        content_type: str,
        **kwargs: object,
    ) -> tuple[bytes, werkzeug.datastructures.Headers]: ...
    @overload
    def PUT(
        self,
        endpoint: str | tuple[str, Queries],
        *,
        rc: int = HTTP_CODE_OK,
        content_type: None = None,
        **kwargs: object,
    ) -> tuple[str, werkzeug.datastructures.Headers]: ...
    def PUT(
        self,
        endpoint: str | tuple[str, Queries],
        *,
        rc: int = HTTP_CODE_OK,
        content_type: str | None = None,
        **kwargs: object,
    ) -> tuple[str | bytes, werkzeug.datastructures.Headers]:
        """PUT an HTTP response.

        Args:
            endpoint: Route endpoint to test or (endpoint, url_for kwargs)
            rc: Expected HTTP return code
            content_type: Content type to check for
            kwargs: Passed to client.get

        Returns:
            (response.text, headers)

        """
        return self.open_("PUT", endpoint, rc=rc, content_type=content_type, **kwargs)

    def PUT_J(
        self,
        endpoint: str | tuple[str, Queries],
        *,
        rc: int = HTTP_CODE_OK,
        **kwargs: object,
    ) -> tuple[JSON, werkzeug.datastructures.Headers]:
        """PUT a JSON response.

        Args:
            endpoint: Route endpoint to test or (endpoint, url_for kwargs)
            rc: Expected HTTP return code
            content_type: Content type to check for
            kwargs: Passed to client.get

        Returns:
            (response.json, headers)

        """
        s, headers = self.open_(
            "PUT",
            endpoint,
            rc=rc,
            content_type="application/json",
            **kwargs,
        )
        return json.loads(s), headers

    @overload
    def POST(
        self,
        endpoint: str | tuple[str, Queries],
        *,
        rc: int,
        content_type: str,
        **kwargs: object,
    ) -> tuple[bytes, werkzeug.datastructures.Headers]: ...
    @overload
    def POST(
        self,
        endpoint: str | tuple[str, Queries],
        *,
        rc: int = HTTP_CODE_OK,
        content_type: None = None,
        **kwargs: object,
    ) -> tuple[str, werkzeug.datastructures.Headers]: ...
    def POST(
        self,
        endpoint: str | tuple[str, Queries],
        *,
        rc: int = HTTP_CODE_OK,
        content_type: str | None = None,
        **kwargs: object,
    ) -> tuple[str | bytes, werkzeug.datastructures.Headers]:
        """POST an HTTP response.

        Args:
            endpoint: Route endpoint to test or (endpoint, url_for kwargs)
            rc: Expected HTTP return code
            content_type: Content type to check for
            kwargs: Passed to client.get

        Returns:
            (response.text, headers)

        """
        return self.open_("POST", endpoint, rc=rc, content_type=content_type, **kwargs)

    def POST_J(
        self,
        endpoint: str | tuple[str, Queries],
        *,
        rc: int = HTTP_CODE_OK,
        **kwargs: object,
    ) -> tuple[JSON, werkzeug.datastructures.Headers]:
        """POST a JSON response.

        Args:
            endpoint: Route endpoint to test or (endpoint, url_for kwargs)
            rc: Expected HTTP return code
            content_type: Content type to check for
            kwargs: Passed to client.get

        Returns:
            (response.json, headers)

        """
        s, headers = self.open_(
            "POST",
            endpoint,
            rc=rc,
            content_type="application/json",
            **kwargs,
        )
        return json.loads(s), headers

    @overload
    def DELETE(
        self,
        endpoint: str | tuple[str, Queries],
        *,
        rc: int,
        content_type: str,
        **kwargs: object,
    ) -> tuple[bytes, werkzeug.datastructures.Headers]: ...
    @overload
    def DELETE(
        self,
        endpoint: str | tuple[str, Queries],
        *,
        rc: int = HTTP_CODE_OK,
        content_type: None = None,
        **kwargs: object,
    ) -> tuple[str, werkzeug.datastructures.Headers]: ...
    def DELETE(
        self,
        endpoint: str | tuple[str, Queries],
        *,
        rc: int = HTTP_CODE_OK,
        content_type: str | None = None,
        **kwargs: object,
    ) -> tuple[str | bytes, werkzeug.datastructures.Headers]:
        """DELETE an HTTP response.

        Args:
            endpoint: Route endpoint to test or (endpoint, url_for kwargs)
            rc: Expected HTTP return code
            content_type: Content type to check for
            kwargs: Passed to client.get

        Returns:
            (response.text, headers)

        """
        return self.open_(
            "DELETE",
            endpoint,
            rc=rc,
            content_type=content_type,
            **kwargs,
        )

    def DELETE_J(
        self,
        endpoint: str | tuple[str, Queries],
        *,
        rc: int = HTTP_CODE_OK,
        **kwargs: object,
    ) -> tuple[JSON, werkzeug.datastructures.Headers]:
        """DELETE a JSON response.

        Args:
            endpoint: Route endpoint to test or (endpoint, url_for kwargs)
            rc: Expected HTTP return code
            content_type: Content type to check for
            kwargs: Passed to client.get

        Returns:
            (response.json, headers)

        """
        s, headers = self.open_(
            "DELETE",
            endpoint,
            rc=rc,
            content_type="application/json",
            **kwargs,
        )
        return json.loads(s), headers


@pytest.fixture
def web_client(flask_app: flask.Flask, valid_html: HTMLValidator) -> WebClient:
    """Return a WebClient.

    Returns:
        WebClient

    """
    return WebClient(flask_app, valid_html)


class WebClientEncrypted(WebClient):

    def __init__(
        self,
        app: flask.Flask,
        valid_html: HTMLValidator,
        web_key: str,
    ) -> None:
        super().__init__(app, valid_html)
        self._web_key = web_key

    def login(self) -> None:
        """Login user."""
        self.POST("auth.login", data={"password": self._web_key})


@pytest.fixture
def web_client_encrypted(
    flask_app_encrypted: flask.Flask,
    valid_html: HTMLValidator,
    empty_database_encrypted: tuple[Database, str],
) -> WebClientEncrypted:
    """Return a WebClient.

    Returns:
        WebClient

    """
    _, key = empty_database_encrypted
    # web key and database key are the same
    return WebClientEncrypted(flask_app_encrypted, valid_html, key)
