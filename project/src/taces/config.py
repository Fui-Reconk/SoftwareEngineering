"""Runtime configuration, independent of Flask and the working directory."""

import math
import os
from pathlib import Path
from typing import Any, Mapping


PROJECT_DIR = Path(__file__).resolve().parents[2]


def load_config(overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    config: dict[str, Any] = {
        "DATA_DIR": os.environ.get("TACES_DATA_DIR", str(PROJECT_DIR / "db")),
        "SQLITE_TIMEOUT": os.environ.get("TACES_SQLITE_TIMEOUT", "5"),
        "HOST": os.environ.get("TACES_HOST", "127.0.0.1"),
        "PORT": os.environ.get("TACES_PORT", "5000"),
        "MAX_CONTENT_LENGTH": 16 * 1024,
        "TESTING": False,
        "DEBUG": False,
        "AUTH_SESSION_SECONDS": os.environ.get("TACES_SESSION_SECONDS", "28800"),
        "AUTH_COOKIE_SECURE": os.environ.get("TACES_COOKIE_SECURE", "false"),
    }
    config.update(overrides or {})
    directory = config["DATA_DIR"]
    if not isinstance(directory, (str, os.PathLike)) or not str(directory).strip():
        raise ValueError("DATA_DIR must be a non-empty filesystem path")
    directory = Path(directory).expanduser()
    if not directory.is_absolute():
        directory = PROJECT_DIR / directory
    config["DATA_DIR"] = directory.resolve()
    try:
        if isinstance(config["SQLITE_TIMEOUT"], bool):
            raise ValueError
        timeout = float(config["SQLITE_TIMEOUT"])
        if not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise ValueError("SQLITE_TIMEOUT must be a finite number in (0, 60]") from None
    config["SQLITE_TIMEOUT"] = timeout
    port = config["PORT"]
    if isinstance(port, str) and port.isascii() and port.isdecimal():
        port = int(port)
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("PORT must be an integer in [1, 65535]")
    config["PORT"] = port
    if not isinstance(config["HOST"], str) or not config["HOST"].strip():
        raise ValueError("HOST must be a non-empty string")
    duration = config["AUTH_SESSION_SECONDS"]
    if isinstance(duration, str) and duration.isascii() and duration.isdecimal():
        duration = int(duration)
    if type(duration) is not int or not 60 <= duration <= 86400:
        raise ValueError("AUTH_SESSION_SECONDS must be an integer in [60, 86400]")
    config["AUTH_SESSION_SECONDS"] = duration
    secure = config["AUTH_COOKIE_SECURE"]
    if isinstance(secure, str) and secure.lower() in {"true", "false"}:
        secure = secure.lower() == "true"
    if type(secure) is not bool:
        raise ValueError("AUTH_COOKIE_SECURE must be true or false")
    config["AUTH_COOKIE_SECURE"] = secure
    return config
