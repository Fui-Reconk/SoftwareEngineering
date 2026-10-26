import sqlite3

import pytest

import taces.data.database as storage
from taces.data.database import Database, SCHEMA_VERSION, StorageError, TABLES


def test_eight_core_tables_are_physically_separated(database):
    assert len({path for _, path in database.paths.items()}) == 3
    with database.read() as connection:
        for schema, expected in TABLES.items():
            tables = {
                row[0] for row in connection.execute(
                    f"SELECT name FROM {schema}.sqlite_master WHERE type='table'"
                )
            }
            assert tables == expected
            assert connection.execute(f"PRAGMA {schema}.user_version").fetchone()[0] == SCHEMA_VERSION
            assert connection.execute(f"PRAGMA {schema}.journal_mode").fetchone()[0] == "delete"
            assert connection.execute(f"PRAGMA {schema}.synchronous").fetchone()[0] == 2
            assert connection.execute(f"PRAGMA {schema}.foreign_key_check").fetchall() == []


def test_initialization_is_repeatable_and_keeps_existing_rows(database):
    with database.transaction() as connection:
        connection.execute("INSERT INTO main.course VALUES (?, ?, ?, ?)", ("c1", "课程", "t1", "2026"))
    database.initialize()
    database.initialize()
    with database.read() as connection:
        assert connection.execute("SELECT name FROM main.course").fetchone()[0] == "课程"


def test_cross_file_transaction_commits_together(database):
    with database.transaction() as connection:
        connection.execute("INSERT INTO identity.enroll_code VALUES (?, ?, ?)", ("a" * 64, "c1", 1))
        connection.execute("INSERT INTO evaluation.rating VALUES (?, ?, ?, ?, ?)", ("r1", "s1", "c1", "d1", 4))
        connection.execute(
            "INSERT INTO main.audit_log (log_id, actor, action) VALUES (?, ?, ?)",
            ("a1", "teacher", "query"),
        )
    with database.read() as connection:
        assert connection.execute("SELECT used_flag FROM identity.enroll_code").fetchone()[0] == 1
        assert connection.execute("SELECT score FROM evaluation.rating").fetchone()[0] == 4
        assert connection.execute("SELECT COUNT(*) FROM main.audit_log").fetchone()[0] == 1


def test_cross_file_transaction_rolls_back_on_failure(database):
    with database.transaction() as connection:
        connection.execute("INSERT INTO identity.enroll_code VALUES (?, ?, ?)", ("a" * 64, "c1", 0))
    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            connection.execute("UPDATE identity.enroll_code SET used_flag=1")
            connection.execute("INSERT INTO evaluation.rating VALUES (?, ?, ?, ?, ?)", ("r1", "s1", "c1", "d1", 4))
            connection.execute(
                "INSERT INTO main.audit_log (log_id, actor, action) VALUES (?, ?, ?)",
                ("a1", "teacher", "query"),
            )
            connection.execute("INSERT INTO evaluation.rating VALUES (?, ?, ?, ?, ?)", ("r2", "s2", "c1", "d1", 6))
    with database.read() as connection:
        assert connection.execute("SELECT used_flag FROM identity.enroll_code").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM evaluation.rating").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM main.audit_log").fetchone()[0] == 0


def test_read_connection_cannot_write(database):
    with database.read() as connection:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("INSERT INTO identity.student VALUES ('s', 'name', 'class')")


def test_evaluation_schema_has_no_individual_identity_link(database):
    forbidden = {"student_id", "code", "code_hash", "used_at", "ip", "user_id", "ts"}
    with database.read() as connection:
        for table in ("rating", "open_text"):
            columns = {row[1] for row in connection.execute(f"PRAGMA evaluation.table_info({table})")}
            assert not columns.intersection(forbidden)
            foreign_tables = {row[2] for row in connection.execute(f"PRAGMA evaluation.foreign_key_list({table})")}
            assert not foreign_tables.intersection({"student", "enroll_code"})


@pytest.mark.parametrize("score", [0, 6, 1.5, "bad"])
def test_database_rejects_invalid_scores(database, score):
    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            connection.execute("INSERT INTO evaluation.rating VALUES (?, ?, ?, ?, ?)", ("r1", "s1", "c1", "d1", score))


def test_foreign_keys_and_submission_dimension_uniqueness_are_enforced(database):
    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            connection.execute("INSERT INTO evaluation.open_text VALUES ('o1', 'missing', 'comment')")
    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            connection.execute("INSERT INTO evaluation.rating VALUES ('r1', 's1', 'c1', 'd1', 4)")
            connection.execute("INSERT INTO evaluation.rating VALUES ('r2', 's1', 'c1', 'd1', 5)")


def test_budget_cannot_be_overdrawn(database):
    with database.transaction() as connection:
        connection.execute("INSERT INTO main.course VALUES ('c1', 'course', 't1', '2026')")
        connection.execute(
            "INSERT INTO main.budget_ledger (ledger_id, course_id, eps_total_micros) VALUES ('b1', 'c1', 100000)"
        )
    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            connection.execute("UPDATE main.budget_ledger SET eps_used_micros=100001")


@pytest.mark.parametrize("statement", ["DELETE FROM main.audit_log", "UPDATE main.audit_log SET actor='changed'"])
def test_audit_is_append_only(database, statement):
    with database.transaction() as connection:
        connection.execute("INSERT INTO main.audit_log (log_id, actor, action) VALUES ('a1', 't1', 'query')")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with database.transaction() as connection:
            connection.execute(statement)


@pytest.mark.parametrize("insert", ["INSERT OR REPLACE INTO", "REPLACE INTO"])
@pytest.mark.parametrize("conflict", ["log_id", "rowid"])
def test_audit_replace_is_rejected_and_transaction_is_rolled_back(database, insert, conflict):
    with database.transaction() as connection:
        connection.execute("INSERT INTO identity.enroll_code VALUES (?, 'c1', 0)", ("a" * 64,))
        connection.execute(
            "INSERT INTO main.audit_log (log_id, actor, action, eps_cost_micros, ts) "
            "VALUES ('a1', 'original', 'query', 100000, '2026-10-20T00:00:00Z')"
        )
        original = tuple(connection.execute("SELECT rowid, * FROM main.audit_log").fetchone())

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with database.transaction() as connection:
            connection.execute("UPDATE identity.enroll_code SET used_flag=1")
            connection.execute("INSERT INTO evaluation.rating VALUES ('r1', 's1', 'c1', 'd1', 4)")
            connection.execute("INSERT INTO main.course VALUES ('c1', 'course', 't1', '2026')")
            if conflict == "log_id":
                connection.execute(
                    f"{insert} main.audit_log (log_id, actor, action) "
                    "VALUES ('a1', 'replacement', 'replace')"
                )
            else:
                connection.execute(
                    f"{insert} main.audit_log (rowid, log_id, actor, action) "
                    "VALUES (?, 'a2', 'replacement', 'replace')",
                    (original[0],),
                )

    with database.read() as connection:
        rows = [tuple(row) for row in connection.execute("SELECT rowid, * FROM main.audit_log")]
        assert rows == [original]
        assert connection.execute("SELECT used_flag FROM identity.enroll_code").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM evaluation.rating").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM main.course").fetchone()[0] == 0


@pytest.mark.parametrize("insert", ["INSERT OR REPLACE INTO", "REPLACE INTO"])
def test_audit_replace_syntax_can_append_without_a_conflict(database, insert):
    with database.transaction() as connection:
        connection.execute("INSERT INTO main.audit_log (log_id, actor, action) VALUES ('a1', 't1', 'query')")
    with database.transaction() as connection:
        connection.execute(
            f"{insert} main.audit_log (log_id, actor, action) VALUES ('a2', 't2', 'query')"
        )
    with database.read() as connection:
        assert [tuple(row) for row in connection.execute(
            "SELECT log_id, actor FROM main.audit_log ORDER BY log_id"
        )] == [("a1", "t1"), ("a2", "t2")]


def test_missing_database_is_not_created_by_readiness(tmp_path):
    directory = tmp_path / "missing"
    with pytest.raises(StorageError):
        Database(directory).check_ready()
    assert not directory.exists()


def test_unknown_version_is_refused_without_changing_data(database):
    connection = sqlite3.connect(database.paths.metadata)
    connection.execute("PRAGMA user_version=99")
    connection.close()
    with pytest.raises(StorageError, match="incompatible"):
        database.initialize()
    connection = sqlite3.connect(database.paths.metadata)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 99
    connection.close()


def test_unversioned_existing_database_is_not_adopted(tmp_path):
    database = Database(tmp_path)
    connection = sqlite3.connect(database.paths.metadata)
    connection.execute("CREATE TABLE unrelated (id INTEGER)")
    connection.close()
    with pytest.raises(StorageError):
        database.initialize()
    connection = sqlite3.connect(database.paths.metadata)
    assert connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [("unrelated",)]
    connection.close()


def test_wal_is_refused_instead_of_silently_breaking_cross_file_atomicity(database):
    connection = sqlite3.connect(database.paths.evaluation)
    assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    connection.close()
    with pytest.raises(StorageError, match="DELETE"):
        database.initialize()


def test_failed_schema_initialization_rolls_back_all_files(tmp_path, monkeypatch):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    original_schema_dir = storage.SCHEMA_DIR
    for source in original_schema_dir.glob("*.sql"):
        text = source.read_text(encoding="utf-8")
        if source.name == "evaluation.sql":
            text += "\nINVALID SQL STATEMENT;\n"
        (schema_dir / source.name).write_text(text, encoding="utf-8")
    monkeypatch.setattr(storage, "SCHEMA_DIR", schema_dir)
    database = Database(tmp_path / "data")
    with pytest.raises(sqlite3.OperationalError):
        database.initialize()
    for _, path in database.paths.items():
        connection = sqlite3.connect(path)
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
        connection.close()
    monkeypatch.setattr(storage, "SCHEMA_DIR", original_schema_dir)
    database.initialize()
    database.check_ready()
