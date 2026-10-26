import sqlite3

import pytest

import taces.data.database as storage
from taces.data.database import CORE_TABLES, Database, SCHEMA_VERSION, StorageError, TABLES


@pytest.fixture
def version_one(tmp_path):
    database = Database(tmp_path / "legacy")
    with database._connect(create=True) as connection:
        for filename in ("metadata.sql", "identity.sql", "evaluation.sql"):
            connection.executescript((storage.SCHEMA_DIR / filename).read_text(encoding="utf-8"))
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("INSERT INTO main.course VALUES ('c1', 'course', 'teacher1', '2026')")
        connection.execute("INSERT INTO main.dimension VALUES ('d1', 'c1', 'dimension', 1.0)")
        connection.execute(
            "INSERT INTO main.budget_ledger VALUES ('b1', 'c1', 1000000, 200000, 'saved-time')"
        )
        connection.execute(
            "INSERT INTO main.audit_log VALUES ('log1', 'teacher1', 'query', 'c1', 'mean', 200000, 'saved-time')"
        )
        connection.execute("INSERT INTO identity.student VALUES ('s1', 'student', 'class')")
        connection.execute("INSERT INTO identity.enroll_code VALUES (?, 'c1', 1)", ("a" * 64,))
        connection.execute("INSERT INTO evaluation.rating VALUES ('r1', 'sub1', 'c1', 'd1', 4)")
        connection.execute("INSERT INTO evaluation.open_text VALUES ('o1', 'r1', 'comment')")
        for schema in CORE_TABLES:
            connection.execute(f"PRAGMA {schema}.user_version = 1")
        connection.commit()
    return database


def core_snapshot(database):
    with database.read() as connection:
        return {
            f"{schema}.{table}": [tuple(row) for row in connection.execute(f"SELECT * FROM {schema}.{table}")]
            for schema, tables in CORE_TABLES.items()
            for table in tables
        }


def versions(database):
    with database.read() as connection:
        return tuple(
            connection.execute(f"PRAGMA {schema}.user_version").fetchone()[0]
            for schema in TABLES
        )


def test_upgrade_preserves_all_eight_core_tables_and_audit_guards(version_one):
    before = core_snapshot(version_one)
    with version_one.read() as connection:
        triggers = [tuple(row) for row in connection.execute(
            "SELECT name, sql FROM main.sqlite_master WHERE type='trigger' ORDER BY name"
        )]
    version_one.upgrade()
    assert core_snapshot(version_one) == before
    assert versions(version_one) == (SCHEMA_VERSION,) * 3
    version_one.check_ready()
    with version_one.read() as connection:
        assert connection.execute("PRAGMA recursive_triggers").fetchone()[0] == 1
        assert [tuple(row) for row in connection.execute(
            "SELECT name, sql FROM main.sqlite_master WHERE type='trigger' ORDER BY name"
        )] == triggers
        for schema, expected in TABLES.items():
            assert {row[0] for row in connection.execute(
                f"SELECT name FROM {schema}.sqlite_master WHERE type='table'"
            )} == expected
        assert {row[1] for row in connection.execute("PRAGMA evaluation.table_info(rating)")} == {
            "rating_id", "submission_id", "course_id", "dim_id", "score"
        }
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with version_one.transaction() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO main.audit_log (log_id, actor, action) "
                "VALUES ('log1', 'replacement', 'changed')"
            )
    assert core_snapshot(version_one) == before


def test_upgrade_and_initialize_are_repeatable_with_current_accounts(version_one):
    version_one.upgrade()
    with version_one.transaction() as connection:
        connection.execute(
            "INSERT INTO identity.account VALUES ('u1', 'admin', 'encoded-password', 'admin', 1, 100)"
        )
        connection.execute("INSERT INTO identity.auth_session VALUES (?, 'u1', 200)", ("b" * 64,))
        connection.execute("INSERT INTO identity.login_throttle VALUES (?, 1, 100)", ("c" * 64,))
    before = core_snapshot(version_one)
    for _ in range(2):
        version_one.upgrade()
        version_one.initialize()
    assert core_snapshot(version_one) == before
    with version_one.read() as connection:
        assert tuple(connection.execute("SELECT * FROM identity.account").fetchone()) == (
            "u1", "admin", "encoded-password", "admin", 1, 100
        )
        assert tuple(connection.execute("SELECT * FROM identity.auth_session").fetchone()) == (
            "b" * 64, "u1", 200
        )
        assert tuple(connection.execute("SELECT * FROM identity.login_throttle").fetchone()) == (
            "c" * 64, 1, 100
        )


@pytest.mark.parametrize("action", ["initialize", "check_ready", "transaction"])
def test_legacy_database_requires_an_explicit_upgrade(version_one, action):
    before = core_snapshot(version_one)
    with pytest.raises(StorageError, match="upgrade-db"):
        if action == "transaction":
            with version_one.transaction():
                pytest.fail("Legacy write transaction must not be exposed")
        else:
            getattr(version_one, action)()
    assert core_snapshot(version_one) == before
    assert versions(version_one) == (1, 1, 1)


@pytest.mark.parametrize("bad_versions", [(99, 99, 99), (2, 1, 1), (0, 1, 1), (0, 0, 0)])
def test_upgrade_rejects_unknown_mixed_and_unversioned_databases(version_one, bad_versions):
    before = core_snapshot(version_one)
    with version_one._connect() as connection:
        for schema, version in zip(TABLES, bad_versions):
            connection.execute(f"PRAGMA {schema}.user_version = {version}")
    with pytest.raises(StorageError, match="incompatible"):
        version_one.upgrade()
    assert core_snapshot(version_one) == before
    assert versions(version_one) == bad_versions
    with version_one.read() as connection:
        assert connection.execute(
            "SELECT name FROM identity.sqlite_master WHERE name='account'"
        ).fetchall() == []


@pytest.mark.parametrize("schema, table", [("main", "budget_ledger"), ("identity", "student"), ("evaluation", "open_text")])
def test_upgrade_rejects_missing_core_table(version_one, schema, table):
    with version_one._connect() as connection:
        connection.execute(f"DROP TABLE {schema}.{table}")
    with pytest.raises(StorageError, match="incompatible"):
        version_one.upgrade()
    assert versions(version_one) == (1, 1, 1)
    with version_one.read() as connection:
        assert connection.execute(
            "SELECT name FROM identity.sqlite_master WHERE name='account'"
        ).fetchall() == []


def test_failed_upgrade_rolls_back_ddl_versions_and_rows_across_all_files(version_one, tmp_path, monkeypatch):
    before = core_snapshot(version_one)
    original_schema_dir = storage.SCHEMA_DIR
    schema_dir = tmp_path / "broken-schema"
    schema_dir.mkdir()
    script = (original_schema_dir / "auth.sql").read_text(encoding="utf-8")
    script += """
PRAGMA main.user_version = 2;
PRAGMA identity.user_version = 2;
PRAGMA evaluation.user_version = 2;
CREATE TABLE main.migration_probe (id INTEGER);
UPDATE identity.enroll_code SET used_flag=0;
UPDATE evaluation.rating SET score=1;
INVALID SQL STATEMENT;
"""
    (schema_dir / "auth.sql").write_text(script, encoding="utf-8")
    monkeypatch.setattr(storage, "SCHEMA_DIR", schema_dir)
    with pytest.raises(sqlite3.OperationalError):
        version_one.upgrade()
    assert versions(version_one) == (1, 1, 1)
    assert core_snapshot(version_one) == before
    with version_one.read() as connection:
        for schema, expected in CORE_TABLES.items():
            assert {row[0] for row in connection.execute(
                f"SELECT name FROM {schema}.sqlite_master WHERE type='table'"
            )} == expected
    monkeypatch.setattr(storage, "SCHEMA_DIR", original_schema_dir)
    version_one.upgrade()
    version_one.check_ready()
    assert core_snapshot(version_one) == before


def test_upgrade_never_creates_missing_database_files(tmp_path):
    database = Database(tmp_path / "missing")
    with pytest.raises(StorageError, match="init-db"):
        database.upgrade()
    assert not database.paths.metadata.parent.exists()


def test_upgrade_rejects_a_conflicting_existing_auth_table(version_one):
    with version_one._connect() as connection:
        connection.execute("CREATE TABLE identity.account (unexpected TEXT)")
        connection.execute("INSERT INTO identity.account VALUES ('keep')")
    with pytest.raises(sqlite3.OperationalError, match="already exists"):
        version_one.upgrade()
    assert versions(version_one) == (1, 1, 1)
    with version_one.read() as connection:
        assert connection.execute("SELECT unexpected FROM identity.account").fetchone()[0] == "keep"


@pytest.mark.parametrize("role", ["admin", "teacher", "auditor"])
def test_new_database_accepts_the_three_staff_roles(database, role):
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO identity.account (user_id, username, password_hash, role, created_at) "
            "VALUES ('u1', 'staff', 'encoded-password', ?, 100)", (role,)
        )
    with database.read() as connection:
        assert tuple(connection.execute("SELECT role, is_active FROM identity.account").fetchone()) == (role, 1)


@pytest.mark.parametrize("role, active", [("student", 1), ("ADMIN", 1), ("admin", 2), ("admin", 0.5)])
def test_account_role_and_active_constraints(database, role, active):
    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            connection.execute(
                "INSERT INTO identity.account VALUES ('u1', 'staff', 'encoded-password', ?, ?, 100)",
                (role, active),
            )


def test_session_requires_an_account_and_is_removed_with_it(database):
    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            connection.execute("INSERT INTO identity.auth_session VALUES (?, 'missing', 200)", ("d" * 64,))
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO identity.account VALUES ('u1', 'admin', 'encoded-password', 'admin', 1, 100)"
        )
        connection.execute("INSERT INTO identity.auth_session VALUES (?, 'u1', 200)", ("d" * 64,))
        connection.execute("DELETE FROM identity.account WHERE user_id='u1'")
    with database.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM identity.auth_session").fetchone()[0] == 0
