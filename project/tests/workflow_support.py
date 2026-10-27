"""Shared real-database fixtures for the new workflow APIs."""

import time

import pytest


PASSWORD = "Workflow-password-2026!"


@pytest.fixture
def staff(app, database):
    auth = app.extensions["taces_auth"]
    admin = auth.bootstrap_admin("admin", PASSWORD)
    token, _ = auth.login("admin", PASSWORD)
    teacher = auth.create_account(token, "teacher", PASSWORD, "teacher")
    client = app.test_client()
    client.set_cookie("taces_session", token, path="/api")
    csrf = auth.current(token)["csrf_token"]
    return {"app": app, "db": database, "auth": auth, "admin": admin,
            "teacher": teacher, "token": token, "client": client,
            "headers": {"X-CSRF-Token": csrf}}


def course_body(staff, course_id="c1"):
    return {"course_id": course_id, "name": "数据结构", "teacher_id": staff["teacher"]["user_id"],
            "term": "2026秋", "closes_at": int(time.time()) + 3600}


def create_course(staff, course_id="c1", **changes):
    response = staff["client"].post("/api/admin/courses", json={**course_body(staff, course_id), **changes}, headers=staff["headers"])
    assert response.status_code == 201, response.json
    return response.json["data"]["course"]


def issue_codes(staff, course_id="c1", count=1):
    response = staff["client"].post(f"/api/admin/courses/{course_id}/evaluation-codes",
                                  json={"count": count}, headers=staff["headers"])
    assert response.status_code == 201, response.json
    return response.json["data"]["codes"]


def login_role(staff, username="teacher", role="teacher"):
    if username != "teacher":
        staff["auth"].create_account(staff["token"], username, PASSWORD, role)
    token, result = staff["auth"].login(username, PASSWORD)
    client = staff["app"].test_client()
    client.set_cookie("taces_session", token, path="/api")
    return client, {"X-CSRF-Token": result["csrf_token"]}
