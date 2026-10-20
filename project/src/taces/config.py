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
    return config
