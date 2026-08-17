"""Vazifalar ustidagi asosiy amallar: saqlash, eslatma rejalashtirish,
bajarilgan deb belgilash va takrorlanuvchi vazifalarni keyingi muddatga surish.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

import aiosqlite

from . import timeutil as tu
from .analyzer import ParsedTask
from .db import STATUS_DONE, STATUS_DRAFT, STATUS_PENDING, Database

log = logging.getLogger(__name__)

# Vazifa muddati o'tib ketgan bo'lsa, shuncha vaqt ichida bo'lsa ham eslatamiz
GRACE = timedelta(minutes=2)

# Muddati o'tgach qo'shimcha turtki (faqat muhim vazifalar uchun)
OVERDUE_NUDGE = timedelta(minutes=45)


async def create_from_parsed(
    db: Database,
    user_id: int,
    parsed: ParsedTask,
    *,
    status: str = STATUS_PENDING,
    source: str = "text",
    raw_text: str | None = None,
    batch: str | None = None,
) -> int:
    task_id = await db.create_task(
        user_id,
        title=parsed.title,
        notes=parsed.notes,
        priority=parsed.priority,
        due_at=parsed.due_at,
        has_time=parsed.has_time,
        recurrence=parsed.recurrence,
        category=parsed.category,
        status=status,
        source=source,
        raw_text=raw_text,
        remind_offsets=parsed.remind_offsets,
        batch=batch,
    )
    if status == STATUS_PENDING:
        await plan_reminders(db, task_id, user_id)
    return task_id


async def activate_draft(db: Database, task_id: int, user_id: int) -> aiosqlite.Row | None:
    task = await db.get_task(task_id, user_id)
    if task is None or task["status"] != STATUS_DRAFT:
        return task
    await db.update_task(task_id, user_id, status=STATUS_PENDING)
    await plan_reminders(db, task_id, user_id)
    return await db.get_task(task_id, user_id)


async def plan_reminders(db: Database, task_id: int, user_id: int) -> int:
    """Vazifa uchun eslatmalar jadvalini qaytadan tuzadi."""
    await db.clear_reminders(task_id)

    task = await db.get_task(task_id, user_id)
    if task is None or task["status"] != STATUS_PENDING:
        return 0

    due = tu.parse(task["due_at"])
    if due is None:
        return 0

    now = tu.utc_now()
    moments: list[tuple[datetime, str]] = []

    try:
        offsets = [int(m) for m in json.loads(task["remind_offsets"] or "[]")]
    except (TypeError, ValueError):
        offsets = []

    for minutes in offsets:
        moment = due - timedelta(minutes=minutes)
        if moment > now:
            moments.append((moment, "pre"))

    if due > now - GRACE:
        moments.append((due, "main"))

    if task["priority"] <= 2:
        nudge = due + OVERDUE_NUDGE
        if nudge > now:
            moments.append((nudge, "overdue"))

    await db.add_reminders(task_id, user_id, moments)
    return len(moments)


async def set_due(
    db: Database,
    task_id: int,
    user_id: int,
    due_at: datetime | None,
    *,
    has_time: bool = True,
) -> None:
    await db.update_task(task_id, user_id, due_at=due_at, has_time=int(has_time))
    await plan_reminders(db, task_id, user_id)


async def snooze(db: Database, task_id: int, user_id: int, minutes: int, tz: str) -> datetime | None:
    """Eslatmani keyinroqqa surish. minutes=-1 → ertaga ertalab 09:00."""
    if minutes == -1:
        local = tu.local_now(tz) + timedelta(days=1)
        target = tu.to_utc(local.replace(hour=9, minute=0, second=0, microsecond=0), tz)
    else:
        target = tu.utc_now() + timedelta(minutes=minutes)

    await db.update_task(task_id, user_id, due_at=target, has_time=1)
    await db.clear_reminders(task_id)
    await db.add_reminders(task_id, user_id, [(target, "snooze")])
    return target


async def complete(db: Database, task: aiosqlite.Row, tz: str) -> datetime | None:
    """Bajarildi deb belgilaydi.

    Takrorlanuvchi vazifa bo'lsa — tarix uchun nusxa saqlanadi, asosiy vazifa
    esa keyingi muddatga suriladi. Qaytaradi: keyingi muddat (bo'lsa).
    """
    task_id, user_id = task["id"], task["user_id"]
    now = tu.utc_now()
    due = tu.parse(task["due_at"])
    recurrence = task["recurrence"] or "none"

    if recurrence == "none" or due is None:
        await db.update_task(task_id, user_id, status=STATUS_DONE, completed_at=now)
        await db.clear_reminders(task_id)
        return None

    # Tarix uchun bajarilgan nusxa
    clone_id = await db.create_task(
        user_id,
        title=task["title"],
        notes=task["notes"],
        priority=task["priority"],
        due_at=due,
        has_time=bool(task["has_time"]),
        recurrence="none",
        category=task["category"],
        status=STATUS_DONE,
        source=task["source"],
        raw_text=task["raw_text"],
    )
    await db.update_task(clone_id, user_id, completed_at=now)

    next_due = next_occurrence(due, recurrence, tz)
    await db.update_task(task_id, user_id, due_at=next_due)
    await plan_reminders(db, task_id, user_id)
    return next_due


async def uncomplete(db: Database, task: aiosqlite.Row) -> None:
    await db.update_task(
        task["id"], task["user_id"], status=STATUS_PENDING, completed_at=None
    )
    await plan_reminders(db, task["id"], task["user_id"])


def next_occurrence(due_utc: datetime, recurrence: str, tz: str) -> datetime:
    """Takrorlanish qoidasiga ko'ra keyingi muddatni hisoblaydi.

    Hisob mahalliy vaqtda yuritiladi — shunda soat (masalan 09:00) saqlanib
    qoladi, hatto vaqt mintaqasi yozgi vaqtga o'tsa ham.
    """
    if recurrence not in ("daily", "weekdays", "weekly", "monthly", "yearly"):
        return due_utc

    local = tu.to_local(due_utc, tz)
    now_local = tu.local_now(tz)

    # Kamida bir qadam oldinga suriladi (vazifa muddatidan oldin bajarilsa ham),
    # so'ng hozirgi vaqtdan o'tib ketguncha davom etamiz.
    for _ in range(500):
        local = _step(local, recurrence)
        if local > now_local:
            break

    return tu.to_utc(local, tz)


def _step(local: datetime, recurrence: str) -> datetime:
    if recurrence == "daily":
        return local + timedelta(days=1)
    if recurrence == "weekdays":
        local += timedelta(days=1)
        while local.weekday() >= 5:  # shanba/yakshanba
            local += timedelta(days=1)
        return local
    if recurrence == "weekly":
        return local + timedelta(days=7)
    if recurrence == "monthly":
        return _add_months(local, 1)
    if recurrence == "yearly":
        return _add_months(local, 12)
    return local


def _add_months(dt: datetime, months: int) -> datetime:
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, _days_in_month(year, month))
    return dt.replace(year=year, month=month, day=day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (datetime(year, month + 1, 1) - timedelta(days=1)).day


def preset_due(code: str, tz: str) -> tuple[datetime | None, bool]:
    """Tugmalardagi tayyor vaqt variantlari."""
    now = tu.local_now(tz)

    if code == "clr":
        return None, False
    if code == "1h":
        return tu.to_utc(now + timedelta(hours=1), tz), True
    if code == "3h":
        return tu.to_utc(now + timedelta(hours=3), tz), True
    if code == "te":
        target = now.replace(hour=19, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return tu.to_utc(target, tz), True
    if code == "em":
        target = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        return tu.to_utc(target, tz), True
    if code == "ee":
        target = (now + timedelta(days=1)).replace(hour=19, minute=0, second=0, microsecond=0)
        return tu.to_utc(target, tz), True
    if code == "2d":
        target = (now + timedelta(days=2)).replace(hour=9, minute=0, second=0, microsecond=0)
        return tu.to_utc(target, tz), True
    if code == "nw":
        ahead = (7 - now.weekday()) % 7 or 7
        target = (now + timedelta(days=ahead)).replace(hour=9, minute=0, second=0, microsecond=0)
        return tu.to_utc(target, tz), True

    return None, False
