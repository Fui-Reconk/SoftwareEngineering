import math
import pytest

from taces import create_app
from taces.config import PROJECT_DIR, load_config


def test_factory_and_health_have_no_filesystem_side_effects(tmp_path):
    directory = tmp_path / "not-created"
    app = create_app({"TESTING": True, "DATA_DIR": directory})
    assert app.test_client().get("/api/health").status_code == 200
    assert not directory.exists()


def test_relative_directory_is_independent_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = load_config({"DATA_DIR": "db/custom"})
    assert config["DATA_DIR"] == (PROJECT_DIR / "db/custom").resolve()


def test_environment_and_explicit_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("TACES_DATA_DIR", str(tmp_path / "env"))
    monkeypatch.setenv("TACES_PORT", "8081")
    monkeypatch.setenv("TACES_SQLITE_TIMEOUT", "2.5")
    config = load_config()
    assert config["DATA_DIR"] == tmp_path / "env"
    assert config["PORT"] == 8081
    assert config["SQLITE_TIMEOUT"] == 2.5
    assert load_config({"PORT": 8082})["PORT"] == 8082


@pytest.mark.parametrize("timeout", [True, 0, -1, "invalid", math.nan, math.inf, 61, None])
def test_invalid_timeout_fails_early(timeout):
    with pytest.raises(ValueError, match="SQLITE_TIMEOUT"):
        load_config({"SQLITE_TIMEOUT": timeout})


@pytest.mark.parametrize("port", [True, 0, 65536, 1.5, "1.5", "invalid", None])
def test_invalid_port_fails_early(port):
    with pytest.raises(ValueError, match="PORT"):
        load_config({"PORT": port})


@pytest.mark.parametrize("directory", ["", " ", None, 123])
def test_invalid_data_directory_fails_early(directory):
    with pytest.raises(ValueError, match="DATA_DIR"):
        load_config({"DATA_DIR": directory})


def test_factory_instances_have_independent_configuration(tmp_path):
    first = create_app({"DATA_DIR": tmp_path / "first"})
    second = create_app({"DATA_DIR": tmp_path / "second"})
    assert first.extensions["taces_database"].paths != second.extensions["taces_database"].paths
    assert first.config["DATA_DIR"] != second.config["DATA_DIR"]
