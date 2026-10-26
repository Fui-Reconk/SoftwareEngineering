"""Transactions recheck authority and keep security mutations with their audit."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import sqlite3
from threading import Barrier

import pytest

import taces.business.auth.service as auth_module
from taces.business.auth.service import csrf_token
from taces.business.errors import ServiceError


PASSWORD = "Atomicity-password-2026!"
NEW_PASSWORD = "Changed-atomicity-2026!"


@pytest.fixture
def staff(app, database):
    service = app.extensions["taces_auth"]
    administrator = service.bootstrap_admin("admin", PASSWORD)
    admin_token, _ = service.login("admin", PASSWORD)
    teacher = service.create_account(admin_token, "teacher", PASSWORD, "teacher")
    teacher_token, _ = service.login("teacher", PASSWORD)
    return service, administrator, admin_token, teacher, teacher_token


def identity_snapshot(database):
    with database.read() as connection:
        return {
            table: [tuple(row) for row in connection.execute(f"SELECT * FROM identity.{table} ORDER BY 1")]
            for table in ("account", "auth_session", "login_throttle")
        }


def audit_snapshot(database):
    with database.read() as connection:
        return [tuple(row) for row in connection.execute("SELECT * FROM main.audit_log ORDER BY log_id")]


def test_concurrent_administrators_cannot_disable_each_other_and_leave_no_admin(staff, database):
    service, first, first_token, _, _ = staff
    second = service.create_account(first_token, "admin_two", PASSWORD, "admin")
    second_token, _ = service.login("admin_two", PASSWORD)
    gate = Barrier(2)

    def disable(actor_token, target_id):
        gate.wait(timeout=5)
        try:
            service.update_account(actor_token, target_id, {"is_active": False})
            return 200, None
        except ServiceError as error:
            return error.status, error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_result = pool.submit(disable, first_token, second["user_id"])
        second_result = pool.submit(disable, second_token, first["user_id"])
        results = [first_result.result(timeout=15), second_result.result(timeout=15)]
    assert sorted(results, key=lambda result: result[0]) == [(200, None), (401, "UNAUTHENTICATED")]
    with database.read() as connection:
        active = {row[0] for row in connection.execute(
            "SELECT user_id FROM identity.account WHERE role='admin' AND is_active=1"
        )}
        assert len(active) == 1
        assert connection.execute(
            "SELECT count(*) FROM main.audit_log WHERE action LIKE 'account.update:%'"
        ).fetchone()[0] == 1
    for account, raw_token in ((first, first_token), (second, second_token)):
        if account["user_id"] in active:
            assert service.current(raw_token)["account"]["is_active"] is True
        else:
            with pytest.raises(ServiceError) as caught:
                service.current(raw_token)
            assert caught.value.status == 401


@pytest.mark.parametrize("change, expected_status", [({"role": "teacher"}, 403), ({"is_active": 0}, 401)])
def test_authority_is_rechecked_after_http_precheck(staff, app, database, monkeypatch, change, expected_status):
    service, administrator, admin_token, teacher, _ = staff
    service.create_account(admin_token, "backup_admin", PASSWORD, "admin")
    before = identity_snapshot(database)
    original = service.update_account
    reached = []

    def change_actor_then_update(token, user_id, changes):
        # Reaching this method proves protected() already accepted the old session.
        reached.append(user_id)
        with database.transaction() as connection:
            column, value = next(iter(change.items()))
            connection.execute(
                f"UPDATE identity.account SET {column}=? WHERE user_id=?",
                (value, administrator["user_id"]),
            )
        return original(token, user_id, changes)

    monkeypatch.setattr(service, "update_account", change_actor_then_update)
    client = app.test_client()
    client.set_cookie("taces_session", admin_token, path="/api")
    response = client.patch(
        f"/api/admin/accounts/{teacher['user_id']}",
        json={"role": "auditor", "is_active": False},
        headers={"X-CSRF-Token": csrf_token(admin_token)},
    )
    assert reached == [teacher["user_id"]]
    assert response.status_code == expected_status, response.get_json()
    after = identity_snapshot(database)
    assert next(row for row in after["account"] if row[0] == teacher["user_id"]) == next(
        row for row in before["account"] if row[0] == teacher["user_id"]
    )
    assert after["auth_session"] == before["auth_session"]
    with database.read() as connection:
        assert connection.execute(
            "SELECT count(*) FROM main.audit_log WHERE action=?",
            ("account.update:" + teacher["user_id"],),
        ).fetchone()[0] == 0


@pytest.mark.parametrize("operation", ["create", "update", "password", "login", "logout"])
def test_audit_failure_rolls_back_account_and_session_changes(staff, database, monkeypatch, operation):
    service, administrator, admin_token, teacher, teacher_token = staff
    with database.transaction() as connection:
        # Login would clear the throttle and expired session before writing its audit.
        connection.execute(
            "INSERT INTO identity.login_throttle VALUES (?, 1, ?)",
            (hashlib.sha256(b"admin").hexdigest(), int(auth_module.time.time())),
        )
        connection.execute(
            "INSERT INTO identity.auth_session VALUES (?, ?, 1)", ("e" * 64, teacher["user_id"])
        )
    before = identity_snapshot(database)
    audits_before = audit_snapshot(database)

    def failing_audit(connection, actor, action):
        raise sqlite3.OperationalError("injected audit write failure")

    monkeypatch.setattr(auth_module, "audit", failing_audit)
    with pytest.raises(sqlite3.OperationalError, match="injected audit write failure"):
        if operation == "create":
            service.create_account(admin_token, "new_teacher", NEW_PASSWORD, "teacher")
        elif operation == "update":
            service.update_account(admin_token, teacher["user_id"], {
                "role": "auditor", "is_active": False, "password": NEW_PASSWORD,
            })
        elif operation == "password":
            service.change_password(teacher_token, PASSWORD, NEW_PASSWORD)
        elif operation == "login":
            service.login("admin", PASSWORD, previous_token=admin_token)
        else:
            service.logout(teacher_token)
    assert identity_snapshot(database) == before
    assert audit_snapshot(database) == audits_before
    assert service.current(admin_token)["account"] == administrator
    assert service.current(teacher_token)["account"] == teacher


@pytest.mark.parametrize("operation, action", [
    ("list", "accounts.list"), ("create", "accounts.create"), ("update", "accounts.update"),
])
def test_service_forbidden_requests_commit_denial_audit_without_changing_identity(staff, database, operation, action):
    service, administrator, _, teacher, teacher_token = staff
    before = identity_snapshot(database)
    old_audits = {row[0] for row in audit_snapshot(database)}
    with pytest.raises(ServiceError) as caught:
        if operation == "list":
            service.list_accounts(teacher_token)
        elif operation == "create":
            service.create_account(teacher_token, "new_admin", PASSWORD, "admin")
        else:
            service.update_account(teacher_token, administrator["user_id"], {"is_active": False})
    assert (caught.value.status, caught.value.code) == (403, "FORBIDDEN")
    assert identity_snapshot(database) == before
    with database.read() as connection:
        new_rows = [dict(row) for row in connection.execute("SELECT * FROM main.audit_log")
                    if row["log_id"] not in old_audits]
    assert len(new_rows) == 1
    assert new_rows[0]["actor"] == teacher["user_id"]
    assert new_rows[0]["action"] == "access.denied:" + action
