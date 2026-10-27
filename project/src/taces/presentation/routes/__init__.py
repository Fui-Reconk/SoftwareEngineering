"""Blueprint registry.

API blueprints live under `/api`; page blueprints take no prefix. Adding a
blueprint here is the only place that changes when a new one appears, so page
work and API work never edit the same lines in `app.py`.
"""

from flask import Flask

from .auth import auth
from .health import health
from .pages import pages
from .courses import courses_admin
from .submissions import submissions
from .statistics import statistics


def register(app: Flask) -> None:
    app.register_blueprint(health, url_prefix="/api")
    app.register_blueprint(auth, url_prefix="/api")
    app.register_blueprint(pages)
    app.register_blueprint(courses_admin, url_prefix="/api")
    app.register_blueprint(submissions, url_prefix="/api")
    app.register_blueprint(statistics, url_prefix="/api")
