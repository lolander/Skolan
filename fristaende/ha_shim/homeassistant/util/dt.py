from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DEFAULT_TIME_ZONE = ZoneInfo("Europe/Stockholm")


def set_default_time_zone(namn: str) -> None:
    global DEFAULT_TIME_ZONE
    DEFAULT_TIME_ZONE = ZoneInfo(namn)


def now(tz=None) -> datetime:
    return datetime.now(tz or DEFAULT_TIME_ZONE)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_local(d: datetime) -> datetime:
    return d.astimezone(DEFAULT_TIME_ZONE)


def parse_datetime(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None
