from __future__ import annotations

from typing import TYPE_CHECKING

from flask_htmx_template import web_theme
from flask_htmx_template.controllers.common import ctx

if TYPE_CHECKING:
    import flask


def test_ctx_theme_uses_requested_values(flask_app: flask.Flask) -> None:
    swatch = "#ff5500"
    mood = web_theme.Mood.VIBRANT

    with flask_app.app_context():
        selection = ctx.ctx_theme(swatch, mood.name)

    assert selection.swatch == swatch
    assert selection.mood == mood


def test_ctx_theme_uses_configured_mood_when_requested_mood_is_invalid(
    flask_app: flask.Flask,
) -> None:
    swatch = "#ff5500"

    with flask_app.app_context():
        selection = ctx.ctx_theme(swatch, "INVALID")

    assert selection.swatch == swatch
    assert selection.mood == web_theme.DEFAULT_MOOD


def test_ctx_theme_uses_configured_values_when_selection_is_missing(
    flask_app: flask.Flask,
) -> None:
    with flask_app.app_context():
        selection = ctx.ctx_theme()

    assert selection.swatch == web_theme.DEFAULT_SWATCH
    assert selection.mood == web_theme.DEFAULT_MOOD


def test_ctx_theme_fetches_only_swatch_when_mood_is_valid(
    flask_app: flask.Flask,
) -> None:
    mood = web_theme.Mood.VIBRANT

    with flask_app.app_context():
        selection = ctx.ctx_theme(mood_name=mood.name)

    assert selection.swatch == web_theme.DEFAULT_SWATCH
    assert selection.mood == mood
