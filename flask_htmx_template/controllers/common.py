"""Common component controllers."""

from __future__ import annotations

import re
from pathlib import Path

import flask

from flask_htmx_template import web, web_theme
from flask_htmx_template.controllers import auth, base
from flask_htmx_template.models.config import Config, ConfigKey

_SWATCH_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_COOKIE_SWATCH = "theme_swatch"
_COOKIE_MOOD = "theme_mood"
_COOKIE_MAX_AGE = 365 * 24 * 60 * 60


@auth.login_exempt
def theme_css() -> flask.Response:
    """GET /theme.css — Material Design 3 theme override for Tailwind CSS.

    Priority: query args > cookies > config values.

    Returns:
        CSS response with :root light variables and html.dark overrides

    """
    swatch = flask.request.args.get("swatch") or flask.request.cookies.get(
        _COOKIE_SWATCH,
    )
    mood_name = flask.request.args.get("mood") or flask.request.cookies.get(
        _COOKIE_MOOD,
    )

    if not swatch or not mood_name:
        with web.db.begin_session():
            if not swatch:
                swatch = Config.fetch(ConfigKey.WEB_THEME_SWATCH)
            if not mood_name:
                mood_name = Config.fetch(ConfigKey.WEB_THEME_MOOD)

    try:
        mood = web_theme.Mood[mood_name]
    except KeyError:
        mood = web_theme.DEFAULT_MOOD

    t = web_theme.generate(swatch, mood)

    def css_vars(colors: web_theme.Colors | web_theme.FixedColors) -> list[str]:
        return [f"  --color-{k.replace('_', '-')}: {v};" for k, v in colors.items()]

    lines: list[str] = ["@layer theme {", ":root {"]
    lines.extend(css_vars(t["fixed"]))
    lines.extend(css_vars(t["light"]))
    lines.extend(["}", "}", "", "@layer base {", "html:where(.dark, .dark *) {"])
    lines.extend(css_vars(t["dark"]))
    lines.extend(["}", "}"])
    css = "\n".join(lines) + "\n"

    return flask.Response(css, content_type="text/css; charset=utf-8")


@auth.login_exempt
def theme() -> str | flask.Response:
    """GET & PUT /h/theme — Theme editor dialog and cookie save.

    GET: Returns the theme editor dialog HTML.
    PUT: Validates and saves swatch+mood to cookies.

    Returns:
        Dialog HTML (GET) or dialog-close response with snackbar (PUT)

    """
    if flask.request.method == "GET":
        swatch = flask.request.cookies.get(_COOKIE_SWATCH)
        mood_name = flask.request.cookies.get(_COOKIE_MOOD)

        if not swatch or not mood_name:
            with web.db.begin_session():
                if not swatch:
                    swatch = Config.fetch(ConfigKey.WEB_THEME_SWATCH)
                if not mood_name:
                    mood_name = Config.fetch(ConfigKey.WEB_THEME_MOOD)

        if mood_name not in web_theme.Mood.__members__:
            mood_name = web_theme.DEFAULT_MOOD.name

        return flask.render_template(
            "shared/theme-edit.jinja",
            swatch=swatch,
            mood=mood_name,
            moods=list(web_theme.Mood),
        )

    # PUT — save to cookies
    swatch = flask.request.form.get("swatch", "").strip()
    mood_name = flask.request.form.get("mood", "").strip()

    if not _SWATCH_RE.match(swatch):
        return base.error("Invalid swatch color")
    if mood_name not in web_theme.Mood.__members__:
        return base.error("Invalid mood")

    response = base.dialog_swap(snackbar="Theme saved")
    response.set_cookie(
        _COOKIE_SWATCH,
        swatch,
        max_age=_COOKIE_MAX_AGE,
        samesite="Lax",
        path="/",
    )
    response.set_cookie(
        _COOKIE_MOOD,
        mood_name,
        max_age=_COOKIE_MAX_AGE,
        samesite="Lax",
        path="/",
    )
    return response


def page_dashboard() -> flask.Response:
    """GET home/dashboard page.

    Returns:
        string HTML response

    """
    return base.page("page.jinja", "Dashboard")


@auth.login_exempt
def page_status() -> str:
    """GET simple status for uptime page.

    Returns:
        string HTML response

    """
    return "ok"


def page_style_test() -> flask.Response:
    """GET CSS & HTML style test page.

    Returns:
        string HTML response

    """
    return base.page(
        "shared/style-test.jinja",
        "Style test",
    )


def favicon() -> flask.Response:
    """GET favicon file.

    Returns:
        string HTML response

    """
    path = Path(flask.current_app.static_folder or "static") / "img" / "favicon.ico"
    return flask.send_file(path)


ROUTES: base.Routes = {
    "/": (page_dashboard, ["GET"]),
    "/index": (page_dashboard, ["GET"]),
    "/favicon.ico": (favicon, ["GET"]),
    "/status": (page_status, ["GET"]),
    "/theme.css": (theme_css, ["GET"]),
    "/h/theme": (theme, ["GET", "PUT"]),
    "/d/style-test": (page_style_test, ["GET"]),
}
