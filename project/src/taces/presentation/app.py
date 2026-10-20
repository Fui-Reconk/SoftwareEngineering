"""HTTP composition root. Business and data modules remain framework-independent."""

from typing import Any, Mapping

from flask import Flask

from taces.config import load_config
from taces.data.database import Database
from taces.presentation.cli import register_cli
from taces.presentation.errors import register_error_handlers
from taces.presentation.routes.health import health


def create_app(config: Mapping[str, Any] | None = None) -> Flask:
    app = Flask(__name__, static_folder=None, template_folder=None)
    app.config.from_mapping(load_config(config))
    app.json.ensure_ascii = False
    app.extensions["taces_database"] = Database(
        app.config["DATA_DIR"], timeout=app.config["SQLITE_TIMEOUT"]
    )
    app.register_blueprint(health, url_prefix="/api")
    register_cli(app)
    register_error_handlers(app)

    @app.after_request
    def response_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    return app
