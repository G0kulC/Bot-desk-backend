from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def utcnow() -> datetime:
    return datetime.now(UTC)


def today_ist() -> date:
    return datetime.now(IST).date()


def ist_day_start_utc(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=IST).astimezone(UTC)


def ist_month_bounds_utc(year: int, month: int) -> tuple[datetime, datetime]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return ist_day_start_utc(start), ist_day_start_utc(end)


def first_of_month(d: date) -> date:
    return d.replace(day=1)


def fmt_ist(dt: datetime | None) -> str:
    if dt is None:
        dt = utcnow()
    return dt.astimezone(IST).strftime("%d %b %Y, %I:%M %p")


def is_night_ist(dt: datetime, start_hour: int, end_hour: int) -> bool:
    hour = dt.astimezone(IST).hour
    if start_hour > end_hour:
        return hour >= start_hour or hour < end_hour
    return start_hour <= hour < end_hour


def hours_ago(hours: float) -> datetime:
    return utcnow() - timedelta(hours=hours)
