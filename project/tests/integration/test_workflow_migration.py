import sqlite3

import pytest

import taces.data.database as storage
from taces.data.database import Database, SCHEMA_VERSION


def test_version_two_upgrades_without_changing_core_rows(tmp_path):
    database = Database(tmp_path / "legacy")
    with database._connect(create=True) as connection:
        for filename in ("metadata.sql", "identity.sql", "evaluation.sql", "auth.sql"):
            connection.executescript((storage.SCHEMA_DIR / filename).read_text(encoding="utf-8"))
        for schema in ("main", "identity", "evaluation"):
            connection.execute(f"PRAGMA {schema}.user_version=2")
        connection.execute("INSERT INTO main.course VALUES ('c1','old','t1','2026')")
        connection.execute("INSERT INTO main.audit_log(log_id,actor,action) VALUES ('a','actor','old')")
        connection.execute("INSERT INTO identity.enroll_code VALUES (?, 'c1',0)", ("a"*64,))
    database.upgrade()
    assert SCHEMA_VERSION == 3
    database.check_ready()
    with database.read_current() as connection:
        assert tuple(connection.execute("SELECT * FROM main.course").fetchone()) == ("c1","old","t1","2026")
        assert connection.execute("SELECT action FROM main.audit_log").fetchone()[0] == "old"
        assert connection.execute("SELECT closes_at FROM main.course_state").fetchone()[0] == 0
        assert connection.execute("SELECT expires_at FROM identity.code_state").fetchone()[0] == 0
    database.upgrade()


def test_failed_workflow_ddl_rolls_back_new_auth_tables_and_versions(tmp_path, monkeypatch):
    database = Database(tmp_path / "data")
    schema = tmp_path / "schema"
    schema.mkdir()
    for source in storage.SCHEMA_DIR.glob("*.sql"):
        text = source.read_text(encoding="utf-8")
        if source.name == "workflow.sql":
            text += "\nINVALID SQL STATEMENT;\n"
        (schema / source.name).write_text(text, encoding="utf-8")
    monkeypatch.setattr(storage, "SCHEMA_DIR", schema)
    with pytest.raises(sqlite3.OperationalError):
        database.initialize()
    for _, path in database.paths.items():
        with sqlite3.connect(path) as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
            assert connection.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0] == 0
