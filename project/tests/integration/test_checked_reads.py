"""Checked business reads reject damaged storage before returning private data."""

import sqlite3

import pytest

from taces.data.database import CORE_TABLES, Database, SCHEMA_DIR, StorageError


def set_version(database, schema, version):
    with database._connect() as connection:
        connection.execute(f"PRAGMA {schema}.user_version={version}")


def test_data_checked_read_works_and_cannot_write(database):
    with database.read_current() as connection:
        assert connection.execute("SELECT count(*) FROM identity.account").fetchone()[0] == 0
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("INSERT INTO identity.student VALUES ('s1', 'name', 'class')")


@pytest.mark.parametrize("schema", ["main", "identity", "evaluation"])
@pytest.mark.parametrize("version", [0, 1, 99])
def test_data_checked_read_rejects_bad_version_and_releases_locks(database, schema, version):
    set_version(database, schema, version)
    with pytest.raises(StorageError):
        with database.read_current():
            pytest.fail("Invalid schemas must not expose a connection")
    set_version(database, schema, 2)
    with database.transaction() as connection:
        connection.execute("INSERT INTO identity.student VALUES ('s1', 'name', 'class')")
    with database.read_current() as connection:
        assert connection.execute("SELECT name FROM identity.student").fetchone()[0] == "name"


@pytest.mark.parametrize("schema,table", [
    ("main", "course"), ("identity", "login_throttle"), ("evaluation", "open_text"),
])
def test_data_checked_read_rejects_missing_tables(database, schema, table):
    with database._connect() as connection:
        connection.execute(f"DROP TABLE {schema}.{table}")
    with pytest.raises(StorageError):
        with database.read_current():
            pytest.fail("Incomplete schemas must not expose a connection")


def test_data_checked_read_does_not_create_missing_files(tmp_path):
    directory = tmp_path / "missing"
    database = Database(directory)
    with pytest.raises(StorageError):
        with database.read_current():
            pytest.fail("Missing storage must not expose a connection")
    assert not directory.exists()


def test_data_raw_read_can_inspect_real_version_one_without_upgrading(tmp_path):
    database = Database(tmp_path / "legacy")
    with database._connect(create=True) as connection:
        for filename in ("metadata.sql", "identity.sql", "evaluation.sql"):
            connection.executescript((SCHEMA_DIR / filename).read_text(encoding="utf-8"))
        for schema in CORE_TABLES:
            connection.execute(f"PRAGMA {schema}.user_version=1")
    before = {path.name: path.read_bytes() for _, path in database.paths.items()}
    with database.read() as connection:
        for schema, tables in CORE_TABLES.items():
            assert connection.execute(f"PRAGMA {schema}.user_version").fetchone()[0] == 1
            assert {row[0] for row in connection.execute(
                f"SELECT name FROM {schema}.sqlite_master WHERE type='table'"
            )} == tables
    with pytest.raises(StorageError, match="upgrade-db"):
        with database.read_current():
            pytest.fail("Legacy schema must not be exposed to business readers")
    assert {path.name: path.read_bytes() for _, path in database.paths.items()} == before


def test_data_checked_read_closes_connection_after_caller_error(database):
    with pytest.raises(RuntimeError, match="caller failure"):
        with database.read_current() as connection:
            assert connection.execute("SELECT count(*) FROM main.course").fetchone()[0] == 0
            raise RuntimeError("caller failure")
    with database.transaction() as connection:
        connection.execute("INSERT INTO identity.student VALUES ('s1', 'name', 'class')")


@pytest.mark.parametrize("fault", ["mixed_version", "unknown_version", "legacy_version", "missing_table"])
@pytest.mark.parametrize("endpoint", [
    "/api/auth/me", "/api/admin/accounts", "/api/courses", "/api/courses/c1",
])
def test_api_private_reads_refuse_incompatible_schema_without_mutation(app, database, fault, endpoint):
    service = app.extensions["taces_auth"]
    account = service.bootstrap_admin("admin", "Checked-read-password-2026!")
    token, _ = service.login("admin", "Checked-read-password-2026!")
    with database.transaction() as connection:
        connection.execute("INSERT INTO main.course VALUES ('c1', 'course', ?, '2026')", (account["user_id"],))
    healthy_files = {path: path.read_bytes() for _, path in database.paths.items()}
    with database._connect() as connection:
        if fault == "mixed_version":
            connection.execute("PRAGMA main.user_version=99")
        elif fault in {"unknown_version", "legacy_version"}:
            version = 99 if fault == "unknown_version" else 1
            for schema in ("main", "identity", "evaluation"):
                connection.execute(f"PRAGMA {schema}.user_version={version}")
        else:
            connection.execute("DROP TABLE identity.login_throttle")
    damaged_files = {path: path.read_bytes() for _, path in database.paths.items()}
    client = app.test_client()
    client.set_cookie("taces_session", token, path="/api")
    response = client.get(endpoint)
    assert response.status_code == 503
    assert response.json["error"]["code"] == "DATABASE_NOT_READY"
    assert "data" not in response.json
    assert {path: path.read_bytes() for path in damaged_files} == damaged_files
    # Remove only the fault injected into these temporary fixture files. Replaying
    # the original cookie then verifies that a failed read left no connection open.
    for path, original_bytes in healthy_files.items():
        path.write_bytes(original_bytes)
    assert client.get(endpoint).status_code == 200
