from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from flask_htmx_template import exceptions as exc
from flask_htmx_template.controllers.auth import debug

if TYPE_CHECKING:
    import flask


def test_debug_login_rejects_when_debug_is_disabled(flask_app: flask.Flask) -> None:
    # Arrange
    flask_app.debug = False

    try:
        # Act
        with flask_app.test_request_context(), pytest.raises(exc.http.Unauthorized):
            debug.debug_login()
    finally:
        flask_app.debug = True
