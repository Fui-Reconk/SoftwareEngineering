"""Administrator configuration and self-contained auditor queries."""

from decimal import Decimal, DecimalException

from flask import Blueprint, current_app, jsonify, request
from werkzeug.exceptions import BadRequest

from taces.business.audit.service import AuditService
from taces.business.config.service import ConfigService
from taces.business.errors import ServiceError
from taces.business.auth.service import invalid
from .auth import protected, service, token


governance = Blueprint("governance", __name__)


def database():
    return current_app.extensions["taces_database"]


def decimal_literal(value):
    try:
        return Decimal(value)
    except DecimalException:
        # Preserve the field location so business validation returns its 422.
        return Decimal("NaN")


@governance.get("/admin/config")
@protected()
def config_get():
    return jsonify(data=ConfigService(database(), service()).get(token()))


@governance.patch("/admin/config")
@protected(write=True)
def config_patch():
    if not request.is_json:
        raise ServiceError(415, "UNSUPPORTED_MEDIA_TYPE", "请使用application/json。")
    try:
        body = current_app.json.loads(request.get_data(), parse_float=decimal_literal)
    except ValueError:
        raise BadRequest() from None
    return jsonify(data=ConfigService(database(), service()).update(token(), body))


@governance.get("/admin/audit")
@protected()
def audit_list():
    if any(len(request.args.getlist(key)) != 1 for key in request.args):
        raise invalid()
    return jsonify(data=AuditService(database(), service()).list(token(), request.args.to_dict()))
