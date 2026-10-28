"""Staff numbers and names remain distinct through login and publication."""

import csv
import json
import sqlite3
from io import BytesIO, StringIO

import pytest
from werkzeug.http import parse_options_header
from werkzeug.security import generate_password_hash

import taces.data.database as storage
from taces.business.auth.service import AuthService
from taces.data.database import Database, SCHEMA_DIR
from tests.workflow_support import PASSWORD, create_course, issue_codes, staff
from tests.integration.test_statistics import seed_responses


def login(client, username):
    return client.post("/api/auth/login", json={"username": username, "password": PASSWORD},
                       headers={"X-TACES-Request": "1"})


def filename(response):
    return parse_options_header(response.headers["Content-Disposition"])[1]["filename"]


def values(response):
    return dict(list(csv.reader(StringIO(response.data.decode("utf-8-sig"))))[1:])


def test_admin_sets_and_changes_staff_number_and_name_independently(staff):
    response = staff["client"].post("/api/admin/accounts", headers=staff["headers"], json={
        "username": "001234", "display_name": "张晓明", "password": PASSWORD, "role": "teacher",
    })
    assert response.status_code == 201, response.json
    account = response.json["data"]["account"]
    assert (account["username"], account["display_name"]) == ("001234", "张晓明")
    teacher = staff["app"].test_client()
    assert login(teacher, "001234").json["data"]["account"]["display_name"] == "张晓明"
    changed = staff["client"].patch(f"/api/admin/accounts/{account['user_id']}", headers=staff["headers"],
                                    json={"username": "001235", "display_name": "张小明"})
    assert changed.status_code == 200
    assert teacher.get("/api/auth/me").status_code == 401
    assert login(staff["app"].test_client(), "001234").status_code == 401
    assert login(staff["app"].test_client(), "001235").json["data"]["account"]["display_name"] == "张小明"


@pytest.mark.parametrize("name", ["", "  ", None, "张\n明", "x" * 65])
def test_new_account_requires_a_valid_name(staff, name):
    response = staff["client"].post("/api/admin/accounts", headers=staff["headers"], json={
        "username": "001234", "display_name": name, "password": PASSWORD, "role": "teacher",
    })
    assert response.status_code == 400


def test_missing_name_is_rejected_by_account_creation_api(staff):
    response = staff["client"].post("/api/admin/accounts", headers=staff["headers"], json={
        "username": "001234", "password": PASSWORD, "role": "teacher",
    })
    assert response.status_code == 400


def test_duplicate_login_number_cannot_overwrite_another_account(staff):
    response = staff["client"].post("/api/admin/accounts", headers=staff["headers"], json={
        "username": "001234", "display_name": "张晓明", "password": PASSWORD, "role": "teacher",
    })
    account = response.json["data"]["account"]
    conflict = staff["client"].patch(f"/api/admin/accounts/{account['user_id']}", headers=staff["headers"],
                                     json={"username": "TEACHER", "display_name": "李老师"})
    assert conflict.status_code == 409
    all_accounts = staff["client"].get("/api/admin/accounts").json["data"]["accounts"]
    assert next(item for item in all_accounts if item["user_id"] == account["user_id"]) == account


@pytest.mark.parametrize("operation", ["create", "rename"])
def test_assigning_a_free_staff_number_clears_its_old_login_throttle(staff, operation):
    for _ in range(5):
        assert login(staff["app"].test_client(), "001235").status_code == 401
    if operation == "create":
        response = staff["client"].post("/api/admin/accounts", headers=staff["headers"], json={
            "username": "001235", "display_name": "张晓明", "password": PASSWORD, "role": "teacher",
        })
        assert response.status_code == 201
    else:
        response = staff["client"].patch(f"/api/admin/accounts/{staff['teacher']['user_id']}",
                                         headers=staff["headers"], json={"username": "001235"})
        assert response.status_code == 200
    assert login(staff["app"].test_client(), "001235").status_code == 200


def test_audit_distinguishes_people_after_staff_number_is_changed_and_reused(staff):
    first_id = staff["teacher"]["user_id"]
    assert login(staff["app"].test_client(), "teacher").status_code == 200
    changed = staff["client"].patch(f"/api/admin/accounts/{first_id}", headers=staff["headers"],
                                    json={"username": "001235"})
    assert changed.status_code == 200
    new_account = staff["client"].post("/api/admin/accounts", headers=staff["headers"], json={
        "username": "teacher", "display_name": "另一位教师", "password": PASSWORD, "role": "teacher",
    }).json["data"]["account"]
    assert login(staff["app"].test_client(), "teacher").status_code == 200
    records = staff["client"].get("/api/admin/audit?limit=100").json["data"]["entries"]
    assert any(item["actorId"] == first_id and item["action"] == "登录" for item in records)
    assert any(item["actorId"] == new_account["user_id"] and item["action"] == "登录" for item in records)
    assert any(item["targetId"] == first_id and item["action"] == "修改账号"
               and item["accountChange"] == {"from": "teacher", "to": "001235"} for item in records)


def test_publication_keeps_teacher_name_after_rename_and_course_transfer(staff):
    first = staff["client"].post("/api/admin/accounts", headers=staff["headers"], json={
        "username": "001234", "display_name": "张晓明", "password": PASSWORD, "role": "teacher",
    }).json["data"]["account"]
    create_course(staff, teacher_id=first["user_id"])
    student_code = issue_codes(staff)[0]
    verified = staff["app"].test_client().post("/api/evaluation-codes/verify", json={"code": student_code})
    assert verified.status_code == 200
    assert verified.json["data"]["course"]["teacher"] == "张晓明"
    seed_responses(staff)
    original = staff["app"].test_client()
    assert login(original, "001234").status_code == 200
    snapshot = original.get("/api/courses/c1/statistics").json["data"]
    assert snapshot["teacherName"] == "张晓明"
    changed = staff["client"].patch(f"/api/admin/accounts/{first['user_id']}", headers=staff["headers"],
                                    json={"display_name": "张小明"})
    assert changed.status_code == 200
    second = staff["client"].post("/api/admin/accounts", headers=staff["headers"], json={
        "username": "002222", "display_name": "李老师", "password": PASSWORD, "role": "teacher",
    }).json["data"]["account"]
    assert staff["client"].patch("/api/admin/courses/c1", headers=staff["headers"],
                                 json={"teacher_id": second["user_id"]}).status_code == 200
    successor = staff["app"].test_client()
    assert login(successor, "002222").status_code == 200
    saved = successor.get("/api/courses/c1/statistics").json["data"]
    assert saved["teacherName"] == "张晓明" and saved["publicationId"] == snapshot["publicationId"]
    csv_response = successor.get("/api/courses/c1/export?format=csv")
    assert filename(csv_response) == "数据结构_2026秋_张晓明.csv"
    assert values(csv_response)["teacherName"] == "张晓明"
    assert values(csv_response)["publicationId"] == snapshot["publicationId"]
    pdf_response = successor.get("/api/courses/c1/export?format=pdf")
    assert filename(pdf_response) == "数据结构_2026秋_张晓明.pdf"
    from pypdf import PdfReader
    text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(pdf_response.data)).pages)
    assert "张晓明" in text and snapshot["publicationId"] in text


def test_v3_upgrade_preserves_login_and_does_not_invent_a_name(tmp_path):
    db = Database(tmp_path / "old")
    encoded = generate_password_hash(PASSWORD)
    with db._connect(create=True) as con:
        for sql in ("metadata.sql", "identity.sql", "evaluation.sql", "auth.sql", "workflow.sql"):
            con.executescript((SCHEMA_DIR / sql).read_text(encoding="utf-8"))
        con.execute("INSERT INTO identity.account VALUES (?, ?, ?, ?, ?, ?)",
                    ("legacy", "001234", encoded, "teacher", 1, 100))
        for schema in ("main", "identity", "evaluation"):
            con.execute(f"PRAGMA {schema}.user_version=3")
    db.upgrade()
    db.upgrade()
    db.check_ready()
    with db.read_current() as con:
        account = con.execute("SELECT * FROM identity.account WHERE user_id='legacy'").fetchone()
        assert account["username"] == "001234" and account["password_hash"] == encoded
        assert account["display_name"] == ""
    _, session = AuthService(db).login("001234", PASSWORD)
    assert session["account"]["display_name"] == ""


def test_v3_name_migration_failure_rolls_back_column_and_all_versions(tmp_path, monkeypatch):
    db = Database(tmp_path / "old")
    with db._connect(create=True) as con:
        for sql in ("metadata.sql", "identity.sql", "evaluation.sql", "auth.sql", "workflow.sql"):
            con.executescript((SCHEMA_DIR / sql).read_text(encoding="utf-8"))
        con.execute("INSERT INTO identity.account VALUES ('legacy','001234','saved-hash','teacher',1,100)")
        for schema in ("main", "identity", "evaluation"):
            con.execute(f"PRAGMA {schema}.user_version=3")
    schema_copy = tmp_path / "schema"
    schema_copy.mkdir()
    (schema_copy / "account_names.sql").write_text(
        (SCHEMA_DIR / "account_names.sql").read_text(encoding="utf-8") + "\nINVALID SQL;\n", encoding="utf-8")
    monkeypatch.setattr(storage, "SCHEMA_DIR", schema_copy)
    with pytest.raises(sqlite3.OperationalError):
        db.upgrade()
    with db.read() as con:
        assert tuple(con.execute(f"PRAGMA {schema}.user_version").fetchone()[0]
                     for schema in ("main", "identity", "evaluation")) == (3, 3, 3)
        assert "display_name" not in {row[1] for row in con.execute("PRAGMA identity.table_info(account)")}
        assert con.execute("SELECT password_hash FROM identity.account WHERE user_id='legacy'").fetchone()[0] == "saved-hash"


def test_legacy_snapshot_uses_current_name_and_marks_it_as_inferred(staff):
    create_course(staff)
    seed_responses(staff)
    token, _ = staff["auth"].login("teacher", PASSWORD)
    teacher = staff["app"].test_client()
    teacher.set_cookie("taces_session", token, path="/api")
    snapshot = teacher.get("/api/courses/c1/statistics").json["data"]
    with staff["db"].transaction() as con:
        data = json.loads(con.execute("SELECT payload FROM main.agg_result WHERE publication_id=?",
                                      (snapshot["publicationId"],)).fetchone()[0])
        data.pop("teacherName", None)
        con.execute("UPDATE main.agg_result SET payload=? WHERE publication_id=?",
                    (json.dumps(data, ensure_ascii=False), snapshot["publicationId"]))
    staff["auth"].update_account(staff["token"], staff["teacher"]["user_id"], {"display_name": "王老师"})
    token, _ = staff["auth"].login("teacher", PASSWORD)
    teacher.set_cookie("taces_session", token, path="/api")
    result = teacher.get("/api/courses/c1/export?format=csv")
    assert filename(result) == "数据结构_2026秋_王老师.csv"
    assert values(result)["teacherName"] == "王老师"
    assert "当前任课" in values(result)["teacherNameNote"]
