"""Exercise the delivered fixture generator against real SQLite and HTTP APIs."""

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


PROJECT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT / "scripts" / "generate_test_data.py"


def test_generator_cli_is_available_from_another_working_directory(tmp_path):
    assert SCRIPT.is_file(), "The test-data generator must be delivered"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"], cwd=tmp_path,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "--check" in result.stdout


@pytest.fixture(scope="module")
def generator():
    assert SCRIPT.is_file(), "The test-data generator must be delivered"
    spec = importlib.util.spec_from_file_location("test_data_generator", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def dataset(generator, tmp_path_factory):
    root = tmp_path_factory.mktemp("generated") / "dataset"
    generator.generate_dataset(root, seed=42, performance_rows=10000)
    return root


def load(root, name):
    return json.loads((root / name).read_text(encoding="utf-8"))


def database_hashes(root):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (root / "db").glob("*.db")}


def test_dataset_has_boundary_distribution_and_performance_scenarios(dataset):
    manifest = load(dataset, "manifest.json")
    courses = {c["id"]: c for c in manifest["courses"]}
    assert [courses[key]["responses"] for key in ("empty", "below_k", "at_k", "above_k")] == [0, 4, 5, 6]
    assert courses["performance"]["responses"] == 10000
    assert {"all_low", "all_high", "uniform", "polarized", "weighted", "one_dimension",
            "ten_dimensions", "text_empty", "text_500", "text_special", "budget_empty",
            "budget_last", "cache_exhausted", "stale_cache", "refresh", "closed", "foreign"} <= courses.keys()
    truth = load(dataset, "ground_truth.json")
    assert truth["all_low"]["means"] == [1, 1, 1]
    assert truth["all_high"]["means"] == [5, 5, 5]
    assert truth["uniform"]["histogram"] == [5, 5, 5, 5, 5]
    assert truth["polarized"]["histogram"] == [10, 0, 0, 0, 10]
    assert truth["weighted"]["weighted_mean"] == pytest.approx(1.7)
    assert truth["text_empty"]["text_responses"] == 0
    assert truth["text_500"]["max_text_length"] == 500


def test_generated_databases_are_valid_and_have_no_identity_join(dataset, generator):
    db = generator.Database(dataset / "db")
    with db.read_current() as con:
        for schema in ("main", "identity", "evaluation"):
            assert con.execute(f"PRAGMA {schema}.integrity_check").fetchone()[0] == "ok"
            assert not con.execute(f"PRAGMA {schema}.foreign_key_check").fetchall()
        identity_columns = {r[1] for table in ("enroll_code", "code_state")
                            for r in con.execute(f"PRAGMA identity.table_info({table})")}
        assert "submission_id" not in identity_columns
        evaluation_columns = {r[1] for table in ("rating", "open_text")
                              for r in con.execute(f"PRAGMA evaluation.table_info({table})")}
        assert not evaluation_columns & {"student_id", "user_id", "code_hash", "ip", "created_at"}
        assert con.execute("SELECT count(*) FROM identity.auth_session").fetchone()[0] == 0
        assert con.execute("SELECT count(*) FROM identity.student").fetchone()[0] == 0


def test_generated_http_cases_and_lifecycle_checks_pass_without_consuming_source(dataset, generator):
    before = database_hashes(dataset)
    report = generator.verify_dataset(dataset)
    assert report["failed"] == 0, [c for c in report["checks"] if not c["passed"]]
    assert report["passed"] >= 100
    assert report["performance_seconds"] is not None
    assert before == database_hashes(dataset)


def test_verifier_detects_an_incorrect_ground_truth(dataset, generator, tmp_path):
    import shutil

    copy = tmp_path / "corrupted"
    shutil.copytree(dataset, copy)
    truth = load(copy, "ground_truth.json")
    truth["all_low"]["means"][0] = 2
    (copy / "ground_truth.json").write_text(json.dumps(truth), encoding="utf-8")
    report = generator.verify_dataset(copy)
    assert report["failed"] >= 1
    assert any(not c["passed"] and "all_low" in c["name"] for c in report["checks"])


def test_generator_refuses_existing_directory_without_touching_files(generator, tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "metadata.db"
    sentinel.write_bytes(b"existing database")
    with pytest.raises(FileExistsError):
        generator.generate_dataset(output, performance_rows=0)
    assert sentinel.read_bytes() == b"existing database"
    assert list(output.iterdir()) == [sentinel]


@pytest.mark.parametrize("rows", [-1, 1, 4, True, 1.5])
def test_generator_rejects_invalid_scale_before_creating_output(generator, tmp_path, rows):
    output = tmp_path / "invalid"
    with pytest.raises(ValueError):
        generator.generate_dataset(output, performance_rows=rows)
    assert not output.exists()


def test_seed_reproduces_logical_data_and_zero_disables_performance(generator, tmp_path):
    first, second, third = (tmp_path / name for name in ("first", "second", "third"))
    generator.generate_dataset(first, seed=19, performance_rows=0)
    generator.generate_dataset(second, seed=19, performance_rows=0)
    generator.generate_dataset(third, seed=20, performance_rows=0)
    assert load(first, "ground_truth.json") == load(second, "ground_truth.json")
    assert load(first, "ground_truth.json")["random"] != load(third, "ground_truth.json")["random"]
    assert "performance" not in load(first, "ground_truth.json")


def test_cli_generates_checks_and_returns_failure_for_corruption(tmp_path):
    output = tmp_path / "cli-data"
    command = [sys.executable, str(SCRIPT), "--output", str(output), "--performance-rows", "0", "--check"]
    run = subprocess.run(command, cwd=tmp_path, capture_output=True, timeout=90)
    assert run.returncode == 0, run.stderr.decode("utf-8", errors="replace")
    assert load(output, "verification.json")["failed"] == 0
    truth = load(output, "ground_truth.json")
    truth["at_k"]["responses"] = 99
    (output / "ground_truth.json").write_text(json.dumps(truth), encoding="utf-8")
    run = subprocess.run(
        [sys.executable, str(SCRIPT), "--verify-only", str(output)],
        cwd=tmp_path, capture_output=True, timeout=90,
    )
    assert run.returncode == 1
    assert load(output, "verification.json")["failed"] >= 1


def test_demo_install_preserves_previous_database_in_a_readable_backup(dataset, generator, tmp_path):
    destination = tmp_path / "demo-db"
    existing = generator.Database(destination)
    existing.initialize()
    with existing.transaction() as con:
        con.execute("INSERT INTO main.course VALUES ('original','原有演示课','legacy-teacher','old')")
    before = database_hashes(dataset)
    backup = generator.install_demo(dataset, destination)
    assert backup is not None
    with generator.Database(backup).read_current() as con:
        assert con.execute("SELECT name FROM main.course WHERE course_id='original'").fetchone()[0] == "原有演示课"
    with generator.Database(destination).read_current() as con:
        assert con.execute("SELECT count(*) FROM main.course").fetchone()[0] == 25
        assert con.execute("SELECT count(*) FROM main.course WHERE course_id='original'").fetchone()[0] == 0
    assert database_hashes(dataset) == before


def test_demo_install_refuses_a_partial_database(dataset, generator, tmp_path):
    destination = tmp_path / "partial"
    destination.mkdir()
    sentinel = destination / "identity.db"
    sentinel.write_bytes(b"do not overwrite")
    with pytest.raises(ValueError, match="incomplete"):
        generator.install_demo(dataset, destination)
    assert sentinel.read_bytes() == b"do not overwrite"


def test_demo_install_closes_all_backup_connections(dataset, generator, tmp_path, monkeypatch):
    import sqlite3

    destination = tmp_path / "close-handles"
    generator.Database(destination).initialize()
    connect = sqlite3.connect
    backups = []

    def tracked_connect(path, *args, **kwargs):
        connection = connect(path, *args, **kwargs)
        if "before-demo-" in str(path):
            backups.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    generator.install_demo(dataset, destination)
    assert len(backups) == 3
    for connection in backups:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


def test_demo_install_restores_all_databases_if_copying_fails(dataset, generator, tmp_path, monkeypatch):
    import shutil

    destination = tmp_path / "rollback-db"
    original = generator.Database(destination)
    original.initialize()
    with original.transaction() as con:
        con.execute("INSERT INTO main.course VALUES ('keep','原有课程','old-teacher','old-term')")
        con.execute("INSERT INTO identity.student VALUES ('keep','原有数据','old-class')")
    copy = shutil.copy2
    calls = 0

    def fail_second_copy(source, target, *args, **kwargs):
        nonlocal calls
        if Path(target).parent == destination:
            calls += 1
            if calls == 2:
                raise OSError("injected second-file copy failure")
        return copy(source, target, *args, **kwargs)

    monkeypatch.setattr(shutil, "copy2", fail_second_copy)
    with pytest.raises(OSError, match="injected"):
        generator.install_demo(dataset, destination)
    with original.read_current() as con:
        assert con.execute("SELECT course_id FROM main.course").fetchall()[0][0] == "keep"
        assert con.execute("SELECT student_id FROM identity.student").fetchall()[0][0] == "keep"
        assert con.execute("SELECT count(*) FROM evaluation.rating").fetchone()[0] == 0
        for schema in ("main", "identity", "evaluation"):
            assert con.execute(f"PRAGMA {schema}.integrity_check").fetchone()[0] == "ok"
