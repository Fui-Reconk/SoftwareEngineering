import sqlite3

import pytest
from werkzeug.exceptions import BadRequest


def test_liveness_and_readiness_are_separate(app):
    client = app.test_client()
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json == {"data": {"service": "taces", "status": "ok"}}
    ready = client.get("/api/ready")
    assert ready.status_code == 503
    assert ready.json["error"]["code"] == "DATABASE_NOT_READY"
    assert str(app.config["DATA_DIR"]) not in ready.get_data(as_text=True)
    assert not app.config["DATA_DIR"].exists()


def test_readiness_after_initialization(app, database):
    response = app.test_client().get("/api/ready")
    assert response.status_code == 200
    assert response.json == {"data": {"service": "taces", "status": "ready"}}


def test_missing_table_is_not_reported_as_ready(app, database):
    connection = sqlite3.connect(database.paths.identity)
    connection.execute("DROP TABLE student")
    connection.close()
    assert app.test_client().get("/api/ready").status_code == 503


def test_missing_route_returns_json(app):
    response = app.test_client().get("/not-a-route")
    assert response.status_code == 404
    assert response.json["error"]["code"] == "NOT_FOUND"


def test_method_not_allowed_keeps_allow_header(app):
    response = app.test_client().post("/api/health")
    assert response.status_code == 405
    assert response.json["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert "GET" in response.headers["Allow"]


@pytest.mark.parametrize("error,status,code", [
    (RuntimeError("secret database path"), 500, "INTERNAL_SERVER_ERROR"),
    (sqlite3.OperationalError("secret database path"), 503, "DATABASE_UNAVAILABLE"),
    (BadRequest("secret database path"), 400, "BAD_REQUEST"),
])
def test_error_responses_hide_exception_details(app, error, status, code):
    @app.get("/test-failure")
    def fail():
        raise error

    response = app.test_client().get("/test-failure")
    assert response.status_code == status
    assert response.json["error"]["code"] == code
    assert "secret database path" not in response.get_data(as_text=True)
    assert "Traceback" not in response.get_data(as_text=True)


def test_response_headers_apply_to_success_and_error(app):
    for path in ("/api/health", "/missing", "/api/ready"):
        response = app.test_client().get(path)
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_init_command_is_repeatable(app):
    runner = app.test_cli_runner()
    for _ in range(2):
        result = runner.invoke(args=["init-db"])
        assert result.exit_code == 0, result.output
    assert app.test_client().get("/api/ready").status_code == 200


def test_init_command_reports_incompatible_database(app, database):
    connection = sqlite3.connect(database.paths.metadata)
    connection.execute("PRAGMA user_version=99")
    connection.close()
    result = app.test_cli_runner().invoke(args=["init-db"])
    assert result.exit_code != 0
    assert "Error:" in result.output
