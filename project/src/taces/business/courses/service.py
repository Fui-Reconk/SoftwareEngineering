"""Course management and one-time codes without an identity/submission link."""

import hashlib
import math
import secrets
from uuid import uuid4

from taces.business.auth.policy import require_permission
from taces.business.auth.service import invalid
from taces.business.common import course_row, fields, identifier, integer, now, text_value, write_audit
from taces.business.errors import ServiceError


DEFAULT_DIMENSIONS = ("教学内容", "教学方法", "考核方式")


def dimensions_value(value):
    if value is None:
        value = [{"name": name} for name in DEFAULT_DIMENSIONS]
    if not isinstance(value, list) or not 1 <= len(value) <= 10:
        raise invalid("评价维度数量须为1–10。")
    result = []
    for item in value:
        fields(item, {"name"}, {"weight"})
        name = text_value(item["name"], maximum=64)
        weight = item.get("weight", 1 / len(value))
        if type(weight) not in (int, float) or not 0 < weight <= 1 or not math.isfinite(weight):
            raise invalid("维度权重须为有效正数。")
        result.append((name, weight))
    if len({name for name, _ in result}) != len(result) or not math.isclose(sum(weight for _, weight in result), 1, abs_tol=1e-9):
        raise invalid("维度名称不能重复，权重之和须为1。")
    return result


class CourseService:
    def __init__(self, database, auth):
        self.database = database
        self.auth = auth

    @staticmethod
    def _teacher(connection, teacher_id):
        teacher_id = identifier(teacher_id)
        row = connection.execute("SELECT role,is_active FROM identity.account WHERE user_id=?", (teacher_id,)).fetchone()
        if row is None or row["role"] != "teacher" or not row["is_active"]:
            raise invalid("课程须分配给启用的教师账号。")
        return teacher_id

    @staticmethod
    def _ensure_budget(connection, course_id):
        connection.execute(
            "INSERT INTO main.budget_ledger (ledger_id,course_id,eps_total_micros) "
            "SELECT ?,?,total_micros FROM main.privacy_policy WHERE singleton=1 "
            "AND NOT EXISTS (SELECT 1 FROM main.budget_ledger WHERE course_id=?)",
            (uuid4().hex, course_id, course_id),
        )

    def create(self, token, body):
        with self.auth._operation(token, "courses.create", write=True) as (connection, actor):
            require_permission(actor, "courses:manage")
            fields(body, {"course_id", "name", "teacher_id", "term"}, {"dimensions", "closes_at"})
            course_id = identifier(body["course_id"])
            name = text_value(body["name"])
            term = text_value(body["term"], maximum=100)
            teacher_id = self._teacher(connection, body["teacher_id"])
            dimensions = dimensions_value(body.get("dimensions"))
            closes_at = integer(body.get("closes_at", now() + 7 * 86400))
            if connection.execute("SELECT 1 FROM main.course WHERE course_id=?", (course_id,)).fetchone():
                raise ServiceError(409, "COURSE_EXISTS", "课程标识已存在。")
            connection.execute("INSERT INTO main.course VALUES (?,?,?,?)", (course_id, name, teacher_id, term))
            connection.executemany("INSERT INTO main.dimension VALUES (?,?,?,?)",
                                   [(uuid4().hex, course_id, label, weight) for label, weight in dimensions])
            connection.execute("INSERT INTO main.course_state VALUES (?,?,0)", (course_id, closes_at))
            self._ensure_budget(connection, course_id)
            write_audit(connection, actor["user_id"], "course.create", course_id=course_id)
            return dict(course_row(connection, course_id))

    def update(self, token, course_id, body):
        with self.auth._operation(token, "courses.update", write=True) as (connection, actor):
            require_permission(actor, "courses:manage")
            fields(body, (), {"name", "teacher_id", "term", "closes_at"})
            if not body:
                raise invalid()
            course = course_row(connection, course_id)
            name = text_value(body.get("name", course["name"]))
            term = text_value(body.get("term", course["term"]), maximum=100)
            teacher_id = self._teacher(connection, body.get("teacher_id", course["teacher_id"]))
            connection.execute("UPDATE main.course SET name=?,teacher_id=?,term=? WHERE course_id=?", (name, teacher_id, term, course_id))
            if "closes_at" in body:
                connection.execute(
                    "INSERT INTO main.course_state (course_id,closes_at) VALUES (?,?) "
                    "ON CONFLICT(course_id) DO UPDATE SET closes_at=excluded.closes_at",
                    (course_id, integer(body["closes_at"])),
                )
            self._ensure_budget(connection, course_id)
            write_audit(connection, actor["user_id"], "course.update", course_id=course_id)
            return dict(course_row(connection, course_id))

    def issue_codes(self, token, course_id, count, expires_at=None):
        with self.auth._operation(token, "codes.issue", write=True) as (connection, actor):
            require_permission(actor, "courses:manage")
            course_row(connection, course_id)
            count = integer(count, 1, 1000)
            state = connection.execute("SELECT closes_at FROM main.course_state WHERE course_id=?", (course_id,)).fetchone()
            if state is None or state[0] <= now():
                raise ServiceError(409, "WINDOW_CLOSED", "评价窗口已关闭。")
            deadline = state[0] if expires_at is None else integer(expires_at)
            if not now() < deadline <= state[0]:
                raise invalid("评价码须在评价截止之前过期。")
            codes = [secrets.token_hex(16) for _ in range(count)]
            hashes = [hashlib.sha256(code.encode("ascii")).hexdigest() for code in codes]
            connection.executemany("INSERT INTO identity.enroll_code VALUES (?,?,0)", [(digest, course_id) for digest in hashes])
            connection.executemany("INSERT INTO identity.code_state VALUES (?,?)", [(digest, deadline) for digest in hashes])
            write_audit(connection, actor["user_id"], "codes.issue", course_id=course_id)
            return codes
