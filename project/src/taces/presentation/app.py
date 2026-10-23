"""HTTP composition root. Business and data modules remain framework-independent."""

from typing import Any, Mapping

from flask import Flask

from taces.config import load_config
from taces.business.auth.service import AuthService
from taces.data.database import Database
from taces.presentation.cli import register_cli
from taces.presentation.errors import register_error_handlers
from taces.presentation.routes.health import health
from taces.presentation.routes.auth import auth


def create_app(config: Mapping[str, Any] | None = None) -> Flask:
    app = Flask(__name__, static_folder=None, template_folder=None)
    app.config.from_mapping(load_config(config))
    app.json.ensure_ascii = False
    app.extensions["taces_database"] = Database(
        app.config["DATA_DIR"], timeout=app.config["SQLITE_TIMEOUT"]
    )
    app.extensions["taces_auth"] = AuthService(
        app.extensions["taces_database"], app.config["AUTH_SESSION_SECONDS"]
    )
    app.register_blueprint(health, url_prefix="/api")
    app.register_blueprint(auth, url_prefix="/api")
    register_cli(app)
    register_error_handlers(app)

    @app.after_request
    def response_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    return app
