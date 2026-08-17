"""Oddiy (AI'siz) matn tahlili.

Ikki joyda ishlatiladi:
  1. Gemini javob bermasa — zaxira variant sifatida;
  2. Foydalanuvchi vaqtni qo'lda yozganda ("ertaga soat 9 da").
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from . import timeutil as tu
from .db import PRIORITY_HIGH, PRIORITY_LOW, PRIORITY_MEDIUM, PRIORITY_URGENT

MONTHS = {
    "yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "may": 5, "iyun": 6,
    "iyul": 7, "avgust": 8, "sentabr": 9, "sentyabr": 9, "oktabr": 10,
    "oktyabr": 10, "noyabr": 11, "dekabr": 12,
}

WEEKDAYS = {
    "dushanba": 0, "seshanba": 1, "chorshanba": 2, "payshanba": 3,
    "juma": 4, "shanba": 5, "yakshanba": 6,
}

DAY_PARTS = {
    "ertalab": 8, "erta tongda": 7, "tongda": 7, "nonushta": 8,
    "tushda": 13, "tushlik": 13, "tushdan keyin": 15, "kunduzi": 12,
    "kechqurun": 19, "kechasi": 21, "kech": 19, "kechki": 19, "oqshom": 19,
}

URGENT_WORDS = (
    "shoshilinch", "zudlik", "juda muhim", "juda zarur", "favqulodda", "tezkor",
    "hoziroq", "darhol", "urgent", "juda tez", "kechiktirib bo'lmaydi",
)
HIGH_WORDS = ("muhim", "zarur", "albatta", "majburiy", "esdan chiqmasin", "unutma")
LOW_WORDS = (
    "shoshilinch emas", "muhim emas", "keyinroq", "bo'sh vaqtda", "imkon bo'lsa",
    "vaqt topsam", "qachondir",
)

_APOSTROPHES = str.maketrans({"ʻ": "'", "ʼ": "'", "’": "'", "‘": "'", "`": "'", "´": "'"})


def normalize(text: str) -> str:
    return text.translate(_APOSTROPHES).strip()


def guess_priority(text: str) -> int:
    low = normalize(text).lower()
    for word in LOW_WORDS:
        if word in low:
            return PRIORITY_LOW
    for word in URGENT_WORDS:
        if word in low:
            return PRIORITY_URGENT
    for word in HIGH_WORDS:
        if word in low:
            return PRIORITY_HIGH
    return PRIORITY_MEDIUM


def _find_time(text: str) -> tuple[int, int, str] | None:
    """Matndan soat:daqiqa juftligini topadi.

    Qaytaradi: (soat, daqiqa, matndagi topilgan bo'lak). Uchinchi qiymat
    sanani izlashdan oldin matndan olib tashlanadi — shunda «25.12 18:00»
    dagi «18:00» sana deb o'qilmaydi.
    """
    for pattern in (r"soat\s*(\d{1,2})[:.\s](\d{2})", r"\b(\d{1,2}):(\d{2})\b"):
        m = re.search(pattern, text)
        if m:
            hour, minute = int(m.group(1)), int(m.group(2))
            if hour < 24 and minute < 60:
                return hour, minute, m.group(0)

    m = re.search(r"soat\s*(\d{1,2})\b", text)
    if m and int(m.group(1)) < 24:
        return int(m.group(1)), 0, m.group(0)

    for word, hour in DAY_PARTS.items():
        if word in text:
            return hour, 0, word
    return None


def _find_relative(text: str) -> timedelta | None:
    patterns = [
        (r"(\d+)\s*(?:daqiqa|minut|min)\w*\s*(?:dan)?\s*(?:keyin|so'ng)", "minutes"),
        (r"(\d+)\s*soat\w*\s*(?:dan)?\s*(?:keyin|so'ng)", "hours"),
        (r"(\d+)\s*kun\w*\s*(?:dan)?\s*(?:keyin|so'ng)", "days"),
        (r"(\d+)\s*hafta\w*\s*(?:dan)?\s*(?:keyin|so'ng)", "weeks"),
        (r"(\d+)\s*oy\w*\s*(?:dan)?\s*(?:keyin|so'ng)", "months"),
    ]
    for pattern, unit in patterns:
        m = re.search(pattern, text)
        if m:
            value = int(m.group(1))
            if unit == "months":
                return timedelta(days=30 * value)
            return timedelta(**{unit: value})

    if re.search(r"\byarim soat\w*\s*(?:dan)?\s*(?:keyin|so'ng)", text):
        return timedelta(minutes=30)
    return None


def parse_datetime(text: str, tz: str) -> tuple[datetime | None, bool]:
    """Matndan sana-vaqtni ajratadi.

    Qaytaradi: (UTC datetime yoki None, aniq soat ko'rsatilganmi).
    """
    low = normalize(text).lower()
    now_local = tu.local_now(tz)

    relative = _find_relative(low)
    if relative is not None:
        return tu.to_utc(now_local + relative, tz), True

    found_time = _find_time(low)
    time_part = (found_time[0], found_time[1]) if found_time else None
    has_time = found_time is not None

    # Soat topilgan bo'lsa, uni matndan olib tashlaymiz — sana bilan chalkashmasin
    rest = low.replace(found_time[2], " ", 1) if found_time else low

    day: datetime | None = None

    # "17.08.2026" yoki "17.08" (oy 1-12 bo'lmasa — bu sana emas)
    m = re.search(r"\b(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\b", rest)
    if m:
        d, mon = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else now_local.year
        if year < 100:
            year += 2000
        try:
            day = now_local.replace(year=year, month=mon, day=d)
            if m.group(3) is None and day.date() < now_local.date():
                day = day.replace(year=year + 1)
        except ValueError:
            day = None

    # "17-avgust" / "17 avgust"
    if day is None:
        m = re.search(r"\b(\d{1,2})[\s-]*(" + "|".join(MONTHS) + r")", rest)
        if m:
            try:
                day = now_local.replace(month=MONTHS[m.group(2)], day=int(m.group(1)))
                if day.date() < now_local.date():
                    day = day.replace(year=day.year + 1)
            except ValueError:
                day = None

    if day is None:
        if "indinga" in low or "erta indin" in low:
            day = now_local + timedelta(days=2)
        elif "ertaga" in low:
            day = now_local + timedelta(days=1)
        elif "bugun" in low:
            day = now_local
        elif re.search(r"(kelasi|keyingi)\s+hafta", low):
            day = now_local + timedelta(days=7)
        elif re.search(r"(kelasi|keyingi)\s+oy", low):
            day = now_local + timedelta(days=30)

    if day is None:
        for name, index in WEEKDAYS.items():
            if name in low:
                ahead = (index - now_local.weekday()) % 7
                if ahead == 0:
                    ahead = 7
                day = now_local + timedelta(days=ahead)
                break

    if day is None and time_part is None:
        return None, False

    if day is None:
        day = now_local

    hour, minute = time_part if time_part else (9, 0)
    result = day.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # Faqat soat aytilgan bo'lsa va u o'tib ketgan bo'lsa — ertangi kunga
    if result <= now_local and not re.search(r"bugun|kecha", low):
        if time_part is not None and day.date() == now_local.date():
            result += timedelta(days=1)

    return tu.to_utc(result, tz), has_time


def clean_title(text: str, limit: int = 120) -> str:
    """Xom matndan qisqa sarlavha yasaydi."""
    title = re.sub(r"\s+", " ", normalize(text)).strip(" .,!?;:")
    if len(title) > limit:
        title = title[: limit - 1].rsplit(" ", 1)[0] + "…"
    return title or "Nomsiz vazifa"


def fallback_parse(text: str, tz: str) -> dict:
    """Gemini ishlamaganda ishlatiladigan sodda tahlil."""
    due_at, has_time = parse_datetime(text, tz)
    return {
        "title": clean_title(text),
        "notes": None,
        "priority": guess_priority(text),
        "due_at": due_at,
        "has_time": has_time,
        "recurrence": "none",
        "category": None,
    }
