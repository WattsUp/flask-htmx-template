"""Flask extension."""

from __future__ import annotations

import datetime
import functools
import json
import logging
import os
from decimal import Decimal
from pathlib import Path
from typing import Any, cast, override, TYPE_CHECKING

import flask
import flask_login
import prometheus_client
import prometheus_flask_exporter
import prometheus_flask_exporter.multiprocess
from werkzeug.exceptions import HTTPException

from flask_htmx_template import controllers
from flask_htmx_template import exceptions as exc
from flask_htmx_template import sql, utils, web_assets
from flask_htmx_template.controllers import base
from flask_htmx_template.controllers.api_docs import ctx as api_docs_ctx
from flask_htmx_template.controllers.api_docs import html as api_docs_html
from flask_htmx_template.controllers.api_docs import json as api_docs_json
from flask_htmx_template.controllers.auth import bearer as auth_bearer
from flask_htmx_template.controllers.auth import ctx as auth_ctx
from flask_htmx_template.controllers.auth import debug as auth_debug
from flask_htmx_template.controllers.auth import html as auth_html
from flask_htmx_template.controllers.common import html as common_html
from flask_htmx_template.controllers.items import html as items_html
from flask_htmx_template.controllers.items import json as items_json
from flask_htmx_template.database import PostgresDatabase, SQLiteDatabase
from flask_htmx_template.models.config import Config, ConfigKey
from flask_htmx_template.version import __version__

if TYPE_CHECKING:
    import jinja2
    import werkzeug

    from flask_htmx_template.database import Database


class _Request(flask.Request):
    """Flask Request that always raises descriptive JSON parse errors.

    NOTE: Flask's on_json_loading_failed() swallows the original ValueError
    and re-raises a bare BadRequest() when app.debug is False, losing the
    decode message. We skip Flask's wrapper and use werkzeug's implementation
    directly so the error text is always preserved.
    """

    @override
    def on_json_loading_failed(self, e: ValueError | None) -> Any:
        if e is not None:
            msg = f"Failed to decode JSON object: {e}"
            raise exc.http.BadRequest(msg)
        msg = (
            "Did not attempt to load JSON data because the request"
            " Content-Type was not 'application/json'."
        )
        raise exc.http.UnsupportedMediaType(msg)


class JSONEncoder(flask.json.provider.JSONProvider):
    """Custom JSON encoder."""

    @override
    def dumps(self, obj: object, **kwargs: object) -> str:
        # NOTE: Flask also uses this provider to encode test request bodies before
        # it creates a request context.
        if flask.has_request_context():
            indent = flask.request.headers.get("X-Indent", type=int)
            if indent is not None:
                kwargs["indent"] = min(indent, 8)
        return json.dumps(utils.json_mutate(obj), **cast("Any", kwargs))

    @override
    def loads(self, s: str | bytes, **kwargs: object) -> object:
        return json.loads(s, **cast("Any", kwargs))


class FlaskExtension:
    """flask extension."""

    def init_app(self, app: flask.Flask) -> None:
        """Initialize app with extension.

        Args:
            app: Flask app to initialize

        """
        config = flask.Config(app.root_path)  # flask_htmx_template: ignore[mixins]
        config.from_prefixed_env("DB")
        self._db = self._open_db(config)

        self._original_url_for = app.url_for
        app.url_for = self.url_for

        self._add_routes(app)
        api_docs_ctx.init_docs(app)
        web_assets.build_bundles(app)
        self._init_auth(app, self._db)
        self._init_jinja_env(app.jinja_env)
        self._init_metrics(app)

        app.context_processor(base.ctx_base)

        app.request_class = _Request
        app.json_provider_class = JSONEncoder
        app.json = JSONEncoder(app)

        app.register_error_handler(HTTPException, _handle_http_exception)

    @classmethod
    def _open_db(cls, config: dict[str, object]) -> Database:
        s = config.get("PATH", "~/.flask-htmx-template/database.db")
        if not isinstance(s, str):
            raise TypeError

        if sql.is_postgres_url(s):
            return PostgresDatabase(s)

        path = Path(s).expanduser().absolute()

        return SQLiteDatabase(path)

    @classmethod
    def _add_routes(cls, app: flask.Flask) -> None:
        modules = [
            api_docs_html,
            api_docs_json,
            auth_html,
            auth_debug,
            common_html,
            items_html,
            items_json,
        ]
        n_trim = len(controllers.__name__) + 1
        urls: set[str] = set()
        for m in modules:
            routes: base.Routes = m.ROUTES
            for url, (view_func, methods) in routes.items():
                route_prefix = getattr(m, "ROUTE_PREFIX", m.__name__[n_trim:])
                endpoint = f"{route_prefix}.{view_func.__name__}"
                if url in urls:  # pragma: no cover
                    raise exc.DuplicateURLError(url, endpoint)
                if url.startswith("/d/") and not app.debug:
                    continue
                urls.add(url)
                app.add_url_rule(url, endpoint, view_func, methods=methods)

    @classmethod
    def _init_auth(cls, app: flask.Flask, d: Database) -> None:
        with d.begin_session():
            secret_key = Config.fetch(ConfigKey.SECRET_KEY)

        app.secret_key = secret_key
        config: dict[str, object] = app.config
        config["SESSION_COOKIE_SECURE"] = True
        config["SESSION_COOKIE_HTTPONLY"] = True
        config["SESSION_COOKIE_SAMESITE"] = "Lax"
        config["REMEMBER_COOKIE_SECURE"] = True
        config["REMEMBER_COOKIE_HTTPONLY"] = True
        config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
        config["REMEMBER_COOKIE_DURATION"] = datetime.timedelta(days=28)
        app.after_request(base.change_redirect_to_htmx)
        app.after_request(base.append_json_newline)

        login_manager = flask_login.LoginManager()
        login_manager.init_app(app)
        login_manager.user_loader(auth_ctx.get_user)
        login_manager.request_loader(auth_bearer.load_user)
        login_manager.login_view = "auth.page_login"

        app.before_request(auth_ctx.default_login_required)

    @classmethod
    def _init_jinja_env(cls, env: jinja2.Environment) -> None:
        env.filters["seconds"] = utils.format_seconds
        env.filters["days"] = utils.format_days
        env.filters["days_abv"] = functools.partial(
            utils.format_days,
            labels=["days", "wks", "mos", "yrs"],
        )
        env.filters["comma"] = lambda x: f"{x:,.2f}"
        env.filters["qty"] = lambda x: f"{x:,.6f}"
        env.filters["tojson"] = base.ctx_to_json
        env.filters["input_value"] = lambda x: str(x or "").rstrip("0").rstrip(".")

        def percent(x: Decimal | float | object) -> str:
            if not isinstance(x, Decimal | float):
                raise TypeError
            return f"{x * 100:5.2f}%"

        env.filters["percent"] = percent

    @classmethod
    def _init_metrics(cls, app: flask.Flask) -> None:
        multiproc = "PROMETHEUS_MULTIPROC_DIR" in os.environ
        metrics_class = (
            prometheus_flask_exporter.multiprocess.GunicornPrometheusMetrics
            if multiproc
            else prometheus_flask_exporter.PrometheusMetrics
        )
        metrics = metrics_class(
            app,
            path="/metrics",
            metrics_decorator=auth_ctx.login_exempt,
            excluded_paths=["/static", "/metrics", "/status"],
            group_by="endpoint",
            registry=(
                None
                if multiproc
                else prometheus_client.CollectorRegistry(auto_describe=True)
            ),
        )
        metrics.info(
            "flask_htmx_template_info",
            "flask-htmx-template info",
            version=__version__,
        )
        app.extensions["flask_htmx_template_metrics"] = metrics

    def url_for(
        self,
        /,
        endpoint: str,
        *,
        _anchor: str | None = None,
        _method: str | None = None,
        _scheme: str | None = None,
        _external: bool | None = None,
        **values: object,
    ) -> str:
        """Override flask.url_for.

        Returns:
            URL with better arg formatting

        """
        # Change snake case to kebab case
        # Change bools to "" if True, omit if False
        values = {
            k.replace("_", "-"): "" if isinstance(v, bool) else v
            for k, v in values.items()
            if not isinstance(v, str | bool | None) or v
        }
        return self._original_url_for(
            endpoint,
            _anchor=_anchor,
            _method=_method,
            _scheme=_scheme,
            _external=_external,
            **values,
        )

    @property
    def db(self) -> Database:
        """Database flask is serving."""
        return self._db


def _handle_http_exception(
    e: HTTPException,
) -> werkzeug.Response | tuple[base.ErrorJSON, int]:
    if flask.request.path.startswith("/j/"):
        return {"errors": [e.description or str(e)]}, e.code or 500
    return e.get_response()


ext = FlaskExtension()
db: Database


def create_app() -> flask.Flask:
    """Create flask app.

    Returns:
        Flask App

    """
    app = flask.Flask(__name__)

    logging.getLogger("werkzeug").setLevel(
        logging.DEBUG if app.debug else logging.WARNING,
    )
    utils.init_logger(debug=app.debug)

    ext.init_app(app)
    return app


def __getattr__(name: str) -> object:
    if name == "db":
        return ext.db
    msg = f"module {__name__} has no attribute {name}"
    raise AttributeError(msg)
