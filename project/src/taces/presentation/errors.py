"""One JSON error shape, without internal exception messages in HTTP responses."""

from http import HTTPStatus
import sqlite3

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from taces.data.database import StorageError
from taces.business.errors import ServiceError


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ServiceError)
    def handle_service_error(error: ServiceError):
        response = jsonify(error={"code": error.code, "message": error.message})
        response.status_code = error.status
        if error.status == 429:
            response.headers["Retry-After"] = "900"
        return response

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        status = error.code or 500
        response = error.get_response()
        # Keep status-specific headers, including Allow on 405 responses.
        response.data = app.json.dumps({
            "error": {
                "code": HTTPStatus(status).name,
                "message": HTTPStatus(status).phrase,
            }
        })
        response.content_type = "application/json"
        return response

    @app.errorhandler(StorageError)
    def handle_storage_error(error: StorageError):
        app.logger.warning("Database is not ready: %s", error)
        return jsonify(error={
            "code": "DATABASE_NOT_READY",
            "message": "数据库尚未就绪，请运行 init-db；已有旧库请运行 upgrade-db。",
        }), 503

    @app.errorhandler(sqlite3.Error)
    def handle_database_error(error: sqlite3.Error):
        app.logger.exception("Database operation failed")
        return jsonify(error={
            "code": "DATABASE_UNAVAILABLE",
            "message": "数据库暂不可用，请稍后重试。",
        }), 503

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        app.logger.exception("Unhandled backend exception")
        return jsonify(error={
            "code": "INTERNAL_SERVER_ERROR",
            "message": "服务器内部错误。",
        }), 500
