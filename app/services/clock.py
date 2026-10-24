"""'Today' for attendance purposes, in the configured timezone (default: this machine's local time)."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import setting


def today() -> date:
    timezone = setting("TIMEZONE")
    return datetime.now(ZoneInfo(timezone)).date() if timezone else datetime.now().date()
