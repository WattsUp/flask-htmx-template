from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from flask_htmx_template import exceptions as exc
from flask_htmx_template.controllers.auth import debug

if TYPE_CHECKING:
    import flask


def test_debug_login_rejects_when_debug_is_disabled(flask_app: flask.Flask) -> None:
    flask_app.debug = False

    try:
        with flask_app.test_request_context(), pytest.raises(exc.http.Unauthorized):
            debug.debug_login()
    finally:
        flask_app.debug = True


@pytest.mark.parametrize(
    ("path", "form", "target"),
    [
        ("/?next=query-target", {}, "query-target"),
        ("/", {"next": "form-target"}, "form-target"),
        ("/", {}, "/"),
    ],
)
def test_debug_login_redirects_when_debug_is_enabled(
    flask_app: flask.Flask,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    form: dict[str, str],
    target: str,
) -> None:
    logged_in: list[tuple[object, bool]] = []

    def login_user(user: object, *, remember: bool) -> None:
        logged_in.append((user, remember))

    monkeypatch.setattr(debug.flask_login, "login_user", login_user)

    with flask_app.test_request_context(path, method="POST", data=form):
        response = debug.debug_login()

    assert response.status_code == 302
    assert response.location == target
    assert logged_in
    assert logged_in[0][1] is True
