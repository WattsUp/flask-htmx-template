from __future__ import annotations

from typing import TYPE_CHECKING

from flask_htmx_template import web_theme
from flask_htmx_template.controllers.common import ctx

if TYPE_CHECKING:
    import flask


def test_ctx_theme_uses_requested_values(flask_app: flask.Flask) -> None:
    # Arrange
    swatch = "#ff5500"
    mood = web_theme.Mood.VIBRANT

    # Act
    with flask_app.app_context():
        selection = ctx.ctx_theme(swatch, mood.name)

    # Assert
    assert selection.swatch == swatch
    assert selection.mood == mood


def test_ctx_theme_uses_configured_mood_when_requested_mood_is_invalid(
    flask_app: flask.Flask,
) -> None:
    # Arrange
    swatch = "#ff5500"

    # Act
    with flask_app.app_context():
        selection = ctx.ctx_theme(swatch, "INVALID")

    # Assert
    assert selection.swatch == swatch
    assert selection.mood == web_theme.DEFAULT_MOOD
