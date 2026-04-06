from __future__ import annotations

import io
from pathlib import Path

import flask
import setuptools

from flask_htmx_template import web_assets


def test_tailwindcss_filter() -> None:
    f = web_assets.TailwindCSSFilter()

    out = io.StringIO()
    f.output(io.StringIO(), out)
    buf = out.getvalue()
    assert "/*! tailwindcss" in buf
    assert "*,:after,:before" in buf


def test_jsmin_filter() -> None:
    in_ = io.StringIO("const abc = 123;  \nconst string = `${abc} = abc`")
    out = io.StringIO()

    f = web_assets.JSMinFilter()
    f.output(in_, out)

    buf = out.getvalue()
    target = "const abc=123;const string=`${abc} = abc`"
    assert buf == target


def test_build_bundles_debug() -> None:
    path_root = Path(web_assets.__file__).parent.resolve()
    app = flask.Flask(__name__, root_path=str(path_root))
    app.debug = True

    path_dist = path_root / "static" / "dist"
    path_dist_css = path_dist / "main.css"
    path_dist_js = path_dist / "main.js"
    path_dist_css.unlink(missing_ok=True)
    path_dist_js.unlink(missing_ok=True)

    web_assets.build_bundles(app, force=True)

    assert path_dist_css.exists()
    assert path_dist_js.exists()

    buf = path_dist_css.read_text("utf-8")
    assert "/*! tailwindcss" in buf
    # With debug, there should be spaces
    assert "*, :after, :before" in buf

    buf = path_dist_js.read_text("utf-8")
    # With debug, there should be comments
    assert "/**" in buf


def test_build_bundles_release() -> None:
    path_root = Path(web_assets.__file__).parent.resolve()
    app = flask.Flask(__name__, root_path=str(path_root))
    app.debug = False

    path_dist = path_root / "static" / "dist"
    path_dist_css = path_dist / "main.css"
    path_dist_js = path_dist / "main.js"
    path_dist_css.unlink(missing_ok=True)
    path_dist_js.unlink(missing_ok=True)

    web_assets.build_bundles(app, force=True)

    assert path_dist_css.exists()
    assert path_dist_js.exists()

    buf = path_dist_css.read_text("utf-8")
    assert "/*! tailwindcss" in buf
    assert "*,:after,:before" in buf

    buf = path_dist_js.read_text("utf-8")
    # Without debug, there should not be comments
    assert "/**" not in buf


def test_build_assets() -> None:
    path_root = Path(web_assets.__file__).parent.resolve()
    path_dist = path_root / "static" / "dist"
    path_dist_css = path_dist / "main.css"
    path_dist_js = path_dist / "main.js"

    path_dist_css.unlink(missing_ok=True)
    path_dist_js.unlink(missing_ok=True)

    dist = setuptools.Distribution()
    builder = web_assets.BuildAssets(dist)

    builder.packages = None
    builder.run()

    assert path_dist_css.exists()
    assert path_dist_js.exists()

    buf = path_dist_css.read_text("utf-8")
    assert "/*! tailwindcss" in buf
    assert "*,:after,:before" in buf

    buf = path_dist_js.read_text("utf-8")
    # Without debug, there should not be comments
    assert "/**" not in buf
