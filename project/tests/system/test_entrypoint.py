import os
from pathlib import Path
import subprocess
import sys


def test_flask_cli_entrypoint_works_outside_project_directory(tmp_path):
    project = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment["TACES_DATA_DIR"] = str(tmp_path / "isolated-data")
    result = subprocess.run(
        [sys.executable, "-m", "flask", "--app", str(project / "run.py"), "init-db"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert {p.name for p in (tmp_path / "isolated-data").iterdir()} == {
        "metadata.db", "identity.db", "evaluation.db"
    }
