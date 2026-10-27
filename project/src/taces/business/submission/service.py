"""Capability-only anonymous submission; never link a code to a submission ID."""

import hashlib
import re
from uuid import uuid4

from taces.business.auth.service import invalid
from taces.business.common import fields, integer, now, text_value
from taces.business.errors import ServiceError


def code_digest(code):
    if not isinstance(code, str) or not re.fullmatch(r"[0-9a-fA-F]{32}", code):
        return None
    return hashlib.sha256(code.lower().encode("ascii")).hexdigest()


def lookup(connection, digest):
    return connection.execute(
        "SELECT e.course_id,e.used_flag,s.expires_at,w.closes_at,c.name,a.username "
        "FROM identity.enroll_code e JOIN main.course c ON c.course_id=e.course_id "
        "LEFT JOIN identity.code_state s ON s.code_hash=e.code_hash "
        "LEFT JOIN main.course_state w ON w.course_id=e.course_id "
        "LEFT JOIN identity.account a ON a.user_id=c.teacher_id WHERE e.code_hash=?", (digest,)
    ).fetchone()


def rejection(row):
    if row is None:
        return "unknown"
    if row["used_flag"]:
        return "used"
    if row["expires_at"] is None or row["closes_at"] is None or min(row["expires_at"], row["closes_at"]) <= now():
        return "expired"
    return None


class SubmissionService:
    def __init__(self, database):
        self.database = database

    def verify(self, code):
        digest = code_digest(code)
        if digest is None:
            return {"valid": False, "reason": "unknown"}
        with self.database.read_current() as connection:
            row = lookup(connection, digest)
            reason = rejection(row)
            if reason:
                return {"valid": False, "reason": reason}
            dimensions = connection.execute(
                "SELECT name FROM main.dimension WHERE course_id=? ORDER BY rowid", (row["course_id"],)
            ).fetchall()
            return {"valid": True, "course": {"code": row["course_id"], "title": row["name"],
                    "teacher": row["username"] or "授课教师", "dimensions": [{"name": item[0]} for item in dimensions]}}

    def submit(self, body):
        fields(body, {"code", "ratings"}, {"openText"})
        digest = code_digest(body["code"])
        if digest is None:
            raise ServiceError(400, "INVALID_CODE", "评价码无效。")
        with self.database.transaction() as connection:
            row = lookup(connection, digest)
            reason = rejection(row)
            if reason == "unknown":
                raise ServiceError(400, "INVALID_CODE", "评价码无效。")
            if reason == "used":
                raise ServiceError(409, "CODE_USED", "此评价码已经提交。")
            if reason == "expired":
                raise ServiceError(409, "WINDOW_CLOSED", "评价码已过期或评价窗口已关闭。")
            dimensions = connection.execute(
                "SELECT dim_id,name FROM main.dimension WHERE course_id=? ORDER BY rowid", (row["course_id"],)
            ).fetchall()
            if not 1 <= len(dimensions) <= 10:
                raise ServiceError(409, "COURSE_NOT_CONFIGURED", "课程评价维度尚未配置。")
            ratings = body["ratings"]
            if not isinstance(ratings, list) or len(ratings) != len(dimensions):
                raise invalid("请完整填写每个评价维度。")
            scores = {}
            for item in ratings:
                fields(item, {"dimension", "score"})
                label = text_value(item["dimension"], maximum=64)
                if label in scores:
                    raise invalid("不能重复提交同一维度。")
                scores[label] = integer(item["score"], 1, 5)
            if scores.keys() != {item["name"] for item in dimensions}:
                raise invalid("评价维度与课程不匹配。")
            comment = text_value(body.get("openText", ""), maximum=500, minimum=0)
            updated = connection.execute(
                "UPDATE identity.enroll_code SET used_flag=1 WHERE code_hash=? AND used_flag=0", (digest,)
            )
            if updated.rowcount != 1:
                raise ServiceError(409, "CODE_USED", "此评价码已经提交。")
            submission_id = uuid4().hex
            rows = [(uuid4().hex, submission_id, row["course_id"], item["dim_id"], scores[item["name"]]) for item in dimensions]
            connection.executemany("INSERT INTO evaluation.rating VALUES (?,?,?,?,?)", rows)
            if comment:
                connection.execute("INSERT INTO evaluation.open_text VALUES (?,?,?)", (uuid4().hex, rows[0][0], comment))
            connection.execute("UPDATE main.course_state SET data_version=data_version+1 WHERE course_id=?", (row["course_id"],))
            # No per-submission audit timestamp, code hash, account ID, IP, or
            # identity-to-submission relationship is written to evaluation data.
            return {"submissionId": submission_id}
