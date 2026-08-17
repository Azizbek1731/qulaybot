"""Vaqt bilan ishlash: UTC <-> mahalliy vaqt, o'zbekcha formatlash."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ISO_FMT = "%Y-%m-%d %H:%M:%S"

MONTHS_UZ = [
    "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
]

WEEKDAYS_UZ = [
    "dushanba", "seshanba", "chorshanba", "payshanba",
    "juma", "shanba", "yakshanba",
]


def tzinfo(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def utc_now() -> datetime:
    """Hozirgi UTC vaqti (tz-aware)."""
    return datetime.now(timezone.utc)


def local_now(tz_name: str) -> datetime:
    return utc_now().astimezone(tzinfo(tz_name))


def to_utc(dt_local: datetime, tz_name: str) -> datetime:
    """Mahalliy (naive yoki aware) vaqtni UTC ga o'giradi."""
    if dt_local.tzinfo is None:
        dt_local = dt_local.replace(tzinfo=tzinfo(tz_name))
    return dt_local.astimezone(timezone.utc)


def to_local(dt_utc: datetime, tz_name: str) -> datetime:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(tzinfo(tz_name))


def dump(dt: datetime | None) -> str | None:
    """UTC datetime -> bazaga yoziladigan matn."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime(ISO_FMT)


def parse(value: str | None) -> datetime | None:
    """Bazadagi matn -> UTC datetime."""
    if not value:
        return None
    try:
        return datetime.strptime(value, ISO_FMT).replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            return datetime.fromisoformat(value).astimezone(timezone.utc)
        except ValueError:
            return None


def fmt_datetime(dt_utc: datetime | None, tz_name: str, *, has_time: bool = True) -> str:
    """Sanani odam o'qiydigan ko'rinishda: «Bugun 14:00», «17-avgust, 09:30»."""
    if dt_utc is None:
        return "vaqtsiz"

    local = to_local(dt_utc, tz_name)
    today = local_now(tz_name).date()
    delta_days = (local.date() - today).days

    time_part = local.strftime("%H:%M") if has_time else ""

    if delta_days == 0:
        day_part = "Bugun"
    elif delta_days == 1:
        day_part = "Ertaga"
    elif delta_days == 2:
        day_part = "Indinga"
    elif delta_days == -1:
        day_part = "Kecha"
    elif 0 < delta_days < 7:
        day_part = WEEKDAYS_UZ[local.weekday()].capitalize()
    else:
        day_part = f"{local.day}-{MONTHS_UZ[local.month - 1]}"
        if local.year != today.year:
            day_part += f" {local.year}"

    return f"{day_part} {time_part}".strip()


def fmt_relative(dt_utc: datetime | None) -> str:
    """«2 soatdan keyin», «15 daqiqa oldin» ko'rinishidagi nisbiy vaqt."""
    if dt_utc is None:
        return ""

    diff = (dt_utc - utc_now()).total_seconds()
    past = diff < 0
    diff = abs(diff)

    if diff < 60:
        text = "1 daqiqa"
    elif diff < 3600:
        text = f"{int(diff // 60)} daqiqa"
    elif diff < 86400:
        hours = int(diff // 3600)
        minutes = int((diff % 3600) // 60)
        text = f"{hours} soat" + (f" {minutes} daqiqa" if minutes else "")
    else:
        days = int(diff // 86400)
        text = f"{days} kun"

    return f"{text} oldin" if past else f"{text}dan keyin"


def start_of_day(tz_name: str, offset_days: int = 0) -> datetime:
    """Mahalliy kunning boshlanishi, UTC da."""
    local = local_now(tz_name) + timedelta(days=offset_days)
    local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc)


def end_of_day(tz_name: str, offset_days: int = 0) -> datetime:
    return start_of_day(tz_name, offset_days + 1)
