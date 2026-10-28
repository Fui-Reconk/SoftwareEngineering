import time
import hashlib
import json
import re
import sqlite3

import pytest

from tests.workflow_support import staff, course_body, create_course, issue_codes, login_role


def test_course_creation_preserves_existing_list_shape_and_adds_budget(staff):
    course = create_course(staff)
    assert set(course) == {"course_id", "name", "teacher_id", "term"}
    assert staff["client"].get("/api/courses").json["data"]["courses"] == [course]
    with staff["db"].read_current() as connection:
        assert connection.execute("SELECT eps_total_micros,eps_used_micros FROM main.budget_ledger").fetchone()[:] == (4000000, 0)
        assert len(connection.execute("SELECT * FROM main.dimension").fetchall()) == 3
        assert connection.execute("SELECT action FROM main.audit_log ORDER BY rowid DESC").fetchone()[0] == "course.create"


@pytest.mark.parametrize("changes", [
    {"teacher_id": "missing"}, {"teacher_id": None}, {"name": ""}, {"name": "bad\ud800"},
    {"course_id": "../escape"}, {"term": []}, {"closes_at": True},
    {"dimensions": [{"name": "one", "weight": 0.2}]},
    {"dimensions": [{"name": "one"}, {"name": "one"}]}, {"unexpected": 1},
])
def test_course_invalid_input_is_atomic(staff, changes):
    response = staff["client"].post("/api/admin/courses", headers=staff["headers"],
                                  data=json.dumps({**course_body(staff), **changes}), content_type="application/json")
    assert response.status_code == 400
    with staff["db"].read_current() as connection:
        for table in ("course", "dimension", "course_state", "budget_ledger"):
            assert connection.execute(f"SELECT count(*) FROM main.{table}").fetchone()[0] == 0


def test_duplicate_course_is_conflict_not_overwrite(staff):
    course = create_course(staff)
    response = staff["client"].post("/api/admin/courses", json={**course_body(staff), "name": "replacement"}, headers=staff["headers"])
    assert response.status_code == 409
    assert staff["client"].get("/api/courses/c1").json["data"]["course"] == course


@pytest.mark.parametrize("role", ["teacher", "auditor"])
def test_staff_without_course_management_permission_is_denied(staff, role):
    client, headers = login_role(staff, "teacher" if role == "teacher" else "auditor", role)
    assert client.post("/api/admin/courses", json=course_body(staff), headers=headers).status_code == 403
    assert client.post("/api/admin/courses/c1/evaluation-codes", json={"count": 1}, headers=headers).status_code == 403


def test_course_management_requires_current_session_and_csrf(staff):
    assert staff["app"].test_client().post("/api/admin/courses", json=course_body(staff)).status_code == 401
    assert staff["client"].post("/api/admin/courses", json=course_body(staff)).status_code == 403


def test_code_batch_is_unique_and_only_digests_are_stored(staff):
    create_course(staff)
    codes = issue_codes(staff, count=20)
    assert len(codes) == len(set(codes)) == 20
    assert all(re.fullmatch("[0-9a-f]{32}", code) for code in codes)
    with staff["db"].read_current() as connection:
        stored = {row[0] for row in connection.execute("SELECT code_hash FROM identity.enroll_code")}
        assert stored == {hashlib.sha256(code.encode()).hexdigest() for code in codes}
        assert connection.execute("SELECT count(*) FROM identity.code_state").fetchone()[0] == 20
        audit = json.dumps([dict(row) for row in connection.execute("SELECT * FROM main.audit_log")])
        assert all(code not in audit for code in codes)


@pytest.mark.parametrize("count", [0, -1, 1001, True, 1.5, "1", None])
def test_code_batch_invalid_count_is_atomic(staff, count):
    create_course(staff)
    response = staff["client"].post("/api/admin/courses/c1/evaluation-codes", json={"count": count}, headers=staff["headers"])
    assert response.status_code == 400
    with staff["db"].read_current() as connection:
        assert connection.execute("SELECT count(*) FROM identity.enroll_code").fetchone()[0] == 0


def test_course_can_transfer_owner_and_close_window(staff):
    create_course(staff)
    other = staff["auth"].create_account(staff["token"], "other", "Other-password-2026!", "teacher")
    result = staff["client"].patch("/api/admin/courses/c1", headers=staff["headers"], json={"teacher_id": other["user_id"], "closes_at": 0})
    assert result.status_code == 200
    teacher, _ = login_role(staff)
    assert teacher.get("/api/courses/c1").status_code == 403
    assert staff["client"].post("/api/admin/courses/c1/evaluation-codes", json={"count": 1}, headers=staff["headers"]).status_code == 409


def test_reassigned_course_moves_between_teacher_workspaces(staff):
    course = create_course(staff)
    other = staff["auth"].create_account(staff["token"], "second_teacher", "Other-password-2026!", "teacher")
    other_token, _ = staff["auth"].login("second_teacher", "Other-password-2026!")
    previous, _ = login_role(staff)
    current = staff["app"].test_client()
    current.set_cookie("taces_session", other_token, path="/api")
    assert previous.get("/api/courses").json["data"]["courses"] == [course]
    assert current.get("/api/courses").json["data"]["courses"] == []

    response = staff["client"].patch("/api/admin/courses/c1", headers=staff["headers"],
                                     json={"teacher_id": other["user_id"]})
    assert response.status_code == 200
    assert previous.get("/api/courses").json["data"]["courses"] == []
    assert current.get("/api/courses").json["data"]["courses"] == [
        {**course, "teacher_id": other["user_id"]}
    ]
    assert previous.get("/api/courses/c1").status_code == 403
    assert current.get("/api/courses/c1").status_code == 200


def test_course_audit_failure_rolls_back_every_write(staff, monkeypatch):
    import taces.business.courses.service as module
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("injected audit failure")
    monkeypatch.setattr(module, "write_audit", fail)
    response = staff["client"].post("/api/admin/courses", json=course_body(staff), headers=staff["headers"])
    assert response.status_code == 503
    with staff["db"].read_current() as connection:
        for table in ("course", "dimension", "course_state", "budget_ledger"):
            assert connection.execute(f"SELECT count(*) FROM main.{table}").fetchone()[0] == 0


def test_large_integer_weight_returns_validation_error(staff):
    body = {**course_body(staff), "dimensions": [{"name": "one", "weight": 10**400}]}
    response = staff["client"].post("/api/admin/courses", json=body, headers=staff["headers"])
    assert response.status_code == 400
    assert response.json["error"]["code"] == "INVALID_INPUT"
    assert staff["client"].get("/api/courses").json["data"]["courses"] == []


@pytest.mark.parametrize("method", ["post", "patch"])
def test_surrogate_teacher_id_returns_validation_error(staff, method):
    if method == "patch":
        original = create_course(staff)
        body = {"teacher_id": "bad\ud800"}
        path = "/api/admin/courses/c1"
    else:
        body = {**course_body(staff), "teacher_id": "bad\ud800"}
        path = "/api/admin/courses"
    response = getattr(staff["client"], method)(path, data=json.dumps(body), content_type="application/json", headers=staff["headers"])
    assert response.status_code == 400
    assert response.json["error"]["code"] == "INVALID_INPUT"
    actual = staff["client"].get("/api/courses").json["data"]["courses"]
    assert actual == ([original] if method == "patch" else [])


def test_admin_course_list_exposes_window_and_dimensions_only_to_admin(staff):
    closes_at = int(time.time()) + 3600
    dimensions = [{"name": "内容", "weight": 0.7}, {"name": "反馈", "weight": 0.3}]
    course = create_course(staff, closes_at=closes_at, dimensions=dimensions)
    response = staff["client"].get("/api/admin/courses")
    assert response.status_code == 200
    assert response.json["data"]["courses"] == [{**course, "closes_at": closes_at, "dimensions": dimensions}]
    teacher, _ = login_role(staff)
    assert teacher.get("/api/admin/courses").status_code == 403
    assert staff["app"].test_client().get("/api/admin/courses").status_code == 401
