"""HTTP composition root. Business and data modules remain framework-independent."""

from typing import Any, Mapping

from flask import Flask

from taces.config import load_config
from taces.business.auth.service import AuthService
from taces.data.database import Database
from taces.presentation.cli import register_cli
from taces.presentation.errors import register_error_handlers
from taces.presentation.routes import register as register_blueprints


def create_app(config: Mapping[str, Any] | None = None) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_mapping(load_config(config))
    app.json.ensure_ascii = False
    app.extensions["taces_database"] = Database(
        app.config["DATA_DIR"], timeout=app.config["SQLITE_TIMEOUT"]
    )
    app.extensions["taces_auth"] = AuthService(
        app.extensions["taces_database"], app.config["AUTH_SESSION_SECONDS"]
    )
    register_blueprints(app)
    register_cli(app)
    register_error_handlers(app)

    @app.after_request
    def response_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    return app
