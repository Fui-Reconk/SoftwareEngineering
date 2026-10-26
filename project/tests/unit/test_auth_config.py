import pytest

from taces.config import load_config


@pytest.mark.parametrize("duration", [True, 0, 59, 86401, 60.5, "bad", None])
def test_invalid_session_duration(duration):
    with pytest.raises(ValueError, match="AUTH_SESSION_SECONDS"):
        load_config({"AUTH_SESSION_SECONDS": duration})


@pytest.mark.parametrize("secure", [1, 0, "yes", None, []])
def test_invalid_cookie_secure(secure):
    with pytest.raises(ValueError, match="AUTH_COOKIE_SECURE"):
        load_config({"AUTH_COOKIE_SECURE": secure})


def test_auth_environment_and_explicit_overrides(monkeypatch):
    monkeypatch.setenv("TACES_SESSION_SECONDS", "600")
    monkeypatch.setenv("TACES_COOKIE_SECURE", "TRUE")
    config = load_config()
    assert config["AUTH_SESSION_SECONDS"] == 600
    assert config["AUTH_COOKIE_SECURE"] is True
    config = load_config({"AUTH_SESSION_SECONDS": 60, "AUTH_COOKIE_SECURE": False})
    assert config["AUTH_SESSION_SECONDS"] == 60
    assert config["AUTH_COOKIE_SECURE"] is False
