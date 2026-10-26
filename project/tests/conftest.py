import pytest

from taces import create_app


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "DATA_DIR": tmp_path / "data"})


@pytest.fixture
def database(app):
    database = app.extensions["taces_database"]
    database.initialize()
    return database
