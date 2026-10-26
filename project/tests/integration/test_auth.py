"""Local integration checks for account sessions, role boundaries, and revocation."""

import json

import pytest


PASSWORD = "Initial-password-2026!"
NEW_PASSWORD = "Changed-password-2026!"
LOGIN_HEADERS = {"X-TACES-Request": "1"}
SAFE_ACCOUNT_KEYS = {"user_id", "username", "role", "is_active", "created_at"}


def login(client, username="admin", password=PASSWORD, **kwargs):
    return client.post(
        "/api/auth/login", json={"username": username, "password": password},
        headers=LOGIN_HEADERS, **kwargs,
    )


def assert_safe_account(account):
    assert set(account) == SAFE_ACCOUNT_KEYS
    assert isinstance(account["is_active"], bool)
    assert account["user_id"]
    assert account["created_at"]


@pytest.fixture
def admin(app, database):
    account = app.extensions["taces_auth"].bootstrap_admin("admin", PASSWORD)
    assert_safe_account(account)
    assert account["role"] == "admin"
    return account


@pytest.fixture
def admin_client(app, admin):
    client = app.test_client()
    response = login(client)
    assert response.status_code == 200, response.get_json()
    return client, {"X-CSRF-Token": response.get_json()["data"]["csrf_token"]}


def create_account(admin_client, username="teacher", role="teacher"):
    client, headers = admin_client
    response = client.post(
        "/api/admin/accounts", headers=headers,
        json={"username": username, "password": PASSWORD, "role": role},
    )
    assert response.status_code == 201, response.get_json()
    account = response.get_json()["data"]["account"]
    assert_safe_account(account)
    return account


def test_bootstrap_cli_creates_only_first_admin_and_hides_password(app, database):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["create-admin", "--username", "admin"], input=f"{PASSWORD}\n{PASSWORD}\n")
    assert result.exit_code == 0, result.output
    assert PASSWORD not in result.output
    duplicate = runner.invoke(args=["create-admin", "--username", "second"], input=f"{PASSWORD}\n{PASSWORD}\n")
    assert duplicate.exit_code != 0
    assert PASSWORD not in duplicate.output
    assert login(app.test_client()).status_code == 200
    assert login(app.test_client(), "second").status_code == 401


def test_login_returns_safe_account_and_protected_cookie(app, admin):
    client = app.test_client()
    response = login(client)
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert set(data) == {"account", "csrf_token", "expires_at"}
    assert_safe_account(data["account"])
    assert data["account"] == admin
    assert data["csrf_token"]
    assert data["expires_at"]
    cookie = response.headers["Set-Cookie"]
    assert "taces_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Strict" in cookie
    assert "Cache-Control" in response.headers and "no-store" in response.headers["Cache-Control"]
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.get_json()["data"] == data


def test_secure_cookie_configuration_is_honored(app, admin):
    app.config["AUTH_COOKIE_SECURE"] = True
    response = login(app.test_client())
    assert response.status_code == 200
    assert "Secure" in response.headers["Set-Cookie"]


@pytest.mark.parametrize("path", ["/api/auth/me", "/api/admin/accounts", "/api/courses", "/api/courses/missing"])
def test_private_reads_require_login(app, database, path):
    response = app.test_client().get(path)
    assert response.status_code == 401
    assert "error" in response.get_json()


@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/auth/logout", {}),
    ("post", "/api/auth/password", {"current_password": PASSWORD, "new_password": NEW_PASSWORD}),
    ("post", "/api/admin/accounts", {"username": "teacher", "password": PASSWORD, "role": "teacher"}),
    ("patch", "/api/admin/accounts/missing", {"is_active": False}),
])
def test_private_mutations_require_login(app, database, method, path, body):
    response = getattr(app.test_client(), method)(path, json=body, headers={"X-CSRF-Token": "invented"})
    assert response.status_code == 401


@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/auth/logout", {}),
    ("post", "/api/auth/password", {"current_password": PASSWORD, "new_password": NEW_PASSWORD}),
    ("post", "/api/admin/accounts", {"username": "teacher", "password": PASSWORD, "role": "teacher"}),
    ("patch", "/api/admin/accounts/missing", {"is_active": False}),
])
@pytest.mark.parametrize("headers", [{}, {"X-CSRF-Token": "wrong-token"}])
def test_authenticated_mutations_require_valid_csrf(admin_client, method, path, body, headers):
    client, _ = admin_client
    response = getattr(client, method)(path, json=body, headers=headers)
    assert response.status_code == 403
    assert client.get("/api/auth/me").status_code == 200


def test_login_rejects_missing_custom_header_cross_origin_and_form(app, admin):
    client = app.test_client()
    body = {"username": "admin", "password": PASSWORD}
    assert client.post("/api/auth/login", json=body).status_code == 403
    assert client.post(
        "/api/auth/login", json=body,
        headers={**LOGIN_HEADERS, "Origin": "https://untrusted.example"},
    ).status_code == 403
    assert client.post("/api/auth/login", data=body, headers=LOGIN_HEADERS).status_code in {400, 403, 415}
    assert client.get("/api/auth/me").status_code == 401
    assert client.post(
        "/api/auth/login", json=body,
        headers={**LOGIN_HEADERS, "Origin": "http://localhost"},
    ).status_code == 200


def test_logout_revokes_cookie_even_when_replayed(app, admin_client):
    client, headers = admin_client
    session_cookie = client.get_cookie("taces_session", path="/api").value
    response = client.post("/api/auth/logout", headers=headers)
    assert response.status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    replay = app.test_client()
    replay.set_cookie("taces_session", session_cookie, path="/api")
    assert replay.get("/api/auth/me").status_code == 401


def test_relogin_rotates_token_and_revokes_previous_cookie(app, admin_client):
    client, headers = admin_client
    previous_token = client.get_cookie("taces_session", path="/api").value
    response = login(client)
    assert response.status_code == 200
    assert client.get_cookie("taces_session", path="/api").value != previous_token
    assert response.get_json()["data"]["csrf_token"] != headers["X-CSRF-Token"]
    assert client.get("/api/auth/me").status_code == 200
    replay = app.test_client()
    replay.set_cookie("taces_session", previous_token, path="/api")
    assert replay.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize("role", ["teacher", "auditor"])
def test_non_admin_roles_cannot_manage_accounts(app, admin_client, role):
    account = create_account(admin_client, username=role, role=role)
    client = app.test_client()
    response = login(client, role)
    assert response.status_code == 200
    csrf = {"X-CSRF-Token": response.get_json()["data"]["csrf_token"]}
    assert client.get("/api/admin/accounts").status_code == 403
    assert client.post(
        "/api/admin/accounts", headers=csrf,
        json={"username": "newuser", "password": PASSWORD, "role": "teacher"},
    ).status_code == 403
    assert client.patch(
        f"/api/admin/accounts/{account['user_id']}", headers=csrf, json={"role": "admin"},
    ).status_code == 403


def test_admin_can_list_accounts_but_not_password_hashes(admin_client):
    create_account(admin_client, "teacher", "teacher")
    create_account(admin_client, "auditor", "auditor")
    response = admin_client[0].get("/api/admin/accounts")
    assert response.status_code == 200
    accounts = response.get_json()["data"]["accounts"]
    assert {account["username"] for account in accounts} == {"admin", "teacher", "auditor"}
    for account in accounts:
        assert_safe_account(account)


def test_duplicate_username_is_conflict_without_overwriting_account(admin_client):
    original = create_account(admin_client)
    client, headers = admin_client
    response = client.post(
        "/api/admin/accounts", headers=headers,
        json={"username": "teacher", "password": NEW_PASSWORD, "role": "admin"},
    )
    assert response.status_code == 409
    accounts = client.get("/api/admin/accounts").get_json()["data"]["accounts"]
    assert next(account for account in accounts if account["username"] == "teacher") == original


@pytest.mark.parametrize("change", [{"is_active": False}, {"role": "teacher"}, {"role": "auditor", "is_active": False}])
def test_last_active_admin_cannot_be_removed(admin_client, admin, change):
    client, headers = admin_client
    response = client.patch(f"/api/admin/accounts/{admin['user_id']}", headers=headers, json=change)
    assert response.status_code == 409
    assert client.get("/api/auth/me").get_json()["data"]["account"] == admin


def test_active_second_admin_allows_disabling_first(app, admin_client, admin):
    create_account(admin_client, username="admin_two", role="admin")
    client, headers = admin_client
    response = client.patch(
        f"/api/admin/accounts/{admin['user_id']}", headers=headers, json={"is_active": False},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["account"]["is_active"] is False
    assert client.get("/api/auth/me").status_code == 401
    second = app.test_client()
    assert login(second, "admin_two").status_code == 200
    assert second.get("/api/admin/accounts").status_code == 200


def test_disabled_second_admin_does_not_satisfy_last_admin_rule(admin_client, admin):
    second = create_account(admin_client, username="admin_two", role="admin")
    client, headers = admin_client
    assert client.patch(
        f"/api/admin/accounts/{second['user_id']}", headers=headers, json={"is_active": False},
    ).status_code == 200
    assert client.patch(
        f"/api/admin/accounts/{admin['user_id']}", headers=headers, json={"role": "teacher"},
    ).status_code == 409


@pytest.mark.parametrize("change", [{"is_active": False}, {"role": "auditor"}, {"password": NEW_PASSWORD}])
def test_administrative_security_changes_revoke_existing_sessions(app, admin_client, change):
    account = create_account(admin_client)
    first, second = app.test_client(), app.test_client()
    assert login(first, "teacher").status_code == 200
    assert login(second, "teacher").status_code == 200
    token = first.get_cookie("taces_session", path="/api").value
    client, headers = admin_client
    response = client.patch(f"/api/admin/accounts/{account['user_id']}", headers=headers, json=change)
    assert response.status_code == 200
    assert_safe_account(response.get_json()["data"]["account"])
    assert first.get("/api/auth/me").status_code == 401
    assert second.get("/api/auth/me").status_code == 401
    replay = app.test_client()
    replay.set_cookie("taces_session", token, path="/api")
    assert replay.get("/api/auth/me").status_code == 401
    fresh_password = NEW_PASSWORD if "password" in change else PASSWORD
    fresh = login(replay, "teacher", fresh_password)
    assert fresh.status_code == (401 if change.get("is_active") is False else 200)
    if "password" in change:
        assert login(app.test_client(), "teacher", PASSWORD).status_code == 401


def test_password_change_requires_current_password_and_revokes_all_sessions(app, admin_client):
    create_account(admin_client)
    first, second = app.test_client(), app.test_client()
    first_login = login(first, "teacher")
    assert login(second, "teacher").status_code == 200
    headers = {"X-CSRF-Token": first_login.get_json()["data"]["csrf_token"]}
    wrong = first.post(
        "/api/auth/password", headers=headers,
        json={"current_password": "incorrect", "new_password": NEW_PASSWORD},
    )
    assert wrong.status_code == 403
    assert first.get("/api/auth/me").status_code == 200
    response = first.post(
        "/api/auth/password", headers=headers,
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 200
    assert first.get("/api/auth/me").status_code == 401
    assert second.get("/api/auth/me").status_code == 401
    assert login(app.test_client(), "teacher", PASSWORD).status_code == 401
    assert login(app.test_client(), "teacher", NEW_PASSWORD).status_code == 200


def test_login_failures_do_not_disclose_missing_wrong_password_or_disabled_accounts(app, admin_client):
    teacher = create_account(admin_client)
    create_account(admin_client, "active_teacher")
    client, headers = admin_client
    assert client.patch(
        f"/api/admin/accounts/{teacher['user_id']}", headers=headers, json={"is_active": False},
    ).status_code == 200
    responses = [
        login(app.test_client(), "missing_user"),
        login(app.test_client(), "active_teacher", "incorrect"),
        login(app.test_client(), "teacher"),
    ]
    assert [response.status_code for response in responses] == [401, 401, 401]
    assert responses[0].get_json() == responses[1].get_json() == responses[2].get_json()


def test_login_throttle_persists_across_clients_and_expires(app, admin, monkeypatch):
    now = [2_000_000_000.0]
    monkeypatch.setattr("taces.business.auth.service.time.time", lambda: now[0])
    for _ in range(5):
        assert login(app.test_client(), password="incorrect").status_code == 401
    blocked = login(app.test_client())
    assert blocked.status_code == 429
    now[0] += 901
    assert login(app.test_client()).status_code == 200


def test_session_expires_at_absolute_lifetime_without_sliding(app, admin, monkeypatch):
    now = [2_000_000_000.0]
    monkeypatch.setattr("taces.business.auth.service.time.time", lambda: now[0])
    client = app.test_client()
    assert login(client).status_code == 200
    now[0] += 28_799
    assert client.get("/api/auth/me").status_code == 200
    now[0] += 1
    assert client.get("/api/auth/me").status_code == 401


def test_csrf_token_is_bound_to_session(app, admin):
    first, second = app.test_client(), app.test_client()
    first_token = login(first).get_json()["data"]["csrf_token"]
    second_token = login(second).get_json()["data"]["csrf_token"]
    assert first_token != second_token
    assert second.post("/api/auth/logout", headers={"X-CSRF-Token": first_token}).status_code == 403
    assert second.get("/api/auth/me").status_code == 200


@pytest.mark.parametrize("body", [
    [], None, {"username": "admin"}, {"username": ["admin"], "password": PASSWORD},
    {"username": "admin", "password": 123456},
    {"username": "admin", "password": PASSWORD, "role": "admin"},
])
def test_login_rejects_invalid_json_shapes_and_extra_fields(app, admin, body):
    response = app.test_client().post(
        "/api/auth/login", data=json.dumps(body), content_type="application/json", headers=LOGIN_HEADERS,
    )
    assert response.status_code == 400


@pytest.mark.parametrize("overrides", [
    {"username": ""}, {"username": ["teacher"]}, {"password": "short"},
    {"password": None}, {"role": "student"}, {"role": ["admin"]},
    {"is_active": True}, {"user_id": "chosen"},
])
def test_account_creation_validates_types_roles_and_extra_fields(admin_client, overrides):
    client, headers = admin_client
    body = {"username": "teacher", "password": PASSWORD, "role": "teacher", **overrides}
    response = client.post("/api/admin/accounts", headers=headers, json=body)
    assert response.status_code == 400
    assert len(client.get("/api/admin/accounts").get_json()["data"]["accounts"]) == 1


@pytest.mark.parametrize("body", [
    {}, {"is_active": "false"}, {"is_active": 0}, {"role": "student"},
    {"role": None}, {"password": "short"}, {"username": "renamed"}, {"user_id": "forged"},
])
def test_account_updates_validate_types_roles_and_extra_fields(admin_client, body):
    teacher = create_account(admin_client)
    client, headers = admin_client
    response = client.patch(f"/api/admin/accounts/{teacher['user_id']}", headers=headers, json=body)
    assert response.status_code == 400
    accounts = client.get("/api/admin/accounts").get_json()["data"]["accounts"]
    assert next(account for account in accounts if account["user_id"] == teacher["user_id"]) == teacher


def test_updating_missing_account_returns_not_found(admin_client):
    client, headers = admin_client
    response = client.patch("/api/admin/accounts/missing", headers=headers, json={"is_active": False})
    assert response.status_code == 404


def test_course_reads_enforce_teacher_ownership_and_deny_auditors(app, database, admin_client):
    teacher = create_account(admin_client)
    other = create_account(admin_client, "other_teacher")
    create_account(admin_client, "auditor", "auditor")
    with database.transaction() as connection:
        connection.executemany(
            "INSERT INTO main.course (course_id, name, teacher_id, term) VALUES (?, ?, ?, ?)",
            [("c1", "Owned course", teacher["user_id"], "2026"),
             ("c2", "Other course", other["user_id"], "2026")],
        )
    administrator = admin_client[0]
    assert {course["course_id"] for course in administrator.get("/api/courses").get_json()["data"]["courses"]} == {"c1", "c2"}
    assert administrator.get("/api/courses/c2").status_code == 200
    client = app.test_client()
    assert login(client, "teacher").status_code == 200
    response = client.get("/api/courses")
    assert response.status_code == 200
    assert [course["course_id"] for course in response.get_json()["data"]["courses"]] == ["c1"]
    own_course = client.get("/api/courses/c1")
    assert own_course.status_code == 200
    assert own_course.get_json()["data"]["course"]["teacher_id"] == teacher["user_id"]
    assert client.get("/api/courses/c2").status_code == 403
    assert client.get("/api/courses/missing").status_code == 404
    auditor = app.test_client()
    assert login(auditor, "auditor").status_code == 200
    assert auditor.get("/api/courses").status_code == 403
    assert auditor.get("/api/courses/c1").status_code == 403


def test_passwords_and_raw_session_tokens_are_not_stored_or_audited(database, admin_client):
    client, _ = admin_client
    create_account(admin_client)
    raw_token = client.get_cookie("taces_session", path="/api").value
    with database.read() as connection:
        account_rows = connection.execute("SELECT * FROM identity.account").fetchall()
        session_rows = connection.execute("SELECT * FROM identity.auth_session").fetchall()
        audit_rows = connection.execute("SELECT * FROM main.audit_log").fetchall()
        assert account_rows and session_rows and audit_rows
        for rows in (account_rows, session_rows, audit_rows):
            serialized = json.dumps([dict(row) for row in rows])
            assert PASSWORD not in serialized
            assert raw_token not in serialized
        hashes = [row["password_hash"] for row in account_rows]
        assert len(set(hashes)) == len(hashes), "Identical passwords must have independently salted hashes"
        assert all(value != PASSWORD for value in hashes)


@pytest.mark.parametrize("operation", ["login", "create", "update", "current_password", "new_password"])
def test_surrogate_passwords_are_rejected_without_changing_account_or_session_state(
    database, admin, admin_client, operation,
):
    client, csrf_headers = admin_client
    malformed = "prefix-\ud800-suffix"
    if operation == "login":
        method, path, headers = "post", "/api/auth/login", LOGIN_HEADERS
        body = {"username": "admin", "password": malformed}
    elif operation == "create":
        method, path, headers = "post", "/api/admin/accounts", csrf_headers
        body = {"username": "surrogate_user", "password": malformed, "role": "teacher"}
    elif operation == "update":
        method, path, headers = "patch", f"/api/admin/accounts/{admin['user_id']}", csrf_headers
        body = {"password": malformed}
    else:
        method, path, headers = "post", "/api/auth/password", csrf_headers
        body = {"current_password": PASSWORD, "new_password": NEW_PASSWORD}
        body[operation] = malformed

    def state():
        with database.read() as connection:
            return {
                table: [tuple(row) for row in connection.execute(f"SELECT * FROM identity.{table} ORDER BY 1")]
                for table in ("account", "auth_session", "login_throttle")
            }

    original = state()
    # Send JSON escapes on the wire; the app decodes them into lone surrogates.
    response = getattr(client, method)(
        path, data=json.dumps(body), content_type="application/json", headers=headers,
    )
    assert response.status_code == 400
    assert state() == original
    assert client.get("/api/auth/me").get_json()["data"]["account"] == admin
