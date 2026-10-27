from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from tests.workflow_support import staff, create_course, issue_codes, login_role
from tests.integration.test_submissions import valid_body


def seed_responses(staff, count=5, course_id="c1", text="作业反馈清晰，private-secret"):
    client = staff["app"].test_client()
    for code in issue_codes(staff, course_id, count):
        response = client.post("/api/submissions", json={**valid_body(code), "openText": text})
        assert response.status_code == 201, response.json


def publication_counts(staff):
    with staff["db"].read_current() as con:
        return (con.execute("SELECT count(*) FROM main.agg_result").fetchone()[0],
                con.execute("SELECT eps_used_micros FROM main.budget_ledger WHERE course_id='c1'").fetchone()[0],
                con.execute("SELECT count(*) FROM main.audit_log WHERE action LIKE 'statistics.%'").fetchone()[0])


def test_threshold_is_normal_200_without_results_or_charge(staff):
    create_course(staff)
    seed_responses(staff, 3)
    client, _ = login_role(staff)
    response = client.get("/api/courses/c1/statistics")
    assert response.status_code == 200
    assert response.json["data"] == {"state": "unpublished", "reason": "below_threshold",
                                      "sample": 3, "threshold": 5, "shortfall": 2, "charged": False}
    assert publication_counts(staff) == (0, 0, 1)


@pytest.mark.parametrize("role", ["admin", "auditor", "other_teacher"])
def test_statistics_requires_teacher_and_current_ownership(staff, role):
    create_course(staff)
    client = staff["client"] if role == "admin" else login_role(staff, role, "teacher" if role == "other_teacher" else role)[0]
    response = client.get("/api/courses/c1/statistics")
    assert response.status_code == 403
    assert publication_counts(staff)[:2] == (0, 0)


def test_publication_is_bounded_cached_and_never_contains_private_words(staff):
    create_course(staff)
    seed_responses(staff)
    client, _ = login_role(staff)
    first = client.get("/api/courses/c1/statistics")
    assert first.status_code == 200
    data = first.json["data"]
    assert data["state"] == "published" and data["charged"] is True
    assert data["courseCode"] == "c1" and data["courseTitle"] == "数据结构"
    assert data["responses"] == data["enrolled"] == 5
    assert data["publishedAt"].endswith("+08:00")
    assert 1 <= data["pooledMean"] <= 5 and 0 < data["interval"] <= 4
    assert 0 <= data["spread"] <= 4 and type(data["distinguishable"]) is bool
    assert all(1 <= item["value"] <= 5 for item in data["dimensions"])
    assert sum(item["count"] for item in data["distribution"]) == 5
    assert "private-secret" not in str(data)
    again = client.get("/api/courses/c1/statistics").json["data"]
    assert again == {**data, "charged": False}
    assert publication_counts(staff) == (1, 100000, 2)


def test_changed_data_publishes_again_but_exhaustion_returns_last_snapshot(staff):
    create_course(staff)
    seed_responses(staff)
    with staff["db"].transaction() as con:
        con.execute("UPDATE main.budget_ledger SET eps_total_micros=200000")
    client, _ = login_role(staff)
    first = client.get("/api/courses/c1/statistics").json["data"]
    seed_responses(staff, 1)
    second = client.get("/api/courses/c1/statistics").json["data"]
    assert second["publicationId"] != first["publicationId"]
    assert second["responses"] == 6 and second["budgetExhausted"] is True
    seed_responses(staff, 1)
    assert client.get("/api/courses/c1/statistics").json["data"] == {**second, "charged": False}
    assert publication_counts(staff) == (2, 200000, 3)


def test_policy_revision_creates_new_publication(staff):
    create_course(staff)
    seed_responses(staff)
    client, _ = login_role(staff)
    first = client.get("/api/courses/c1/statistics").json["data"]
    with staff["db"].transaction() as con:
        con.execute("UPDATE main.privacy_policy SET epsilon_micros=200000,revision=revision+1")
    second = client.get("/api/courses/c1/statistics").json["data"]
    assert second["publicationId"] != first["publicationId"]
    assert publication_counts(staff)[:2] == (2, 300000)


def test_exhausted_legacy_budget_without_snapshot_does_not_fabricate_results(staff):
    create_course(staff)
    seed_responses(staff)
    with staff["db"].transaction() as con:
        con.execute("UPDATE main.budget_ledger SET eps_used_micros=eps_total_micros")
    client, _ = login_role(staff)
    data = client.get("/api/courses/c1/statistics").json["data"]
    assert data == {"state": "unpublished", "reason": "budget_exhausted", "sample": 5,
                    "threshold": 5, "shortfall": 0, "charged": False}
    assert publication_counts(staff)[:2] == (0, 4000000)


def test_publication_failure_rolls_back_budget_cache_and_audit(staff):
    create_course(staff)
    seed_responses(staff)
    with staff["db"].transaction() as con:
        con.execute("CREATE TRIGGER main.fail_publish BEFORE INSERT ON agg_result BEGIN SELECT RAISE(ABORT,'test'); END")
    client, _ = login_role(staff)
    response = client.get("/api/courses/c1/statistics")
    assert response.status_code == 503
    assert publication_counts(staff) == (0, 0, 0)


def test_concurrent_reads_publish_and_charge_once(staff):
    create_course(staff)
    seed_responses(staff)
    token, _ = staff["auth"].login("teacher", "Workflow-password-2026!")
    barrier = Barrier(2)
    def request():
        client = staff["app"].test_client()
        client.set_cookie("taces_session", token, path="/api")
        barrier.wait()
        response = client.get("/api/courses/c1/statistics")
        assert response.status_code == 200
        return response.json["data"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = list(pool.map(lambda _: request(), range(2)))
    assert a["publicationId"] == b["publicationId"]
    assert sorted([a["charged"], b["charged"]]) == [False, True]
    assert publication_counts(staff) == (1, 100000, 2)
