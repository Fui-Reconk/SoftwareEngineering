"""Canonical presentation time; persisted audit timestamps remain UTC."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")


def utc_stamp():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def shanghai_stamp(value):
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(SHANGHAI).isoformat()
