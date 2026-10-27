from http.cookiejar import CookieJar
import json
from threading import Thread
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from werkzeug.serving import make_server

from tests.workflow_support import PASSWORD


def test_real_http_admin_student_teacher_auditor_export_flow(app, database):
    app.extensions["taces_auth"].bootstrap_admin("admin", PASSWORD)
    server = make_server("127.0.0.1", 0, app)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    def browser():
        return build_opener(HTTPCookieProcessor(CookieJar()))
    def call(client, path, method="GET", body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(base + path, data=data, method=method,
                      headers={"Content-Type": "application/json", **(headers or {})})
        try:
            response = client.open(req, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            value = json.loads(raw) if response.headers.get_content_type() == "application/json" else raw
            return response.status, value
    def login(client, username):
        status, result = call(client, "/api/auth/login", "POST", {"username": username, "password": PASSWORD}, {"X-TACES-Request": "1"})
        assert status == 200
        return {"X-CSRF-Token": result["data"]["csrf_token"]}
    try:
        admin, student, teacher, auditor = browser(), browser(), browser(), browser()
        headers = login(admin, "admin")
        status, result = call(admin, "/api/admin/accounts", "POST", {"username": "teacher", "password": PASSWORD, "role": "teacher"}, headers)
        assert status == 201
        teacher_id = result["data"]["account"]["user_id"]
        assert call(admin, "/api/admin/accounts", "POST", {"username": "auditor", "password": PASSWORD, "role": "auditor"}, headers)[0] == 201
        status, _ = call(admin, "/api/admin/courses", "POST", {"course_id": "flow", "name": "网络闭环课", "teacher_id": teacher_id, "term": "2026秋"}, headers)
        assert status == 201
        status, result = call(admin, "/api/admin/courses/flow/evaluation-codes", "POST", {"count": 5}, headers)
        assert status == 201
        codes = result["data"]["codes"]
        assert call(student, "/api/evaluation-codes/verify", "POST", {"code": codes[0]})[1]["data"]["valid"] is True
        for code in codes:
            body = {"code": code, "ratings": [{"dimension": name, "score": 4} for name in ("教学内容", "教学方法", "考核方式")], "openText": "反馈清晰"}
            assert call(student, "/api/submissions", "POST", body)[0] == 201
        login(teacher, "teacher")
        status, first = call(teacher, "/api/courses/flow/statistics")
        assert status == 200 and first["data"]["state"] == "published"
        status, again = call(teacher, "/api/courses/flow/statistics")
        assert status == 200 and again["data"] == {**first["data"], "charged": False}
        status, exported = call(teacher, "/api/courses/flow/export?format=csv")
        assert status == 200 and first["data"]["publicationId"].encode() in exported
        login(auditor, "auditor")
        assert call(auditor, "/api/courses")[0] == 403
        status, history = call(auditor, "/api/admin/audit?course=flow")
        assert status == 200 and history["data"]["courses"] == [{"course_id": "flow", "name": "网络闭环课"}]
        assert sum(entry["epsCost"] for entry in history["data"]["entries"]) == .1
        assert any(entry["action"] == "导出CSV" for entry in history["data"]["entries"])
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    assert not thread.is_alive()
