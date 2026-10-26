"""Two error shapes: JSON under /api, an HTML page for everything a browser opens."""

from http import HTTPStatus
import sqlite3

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from taces.data.database import StorageError
from taces.business.errors import ServiceError

# Browser-facing pages. The pairs are (title, default message); both are plain
# sentences a teacher can act on, never an exception name.
HTML_PAGES = {
    403: ("没有权限", "这个操作需要更高的权限。"),
    404: ("没有这个页面", "地址可能打错了，或者页面已经移走了。"),
    405: ("这个地址不接受这种请求", "换一种请求方式再试。"),
    500: ("服务出了点问题", "已经记录，稍后再试。"),
    503: ("服务暂时不可用", "数据库可能还没初始化，稍后再试。"),
}


def _wants_html() -> bool:
    """The API keeps its JSON contract; anything else is a page a person opened."""
    return not request.path.startswith("/api")


def _html_error(status: int, message: str | None = None):
    title, fallback = HTML_PAGES.get(status, ("出了点问题", "稍后再试。"))
    return render_template(
        "error.html", code=status, title=title, message=message or fallback
    ), status


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
        if _wants_html():
            return _html_error(status)
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
        if _wants_html():
            return _html_error(503, "数据库尚未就绪，请先运行 init-db。")
        return jsonify(error={
            "code": "DATABASE_NOT_READY",
            "message": "数据库尚未就绪，请运行 init-db；已有旧库请运行 upgrade-db。",
        }), 503

    @app.errorhandler(sqlite3.Error)
    def handle_database_error(error: sqlite3.Error):
        app.logger.exception("Database operation failed")
        if _wants_html():
            return _html_error(503)
        return jsonify(error={
            "code": "DATABASE_UNAVAILABLE",
            "message": "数据库暂不可用，请稍后重试。",
        }), 503

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        app.logger.exception("Unhandled backend exception")
        if _wants_html():
            return _html_error(500)
        return jsonify(error={
            "code": "INTERNAL_SERVER_ERROR",
            "message": "服务器内部错误。",
        }), 500
