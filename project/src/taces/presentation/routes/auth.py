"""JSON staff API; authentication and permissions remain in business services."""

from functools import wraps
import hmac

from flask import Blueprint, current_app, jsonify, request

from taces.business.auth.service import csrf_token, invalid
from taces.business.errors import ServiceError


auth = Blueprint("auth", __name__)
COOKIE_NAME = "taces_session"


def service():
    return current_app.extensions["taces_auth"]


def token():
    return request.cookies.get(COOKIE_NAME)


def check_origin():
    origin = request.headers.get("Origin")
    if origin is not None and origin != request.host_url.rstrip("/"):
        raise ServiceError(403, "CSRF_REJECTED", "请求来源校验失败。")


def protected(*, write=False):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            service().current(token())
            if write:
                try:
                    check_origin()
                    supplied = request.headers.get("X-CSRF-Token", "")
                    if not supplied.isascii() or not hmac.compare_digest(supplied, csrf_token(token())):
                        raise ServiceError(403, "CSRF_REJECTED", "请求校验失败，请重新获取 CSRF token。")
                except ServiceError:
                    service().record_denial(token(), "csrf")
                    raise
            return function(*args, **kwargs)
        return wrapped
    return decorate


def payload(required, optional=()):
    if not request.is_json:
        raise ServiceError(415, "UNSUPPORTED_MEDIA_TYPE", "请使用 application/json。")
    data = request.get_json()
    if not isinstance(data, dict) or set(data) - set(required) - set(optional) or set(required) - set(data):
        raise invalid()
    return data


def clear_cookie(response):
    response.delete_cookie(COOKIE_NAME, path="/api", httponly=True,
                           secure=current_app.config["AUTH_COOKIE_SECURE"], samesite="Strict")
    return response


@auth.post("/auth/login")
def login():
    check_origin()
    if request.headers.get("X-TACES-Request") != "1":
        raise ServiceError(403, "CSRF_REJECTED", "登录请求须携带 X-TACES-Request: 1。")
    data = payload({"username", "password"})
    raw_token, result = service().login(data["username"], data["password"], token())
    response = jsonify(data=result)
    response.set_cookie(COOKIE_NAME, raw_token, path="/api", httponly=True, samesite="Strict",
                        secure=current_app.config["AUTH_COOKIE_SECURE"],
                        max_age=current_app.config["AUTH_SESSION_SECONDS"])
    return response


@auth.get("/auth/me")
def me():
    return jsonify(data=service().current(token()))


@auth.post("/auth/logout")
@protected(write=True)
def logout():
    service().logout(token())
    return clear_cookie(jsonify(data={"logged_out": True}))


@auth.post("/auth/password")
@protected(write=True)
def password():
    data = payload({"current_password", "new_password"})
    service().change_password(token(), data["current_password"], data["new_password"])
    return clear_cookie(jsonify(data={"login_required": True}))


@auth.get("/admin/accounts")
@protected()
def accounts():
    if set(request.args) - {"limit", "offset"}:
        raise invalid()
    limit, offset = request.args.get("limit", "100"), request.args.get("offset", "0")
    if not (limit.isascii() and limit.isdecimal() and offset.isascii() and offset.isdecimal()):
        raise invalid()
    # Bound integer parsing and the SQL offset to avoid malformed huge values.
    if len(limit) > 3 or len(offset) > 9 or not 1 <= int(limit) <= 100:
        raise invalid()
    return jsonify(data={"accounts": service().list_accounts(token(), int(limit), int(offset))})


@auth.post("/admin/accounts")
@protected(write=True)
def create_account():
    data = payload({"username", "password", "role"})
    account = service().create_account(token(), data["username"], data["password"], data["role"])
    return jsonify(data={"account": account}), 201


@auth.patch("/admin/accounts/<user_id>")
@protected(write=True)
def update_account(user_id):
    data = payload(set(), {"role", "is_active", "password"})
    result = service().update_account(token(), user_id, data)
    response = jsonify(data={"account": result})
    # The service revokes all of the target account's sessions, including this one.
    try:
        service().current(token())
    except ServiceError as error:
        if error.status != 401:
            raise
        clear_cookie(response)
    return response


@auth.get("/courses")
def courses():
    return jsonify(data={"courses": service().list_courses(token())})


@auth.get("/courses/<course_id>")
def course(course_id):
    return jsonify(data={"course": service().get_course(token(), course_id)})
