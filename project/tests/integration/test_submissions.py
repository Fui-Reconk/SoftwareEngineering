from concurrent.futures import ThreadPoolExecutor
import json
from threading import Barrier

import pytest

from tests.workflow_support import staff, create_course, issue_codes


def valid_body(code):
    return {"code": code, "ratings": [{"dimension": name, "score": score} for name, score in
            (("教学内容", 4), ("教学方法", 5), ("考核方式", 3))], "openText": "作业反馈很清晰"}


def counts(staff):
    with staff["db"].read_current() as con:
        return (con.execute("SELECT sum(used_flag) FROM identity.enroll_code").fetchone()[0],
                con.execute("SELECT count(*) FROM evaluation.rating").fetchone()[0],
                con.execute("SELECT count(*) FROM evaluation.open_text").fetchone()[0],
                con.execute("SELECT data_version FROM main.course_state WHERE course_id='c1'").fetchone()[0],
                con.execute("SELECT count(*) FROM main.audit_log").fetchone()[0])


def test_anonymous_verify_does_not_consume_code_or_need_csrf(staff):
    create_course(staff)
    code = issue_codes(staff)[0]
    before = counts(staff)
    client = staff["app"].test_client()
    for _ in range(2):
        response = client.post("/api/evaluation-codes/verify", json={"code": code.upper()})
        assert response.status_code == 200
        assert response.json["data"] == {"valid": True, "course": {"code": "c1", "title": "数据结构", "teacher": "teacher",
            "dimensions": [{"name": "教学内容"}, {"name": "教学方法"}, {"name": "考核方式"}]}}
    assert counts(staff) == before


@pytest.mark.parametrize("code", ["a" * 32, "bad", "", None, 5, "\ud800" * 32])
def test_unknown_and_malformed_codes_return_invalid_without_writes(staff, code):
    create_course(staff)
    issue_codes(staff)
    before = counts(staff)
    response = staff["app"].test_client().post("/api/evaluation-codes/verify", data=json.dumps({"code": code}), content_type="application/json")
    assert response.status_code == 200
    assert response.json["data"] == {"valid": False, "reason": "unknown"}
    assert counts(staff) == before


def test_submission_is_anonymous_atomic_and_consumes_once(staff):
    create_course(staff)
    code = issue_codes(staff)[0]
    before = counts(staff)
    client = staff["app"].test_client()
    response = client.post("/api/submissions", json=valid_body(code))
    assert response.status_code == 201
    submission_id = response.json["data"]["submissionId"]
    after = counts(staff)
    assert after[:4] == (1, 3, 1, 1)
    assert after[4] == before[4], "Anonymous operations must not write individual audit timestamps"
    with staff["db"].read_current() as con:
        assert {row[0] for row in con.execute("SELECT submission_id FROM evaluation.rating")} == {submission_id}
        assert con.execute("SELECT content FROM evaluation.open_text").fetchone()[0] == valid_body(code)["openText"]
        for table in ("enroll_code", "code_state"):
            assert "submission_id" not in {row[1] for row in con.execute(f"PRAGMA identity.table_info({table})")}
    assert client.post("/api/submissions", json=valid_body(code)).status_code == 409
    assert client.post("/api/evaluation-codes/verify", json={"code": code}).json["data"] == {"valid": False, "reason": "used"}
    assert counts(staff) == after


@pytest.mark.parametrize("ratings", [[], [{"dimension": "教学内容", "score": 4}],
    [{"dimension": name, "score": 4} for name in ("教学内容", "教学内容", "考核方式")],
    [{"dimension": name, "score": 4} for name in ("教学内容", "教学方法", "unknown")]])
def test_incomplete_duplicate_unknown_dimensions_do_not_consume(staff, ratings):
    create_course(staff)
    code = issue_codes(staff)[0]
    before = counts(staff)
    response = staff["app"].test_client().post("/api/submissions", json={**valid_body(code), "ratings": ratings})
    assert response.status_code == 400
    assert counts(staff) == before


@pytest.mark.parametrize("score", [0, 6, True, 4.0, "4", None])
def test_invalid_score_does_not_consume(staff, score):
    create_course(staff)
    code = issue_codes(staff)[0]
    body = valid_body(code)
    body["ratings"][0]["score"] = score
    before = counts(staff)
    assert staff["app"].test_client().post("/api/submissions", json=body).status_code == 400
    assert counts(staff) == before


@pytest.mark.parametrize("text", ["x"*501, None, "bad\ud800"])
def test_invalid_open_text_does_not_consume(staff, text):
    create_course(staff)
    code = issue_codes(staff)[0]
    before = counts(staff)
    response = staff["app"].test_client().post("/api/submissions", data=json.dumps({**valid_body(code), "openText": text}), content_type="application/json")
    assert response.status_code == 400
    assert counts(staff) == before


def test_optional_text_can_be_omitted(staff):
    create_course(staff)
    code = issue_codes(staff)[0]
    body = valid_body(code)
    body.pop("openText")
    assert staff["app"].test_client().post("/api/submissions", json=body).status_code == 201
    assert counts(staff)[:4] == (1, 3, 0, 1)


def test_closed_window_does_not_consume_code(staff):
    create_course(staff)
    code = issue_codes(staff)[0]
    staff["client"].patch("/api/admin/courses/c1", json={"closes_at": 0}, headers=staff["headers"])
    before = counts(staff)
    client = staff["app"].test_client()
    assert client.post("/api/evaluation-codes/verify", json={"code": code}).json["data"] == {"valid": False, "reason": "expired"}
    response = client.post("/api/submissions", json=valid_body(code))
    assert response.status_code == 409
    assert response.json["error"]["code"] == "WINDOW_CLOSED"
    assert counts(staff) == before


def test_evaluation_insert_failure_rolls_back_consumption_and_version(staff):
    create_course(staff)
    code = issue_codes(staff)[0]
    before = counts(staff)
    with staff["db"].transaction() as con:
        con.execute("CREATE TRIGGER evaluation.inject_failure BEFORE INSERT ON rating BEGIN SELECT RAISE(ABORT,'injected'); END;")
    client = staff["app"].test_client()
    assert client.post("/api/submissions", json=valid_body(code)).status_code == 503
    assert counts(staff) == before
    with staff["db"].transaction() as con:
        con.execute("DROP TRIGGER evaluation.inject_failure")
    assert client.post("/api/submissions", json=valid_body(code)).status_code == 201


def test_concurrent_submissions_have_one_winner(staff):
    create_course(staff)
    code = issue_codes(staff)[0]
    gate = Barrier(2)
    def submit():
        client = staff["app"].test_client()
        gate.wait(timeout=5)
        response = client.post("/api/submissions", json=valid_body(code))
        return response.status_code, response.json
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit) for _ in range(2)]
        results = [future.result(timeout=15) for future in futures]
    assert sorted(result[0] for result in results) == [201, 409]
    assert counts(staff)[:4] == (1, 3, 1, 1)


@pytest.mark.parametrize("text", ["\x00", "\x00文字"])
def test_nul_text_is_input_error_not_retryable_storage_error(staff, text):
    create_course(staff)
    code = issue_codes(staff)[0]
    before = counts(staff)
    response = staff["app"].test_client().post("/api/submissions", json={**valid_body(code), "openText": text})
    assert response.status_code == 400
    assert response.json["error"]["code"] == "INVALID_INPUT"
    assert counts(staff) == before


def test_individual_code_expiry_is_enforced_before_course_deadline(staff, monkeypatch):
    import taces.business.submission.service as module
    create_course(staff)
    deadline = module.now() + 10
    result = staff["client"].post("/api/admin/courses/c1/evaluation-codes", json={"count": 1, "expires_at": deadline}, headers=staff["headers"])
    assert result.status_code == 201
    code = result.json["data"]["codes"][0]
    monkeypatch.setattr(module, "now", lambda: deadline)
    before = counts(staff)
    client = staff["app"].test_client()
    assert client.post("/api/evaluation-codes/verify", json={"code": code}).json["data"] == {"valid": False, "reason": "expired"}
    response = client.post("/api/submissions", json=valid_body(code))
    assert response.status_code == 409
    assert response.json["error"]["code"] == "WINDOW_CLOSED"
    assert counts(staff) == before
