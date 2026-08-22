"""Common HTML controllers."""

from __future__ import annotations

from pathlib import Path

import flask

from flask_htmx_template import web, web_theme
from flask_htmx_template.controllers import base
from flask_htmx_template.controllers.auth import ctx as auth_ctx
from flask_htmx_template.controllers.common import ctx
from flask_htmx_template.models.config import Config, ConfigKey


@auth_ctx.login_exempt
def theme_css() -> flask.Response:
    """GET Material Design 3 theme CSS.

    Returns:
        CSS response for the selected theme.

    """
    swatch = flask.request.args.get("swatch") or flask.request.cookies.get(
        ctx.COOKIE_SWATCH,
    )
    mood_name = flask.request.args.get("mood") or flask.request.cookies.get(
        ctx.COOKIE_MOOD,
    )
    if not swatch or not mood_name:
        with web.db.begin_session():
            swatch = swatch or Config.fetch(ConfigKey.WEB_THEME_SWATCH)
            mood_name = mood_name or Config.fetch(ConfigKey.WEB_THEME_MOOD)
    try:
        mood = web_theme.Mood[mood_name]
    except KeyError:
        mood = web_theme.DEFAULT_MOOD
    theme = web_theme.generate(swatch, mood)

    def css_vars(colors: web_theme.Colors | web_theme.FixedColors) -> list[str]:
        """Build CSS custom-property declarations.

        Returns:
            CSS custom-property declarations.

        """
        return [
            f"  --color-{key.replace('_', '-')}: {value};"
            for key, value in colors.items()
        ]

    lines = ["@layer theme {", ":root {"]
    lines.extend(css_vars(theme["fixed"]))
    lines.extend(css_vars(theme["light"]))
    lines.extend(["}", "}", "", "@layer base {", "html:where(.dark, .dark *) {"])
    lines.extend(css_vars(theme["dark"]))
    lines.extend(["}", "}"])
    return flask.Response(
        "\n".join(lines) + "\n",
        content_type="text/css; charset=utf-8",
    )


@auth_ctx.login_exempt
def theme() -> str | flask.Response:
    """GET and PUT the theme editor dialog.

    Returns:
        Theme editor, validation error, or update response.

    """
    if flask.request.method == "GET":
        swatch = flask.request.cookies.get(ctx.COOKIE_SWATCH)
        mood_name = flask.request.cookies.get(ctx.COOKIE_MOOD)
        if not swatch or not mood_name:
            with web.db.begin_session():
                swatch = swatch or Config.fetch(ConfigKey.WEB_THEME_SWATCH)
                mood_name = mood_name or Config.fetch(ConfigKey.WEB_THEME_MOOD)
        if mood_name not in web_theme.Mood.__members__:
            mood_name = web_theme.DEFAULT_MOOD.name
        return flask.render_template(
            "shared/theme-edit.jinja",
            swatch=swatch,
            mood=mood_name,
            moods=list(web_theme.Mood),
        )

    swatch = flask.request.form.get("swatch", "").strip()
    mood_name = flask.request.form.get("mood", "").strip()
    if not ctx.SWATCH_RE.match(swatch):
        return base.error("Invalid swatch color")
    if mood_name not in web_theme.Mood.__members__:
        return base.error("Invalid mood")
    response = base.dialog_swap(snackbar="Theme saved")
    response.set_cookie(
        ctx.COOKIE_SWATCH,
        swatch,
        max_age=ctx.COOKIE_MAX_AGE,
        samesite="Lax",
        path="/",
    )
    response.set_cookie(
        ctx.COOKIE_MOOD,
        mood_name,
        max_age=ctx.COOKIE_MAX_AGE,
        samesite="Lax",
        path="/",
    )
    return response


def page_dashboard() -> flask.Response:
    """GET the dashboard page.

    Returns:
        Rendered dashboard page.

    """
    return base.page("page.jinja", "Dashboard")


@auth_ctx.login_exempt
def page_status() -> str:
    """GET the uptime status.

    Returns:
        Plain-text uptime status.

    """
    return "ok"


def page_style_test() -> flask.Response:
    """GET the CSS and HTML style test page.

    Returns:
        Rendered style-test page.

    """
    return base.page("shared/style-test.jinja", "Style test")


def favicon() -> flask.Response:
    """GET the favicon.

    Returns:
        Favicon file response.

    """
    path = Path(flask.current_app.static_folder or "static") / "img" / "favicon.ico"
    return flask.send_file(path)


ROUTE_PREFIX = "common"
ROUTES: base.Routes = {
    "/": (page_dashboard, ["GET"]),
    "/index": (page_dashboard, ["GET"]),
    "/favicon.ico": (favicon, ["GET"]),
    "/status": (page_status, ["GET"]),
    "/theme.css": (theme_css, ["GET"]),
    "/h/theme": (theme, ["GET", "PUT"]),
    "/d/style-test": (page_style_test, ["GET"]),
}
