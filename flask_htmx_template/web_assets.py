"""Web assets manager."""

from __future__ import annotations

from pathlib import Path
from typing import override, TYPE_CHECKING

import flask
import flask_assets
import webassets.filter

try:
    from setuptools.command import build_py
except ImportError:
    build_py = None

try:
    import jsmin
    import pytailwindcss
except ImportError:
    pytailwindcss = None
    jsmin = None

if TYPE_CHECKING:
    import io

    import setuptools


class TailwindCSSFilter(webassets.filter.Filter):
    """webassets Filter for running tailwindcss over."""

    DEBUG = False

    @override
    def output(self, _in: io.StringIO, out: io.StringIO, **_: object) -> None:
        if pytailwindcss is None:
            raise NotImplementedError
        path_root = Path(__file__).parent.resolve()
        path_in = path_root / "static" / "src" / "css" / "main.css"

        args = [
            "-i",
            str(path_in),
            "--optimize" if self.DEBUG else "--minify",
        ]
        built_css = pytailwindcss.run(args, auto_install=True, version="v4.1.11")
        out.write(built_css)


class TailwindCSSFilterDebug(TailwindCSSFilter):
    """webassets Filter for running tailwindcss over."""

    DEBUG = True


class JSMinFilter(webassets.filter.Filter):
    """webassets Filter for running jsmin over."""

    @override
    def output(self, _in: io.StringIO, out: io.StringIO, **_: object) -> None:
        if jsmin is None:
            raise NotImplementedError
        # Add back tick to quote_chars for template strings
        minifier = jsmin.JavascriptMinify(quote_chars="'\"`")
        minifier.minify(_in, out)


def build_bundles(app: flask.Flask, *, force: bool = False) -> None:
    """Build asset bundles.

    Args:
        app: Flask app to build for
        force: True will force build bundles

    Raises:
        FileNotFoundError: If source does not exists and neither does dist
        FileNotFoundError: If source does not exists and debug == True

    """
    env_assets = flask_assets.Environment(app)
    stub_dist_css = "dist/main.css"
    stub_dist_js = "dist/main.js"

    path_static = Path(app.static_folder or "static").resolve()
    path_src = path_static / "src"
    path_dist_css = path_static / stub_dist_css
    path_dist_js = path_static / stub_dist_js
    if not path_src.exists():  # pragma: no cover
        # Too difficult to test for simple logic, skip tests
        if not path_dist_css.exists() or not path_dist_js.exists():
            msg = "Static source folder does not exists and neither does dist"
            raise FileNotFoundError(msg)
        if app.debug:
            msg = "Static source folder does not exists but running in debug"
            raise FileNotFoundError(msg)

        # Use dist directly
        env_assets.register("css", stub_dist_css)
        env_assets.register("js", stub_dist_js)
        return

    bundle_css = flask_assets.Bundle(
        "src/*.css",
        "src/**/*.css",
        output=stub_dist_css,
        filters=(
            None
            if pytailwindcss is None
            else (TailwindCSSFilterDebug if app.debug else TailwindCSSFilter,)
        ),
    )
    env_assets.register("css", bundle_css)
    bundle_css.build(force=force, disable_cache=force)

    bundle_js = flask_assets.Bundle(
        # top first
        "src/top.js",
        "src/*.js",
        "src/**/*.js",
        output=stub_dist_js,
        filters=(None if jsmin is None or app.debug else (JSMinFilter,)),
    )
    env_assets.register("js", bundle_js)
    bundle_js.build(force=force, disable_cache=force)


if build_py:

    class BuildAssets(build_py.build_py):
        """Build assets during build command."""

        @override
        def __init__(self, dist: setuptools.Distribution) -> None:
            if pytailwindcss is None or jsmin is None:  # pragma: no cover
                msg = "Filters not installed for BuildAssets"
                raise ImportError(msg)
            super().__init__(dist)

        def run(self) -> None:
            """Build assets during build command."""
            path_root = Path(__file__).parent.resolve()
            app = flask.Flask(__name__, root_path=str(path_root))
            app.debug = False
            build_bundles(app, force=True)
            return super().run()

else:  # pragma: no cover
    pass
