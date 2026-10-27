"""Small framework-independent validators and transaction-local helpers."""

import re
import time
from uuid import uuid4

from taces.business.auth.service import invalid
from taces.business.errors import ServiceError


def now():
    return int(time.time())


def text_value(value, *, maximum=200, minimum=1):
    if not isinstance(value, str) or not minimum <= len(value) <= maximum or "\x00" in value:
        raise invalid()
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise invalid("文本包含无效的Unicode字符。") from None
    value = value.strip()
    if len(value) < minimum:
        raise invalid()
    return value


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", value):
        raise invalid("标识符须为1–64位英文字母、数字、点、短横线或下划线。")
    return value


def integer(value, minimum=0, maximum=253402300799):
    if type(value) is not int or not minimum <= value <= maximum:
        raise invalid()
    return value


def fields(body, required=(), optional=()):
    if not isinstance(body, dict) or set(required) - body.keys() or body.keys() - set(required) - set(optional):
        raise invalid()


def course_row(connection, course_id):
    course = connection.execute("SELECT * FROM main.course WHERE course_id=?", (course_id,)).fetchone()
    if course is None:
        raise ServiceError(404, "COURSE_NOT_FOUND", "课程不存在。")
    return course


def write_audit(connection, actor, action, *, course_id=None, eps_cost_micros=0):
    connection.execute(
        "INSERT INTO main.audit_log (log_id,actor,action,course_id,eps_cost_micros) VALUES (?,?,?,?,?)",
        (uuid4().hex, actor, action, course_id, eps_cost_micros),
    )
