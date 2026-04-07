"""Common component controllers."""

from __future__ import annotations

from pathlib import Path

import flask

from flask_htmx_template import web, web_theme
from flask_htmx_template.controllers import auth, base
from flask_htmx_template.models.config import Config, ConfigKey


def theme() -> flask.Response:
    """GET theme CSS override for Tailwind CSS.

    Returns:
        CSS response with Material Design 3 theme variables as :root and dark overrides

    """
    with web.db.begin_session():
        swatch = Config.fetch(ConfigKey.WEB_THEME_SWATCH)
        mood = Config.web_theme_mood()

    t = web_theme.generate(swatch, mood)

    def css_vars(colors: web_theme.Colors | web_theme.FixedColors) -> list[str]:
        return [f"  --color-{k.replace('_', '-')}: {v};" for k, v in colors.items()]

    lines: list[str] = [
        "@layer theme {",
        ":root {",
    ]
    lines.extend(css_vars(t["fixed"]))
    lines.extend(css_vars(t["light"]))
    lines.extend(["}", "}", "", "@layer base {", "html:where(.dark, .dark *) {"])
    lines.extend(css_vars(t["dark"]))
    lines.extend(["}", "}"])
    css = "\n".join(lines) + "\n"

    return flask.Response(css, content_type="text/css; charset=utf-8")


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
    "/theme.css": (theme, ["GET"]),
    "/d/style-test": (page_style_test, ["GET"]),
}
