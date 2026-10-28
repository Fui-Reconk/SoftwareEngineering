import csv
from io import BytesIO, StringIO

import pytest
from werkzeug.http import parse_options_header

from tests.workflow_support import PASSWORD, staff, create_course, login_role
from tests.integration.test_statistics import seed_responses, publication_counts


def published(staff, **changes):
    create_course(staff, **changes)
    seed_responses(staff)
    teacher, _ = login_role(staff)
    data = teacher.get("/api/courses/c1/statistics").json["data"]
    return teacher, data


def csv_values(response):
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert response.data.startswith(b"\xef\xbb\xbf")
    return dict(list(csv.reader(StringIO(response.data.decode("utf-8-sig"))))[1:])


def attachment_name(response):
    disposition, options = parse_options_header(response.headers["Content-Disposition"])
    assert disposition == "attachment"
    return options["filename"]


@pytest.mark.parametrize("format", ["csv", "pdf"])
def test_export_filename_uses_snapshot_course_term_and_teacher_not_publication_id(staff, format):
    teacher, data = published(staff)
    response = teacher.get(f"/api/courses/c1/export?format={format}")
    assert response.status_code == 200
    assert attachment_name(response) == f"数据结构_2026秋_teacher.{format}"
    assert data["publicationId"] not in attachment_name(response)
    if format == "csv":
        assert csv_values(response)["publicationId"] == data["publicationId"]
    else:
        from pypdf import PdfReader
        text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(response.data)).pages)
        assert data["publicationId"] in text


def test_history_filename_uses_original_course_term_and_published_teacher(staff):
    original_teacher, data = published(staff)
    new_teacher = staff["auth"].create_account(staff["token"], "teacher2", PASSWORD, "teacher", "teacher2")
    changed = staff["client"].patch("/api/admin/courses/c1", json={
        "name": "新课程名", "term": "2027春", "teacher_id": new_teacher["user_id"]
    }, headers=staff["headers"])
    assert changed.status_code == 200
    assert original_teacher.get("/api/courses/c1/export?format=csv").status_code == 403
    token, _ = staff["auth"].login("teacher2", PASSWORD)
    client = staff["app"].test_client()
    client.set_cookie("taces_session", token, path="/api")
    response = client.get("/api/courses/c1/export?format=csv&publication=" + data["publicationId"])
    assert attachment_name(response) == "数据结构_2026秋_teacher.csv"
    assert csv_values(response)["publicationId"] == data["publicationId"]


@pytest.mark.parametrize("username", [".teacher", "teacher.", "..."])
def test_export_filename_preserves_valid_dots_in_teacher_name(staff, username):
    staff["auth"].update_account(staff["token"], staff["teacher"]["user_id"], {"display_name": username})
    client, data = published(staff)
    response = client.get("/api/courses/c1/export?format=csv&publication=" + data["publicationId"])
    assert attachment_name(response) == f"数据结构_2026秋_{username}.csv"
    assert csv_values(response)["publicationId"] == data["publicationId"]


@pytest.mark.parametrize(("course", "term", "expected"), [
    (".NET 程序设计", "2026秋.", "_.NET 程序设计_2026秋._teacher.csv"),
    ("...", "...", "_..._..._teacher.csv"),
])
def test_export_filename_preserves_dots_in_course_and_term(staff, course, term, expected):
    teacher, data = published(staff, name=course, term=term)
    response = teacher.get("/api/courses/c1/export?format=csv")
    assert attachment_name(response) == expected
    assert csv_values(response)["publicationId"] == data["publicationId"]


def test_export_filename_sanitizes_unsafe_characters(staff):
    teacher, _ = published(staff, name="课程/实验\\A:*\r\n奇", term="2026|秋")
    response = teacher.get("/api/courses/c1/export?format=csv")
    assert attachment_name(response) == "课程 实验 A 奇_2026 秋_teacher.csv"
    assert "\r" not in response.headers["Content-Disposition"]
    assert "\n" not in response.headers["Content-Disposition"]


def test_export_filename_limits_long_unicode_names_without_losing_extension(staff):
    teacher, _ = published(staff, name="课" * 200, term="春" * 100)
    response = teacher.get("/api/courses/c1/export?format=csv")
    name = attachment_name(response)
    assert name.startswith("课") and "_春" in name and name.endswith("_teacher.csv")
    assert len(name.encode("utf-8")) <= 255
    assert "�" not in name


def test_csv_reuses_exact_publication_without_spending_or_resampling(staff):
    teacher, data = published(staff)
    before = publication_counts(staff)
    values = csv_values(teacher.get("/api/courses/c1/export?format=csv"))
    assert values["publicationId"] == data["publicationId"]
    assert values["courseTitle"] == "数据结构"
    for key in ("pooledMean", "interval", "spread", "responses", "enrolled"):
        assert float(values[key]) == data[key]
    for row in data["dimensions"]:
        assert float(values["dimension:" + row["name"]]) == row["value"]
    assert values["publishedAt"] == data["publishedAt"]
    assert "private-secret" not in str(values)
    assert publication_counts(staff) == before
    with staff["db"].read_current() as con:
        assert con.execute("SELECT count(*) FROM main.audit_log WHERE action='export.csv'").fetchone()[0] == 1


def test_explicit_old_snapshot_and_export_before_new_publication(staff):
    teacher, first = published(staff)
    seed_responses(staff, 1)
    # Export never triggers publication, even with fresh unreported submissions.
    assert csv_values(teacher.get("/api/courses/c1/export?format=csv"))["responses"] == "5"
    second = teacher.get("/api/courses/c1/statistics").json["data"]
    assert second["responses"] == 6
    values = csv_values(teacher.get("/api/courses/c1/export?format=csv&publication=" + first["publicationId"]))
    assert values["publicationId"] == first["publicationId"] and values["responses"] == "5"
    assert publication_counts(staff)[:2] == (2, 200000)


@pytest.mark.parametrize("role", ["admin", "auditor", "other_teacher"])
def test_export_requires_current_teacher_ownership(staff, role):
    create_course(staff)
    client = staff["client"] if role == "admin" else login_role(staff, role, "teacher" if role == "other_teacher" else role)[0]
    assert client.get("/api/courses/c1/export?format=csv").status_code == 403


def test_export_rejects_missing_snapshot_and_bad_options(staff):
    create_course(staff)
    teacher, _ = login_role(staff)
    response = teacher.get("/api/courses/c1/export?format=csv")
    assert response.status_code == 409 and response.json["error"]["code"] == "NOT_PUBLISHED"
    for suffix in ("format=html", "format=csv&format=pdf", "format=csv&unknown=1", "format=csv&publication=bad"):
        assert teacher.get("/api/courses/c1/export?" + suffix).status_code == 400
    assert teacher.get("/api/courses/c1/export?format=csv&publication=" + "a" * 32).status_code == 404


def test_csv_neutralizes_formula_cells_and_download_filename_is_safe(staff):
    teacher, data = published(staff, name="=SUM(1,2)", term="@malicious")
    response = teacher.get("/api/courses/c1/export?format=csv")
    values = csv_values(response)
    assert values["courseTitle"] == "'=SUM(1,2)"
    assert values["term"] == "'@malicious"
    assert attachment_name(response) == "=SUM(1,2)_@malicious_teacher.csv"
    assert data["publicationId"] not in attachment_name(response)


def test_pdf_contains_chinese_and_exact_saved_numbers(staff):
    teacher, data = published(staff, name="数据结构 <安全> & 实验")
    response = teacher.get("/api/courses/c1/export?format=pdf")
    assert response.status_code == 200 and response.mimetype == "application/pdf"
    from pypdf import PdfReader
    reader = PdfReader(BytesIO(response.data))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "数据结构 <安全> & 实验" in text
    assert "教学内容" in text and "发布快照" in text
    assert data["publicationId"] in text
    assert str(data["pooledMean"]) in text and str(data["interval"]) in text
    assert "private-secret" not in text
    assert publication_counts(staff)[:2] == (1, 100000)


def test_export_audit_failure_does_not_send_unlogged_file(staff):
    teacher, _ = published(staff)
    with staff["db"].transaction() as con:
        con.execute("CREATE TRIGGER main.fail_export BEFORE INSERT ON audit_log WHEN NEW.action='export.csv' BEGIN SELECT RAISE(ABORT,'test'); END")
    response = teacher.get("/api/courses/c1/export?format=csv")
    assert response.status_code == 503 and response.is_json
    assert publication_counts(staff)[:2] == (1, 100000)
