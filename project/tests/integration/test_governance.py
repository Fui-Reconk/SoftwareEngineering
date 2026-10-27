import pytest

from tests.workflow_support import staff, create_course, login_role
from tests.integration.test_statistics import seed_responses, publication_counts


def test_admin_config_has_values_ranges_and_units(staff):
    response = staff["client"].get("/api/admin/config")
    assert response.status_code == 200
    assert response.json["data"] == {
        "values": {"epsilon": .1, "k": 5, "epsilonTotal": 4.0},
        "ranges": {"epsilon": {"min": .01, "max": 1.0}, "k": {"min": 3, "max": 50}, "epsilonTotal": {"min": .1, "max": 20.0}},
        "units": {"epsilon": "ε", "k": "份", "epsilonTotal": "ε"}}


@pytest.mark.parametrize("role", ["teacher", "auditor"])
def test_config_rejects_other_roles_and_audit_rejects_teacher(staff, role):
    client, headers = login_role(staff, role, role)
    assert client.get("/api/admin/config").status_code == 403
    assert client.patch("/api/admin/config", json={"k": 6}, headers=headers).status_code == 403
    assert client.get("/api/admin/audit").status_code == (200 if role == "auditor" else 403)


def test_config_requires_csrf(staff):
    assert staff["client"].patch("/api/admin/config", json={"k": 6}).status_code == 403
    assert staff["client"].get("/api/admin/config").json["data"]["values"]["k"] == 5


@pytest.mark.parametrize("field,value", [("epsilon", True), ("epsilon", .001), ("epsilon", 1.1),
    ("epsilon", "0.1"), ("epsilon", .1000001), ("epsilon", 10**100),
    ("k", 2), ("k", 51), ("k", 5.0), ("epsilonTotal", .01), ("epsilonTotal", 21), ("unknown", 1)])
def test_invalid_config_is_422_with_field_and_no_partial_write(staff, field, value):
    before = staff["client"].get("/api/admin/config").json
    response = staff["client"].patch("/api/admin/config", json={"k": 6, field: value}, headers=staff["headers"])
    assert response.status_code == 422
    assert response.json["error"]["code"] == "INVALID_VALUE"
    assert response.json["error"]["field"] == field
    assert staff["client"].get("/api/admin/config").json == before


def test_budget_limit_change_preserves_spend_cache_and_applies_per_course(staff):
    create_course(staff)
    create_course(staff, "c2")
    seed_responses(staff)
    teacher, _ = login_role(staff)
    first = teacher.get("/api/courses/c1/statistics").json["data"]
    response = staff["client"].patch("/api/admin/config", json={"epsilonTotal": .5}, headers=staff["headers"])
    assert response.status_code == 200
    assert teacher.get("/api/courses/c1/statistics").json["data"] == {**first, "charged": False}
    with staff["db"].read_current() as con:
        assert [tuple(row) for row in con.execute("SELECT eps_total_micros,eps_used_micros FROM main.budget_ledger ORDER BY course_id")] == [(500000, 100000), (500000, 0)]
    create_course(staff, "c3")
    with staff["db"].read_current() as con:
        assert con.execute("SELECT eps_total_micros FROM main.budget_ledger WHERE course_id='c3'").fetchone()[0] == 500000
    changed = staff["client"].patch("/api/admin/config", json={"epsilon": .2}, headers=staff["headers"])
    assert changed.status_code == 200
    second = teacher.get("/api/courses/c1/statistics").json["data"]
    assert second["publicationId"] != first["publicationId"]
    assert publication_counts(staff)[:2] == (2, 300000)
    denied = staff["client"].patch("/api/admin/config", json={"epsilonTotal": .2}, headers=staff["headers"])
    assert denied.status_code == 422 and denied.json["error"]["field"] == "epsilonTotal"
    assert staff["client"].get("/api/admin/config").json["data"]["values"]["epsilonTotal"] == .5


def test_config_cannot_make_release_cost_exceed_total(staff):
    response = staff["client"].patch("/api/admin/config", json={"epsilon": 1, "epsilonTotal": .5}, headers=staff["headers"])
    assert response.status_code == 422 and response.json["error"]["field"] == "epsilon"


def test_config_and_course_budgets_roll_back_when_audit_fails(staff):
    create_course(staff)
    with staff["db"].transaction() as con:
        con.execute("CREATE TRIGGER main.fail_config BEFORE INSERT ON audit_log WHEN NEW.action='privacy.configure' BEGIN SELECT RAISE(ABORT,'test'); END")
    response = staff["client"].patch("/api/admin/config", json={"k": 6, "epsilonTotal": 2}, headers=staff["headers"])
    assert response.status_code == 503
    assert staff["client"].get("/api/admin/config").json["data"]["values"] == {"epsilon": .1, "k": 5, "epsilonTotal": 4.0}
    with staff["db"].read_current() as con:
        assert con.execute("SELECT eps_total_micros FROM main.budget_ledger").fetchone()[0] == 4000000


def test_auditor_gets_courses_translated_names_local_dates_and_pagination(staff):
    create_course(staff)
    create_course(staff, "c2", name="另一门课")
    with staff["db"].transaction() as con:
        con.executemany("INSERT INTO main.audit_log (log_id,actor,action,course_id,eps_cost_micros,ts) VALUES (?,?,?,?,?,?)", [
            ("before", staff["teacher"]["user_id"], "statistics.read", "c1", 0, "2001-01-01T15:59:59Z"),
            ("start", staff["teacher"]["user_id"], "statistics.publish", "c1", 100000, "2001-01-01T16:00:00Z"),
            ("end", staff["teacher"]["user_id"], "statistics.read", "c1", 0, "2001-01-02T15:59:59Z"),
            ("after", staff["teacher"]["user_id"], "statistics.read", "c1", 0, "2001-01-02T16:00:00Z"),
            ("other", staff["teacher"]["user_id"], "statistics.read", "c2", 0, "2001-01-02T00:00:00Z")])
    client, _ = login_role(staff, "auditor", "auditor")
    assert client.get("/api/courses").status_code == 403
    with staff["db"].read_current() as con:
        count = con.execute("SELECT count(*) FROM main.audit_log").fetchone()[0]
    query = "/api/admin/audit?from=2001-01-02&to=2001-01-02&course=c1&limit=1"
    first = client.get(query)
    assert first.status_code == 200
    data = first.json["data"]
    assert data["courses"] == [{"course_id": "c1", "name": "数据结构"}, {"course_id": "c2", "name": "另一门课"}]
    assert data["entries"] == [{"at": "2001-01-02T23:59:59+08:00", "actor": "teacher", "action": "读取统计", "target": "数据结构", "epsCost": 0.0}]
    assert data["next"] == 1
    last = client.get(query + "&offset=1").json["data"]
    assert last["next"] is None
    assert last["entries"] == [{"at": "2001-01-02T00:00:00+08:00", "actor": "teacher", "action": "发布统计", "target": "数据结构", "epsCost": .1}]
    with staff["db"].read_current() as con:
        assert con.execute("SELECT count(*) FROM main.audit_log").fetchone()[0] == count


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "offset=1.5", "from=no-date", "to=9999-12-31", "from=2026-01-02&to=2026-01-01", "from=2026-01-01T00:00:00", "limit=1&limit=2", "course=%ED%A0%80", "from=2001-01-01T00:00:00.1234567Z"])
def test_audit_rejects_malformed_filters(staff, query):
    response = staff["client"].get("/api/admin/audit?" + query)
    assert response.status_code == 400
    assert response.json["error"]["code"] == "INVALID_INPUT"


@pytest.mark.parametrize("literal", ["1.00000000000000001", "0.100000000000000000000000000000000000001"])
def test_config_checks_original_decimal_value_before_float_rounding(staff, literal):
    response = staff["client"].patch("/api/admin/config", data='{"epsilon":' + literal + '}',
        content_type="application/json", headers=staff["headers"])
    assert response.status_code == 422
    assert response.json["error"]["field"] == "epsilon"
    assert staff["client"].get("/api/admin/config").json["data"]["values"]["epsilon"] == .1


@pytest.mark.parametrize("boundary", ["from=2001-01-01T00:00:00.123400Z", "to=2001-01-01T00:00:00.122900Z"])
def test_audit_preserves_microsecond_filter_boundaries(staff, boundary):
    with staff["db"].transaction() as con:
        con.execute("INSERT INTO main.audit_log (log_id,actor,action,ts) VALUES ('precise',?,'statistics.read','2001-01-01T00:00:00.123Z')",
                    (staff["teacher"]["user_id"],))
    # Upper bound excludes normal setup logs from the present day.
    query = boundary + ("&to=2001-01-01T00:00:00.123500Z" if boundary.startswith("from") else "")
    response = staff["client"].get("/api/admin/audit?" + query)
    assert response.status_code == 200
    assert response.json["data"]["entries"] == []
