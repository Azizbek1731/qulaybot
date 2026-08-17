"""Asosiy mantiq testlari: vaqt tahlili, baza, eslatmalar, takrorlanish."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from app import heuristics, service
from app import timeutil as tu
from app.analyzer import Analyzer, ParsedTask
from app.db import STATUS_DONE, STATUS_DRAFT, STATUS_PENDING, Database

TZ = "Asia/Tashkent"


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    await database.ensure_user(1, full_name="Test", default_tz=TZ)
    await database.register_user(1, "+998901234567", "Test")
    yield database
    await database.close()


# ------------------------------------------------------------------- heuristics

def test_parse_relative_minutes():
    due, has_time = heuristics.parse_datetime("30 daqiqadan keyin qo'ng'iroq qilish", TZ)
    assert due is not None and has_time
    delta = (due - tu.utc_now()).total_seconds()
    assert 1700 < delta < 1900


def test_parse_tomorrow_with_hour():
    due, has_time = heuristics.parse_datetime("ertaga soat 15:30 da uchrashuv", TZ)
    local = tu.to_local(due, TZ)
    tomorrow = tu.local_now(TZ) + timedelta(days=1)
    assert has_time
    assert (local.hour, local.minute) == (15, 30)
    assert local.date() == tomorrow.date()


def test_parse_day_part():
    due, has_time = heuristics.parse_datetime("ertaga kechqurun kitob o'qish", TZ)
    local = tu.to_local(due, TZ)
    assert local.hour == 19 and has_time


def test_parse_explicit_date():
    due, _ = heuristics.parse_datetime("25.12 18:00 da bayram", TZ)
    local = tu.to_local(due, TZ)
    assert (local.day, local.month, local.hour) == (25, 12, 18)


def test_parse_weekday_moves_forward():
    due, _ = heuristics.parse_datetime("juma kuni soat 10 da", TZ)
    local = tu.to_local(due, TZ)
    assert local.weekday() == 4
    assert local > tu.local_now(TZ)


def test_parse_no_time():
    due, has_time = heuristics.parse_datetime("non olish kerak", TZ)
    assert due is None and not has_time


def test_priority_keywords():
    assert heuristics.guess_priority("bu juda muhim ish") == 1
    assert heuristics.guess_priority("muhim hisobot") == 2
    assert heuristics.guess_priority("kitob o'qish") == 3
    assert heuristics.guess_priority("bo'sh vaqtda film ko'rish") == 4


# ------------------------------------------------------------------- takrorlash

def test_next_occurrence_daily():
    past = tu.utc_now() - timedelta(days=3)
    nxt = service.next_occurrence(past, "daily", TZ)
    assert nxt > tu.utc_now()
    assert tu.to_local(nxt, TZ).hour == tu.to_local(past, TZ).hour


def test_next_occurrence_weekly_keeps_weekday():
    past = tu.utc_now() - timedelta(days=10)
    nxt = service.next_occurrence(past, "weekly", TZ)
    assert tu.to_local(nxt, TZ).weekday() == tu.to_local(past, TZ).weekday()
    assert nxt > tu.utc_now()


def test_next_occurrence_weekdays_skips_weekend():
    past = tu.utc_now() - timedelta(days=30)
    nxt = service.next_occurrence(past, "weekdays", TZ)
    assert tu.to_local(nxt, TZ).weekday() < 5


def test_next_occurrence_advances_even_if_due_is_future():
    """Vazifa muddatidan oldin bajarilsa ham, keyingisi bir qadam oldinga suriladi."""
    due = tu.utc_now() + timedelta(minutes=10)
    nxt = service.next_occurrence(due, "daily", TZ)
    assert timedelta(hours=23) < (nxt - due) < timedelta(hours=25)


def test_next_occurrence_none_returns_same():
    due = tu.utc_now() + timedelta(hours=2)
    assert service.next_occurrence(due, "none", TZ) == due


def test_next_occurrence_monthly_clamps_day():
    jan31 = tu.to_utc(datetime(2026, 1, 31, 9, 0), TZ)
    nxt = service._add_months(tu.to_local(jan31, TZ), 1)
    assert (nxt.month, nxt.day) == (2, 28)


# ------------------------------------------------------------------------- baza

@pytest.mark.asyncio
async def test_user_isolation(db):
    await db.ensure_user(2, full_name="Boshqa", default_tz=TZ)
    mine = await db.create_task(1, title="Mening ishim")
    await db.create_task(2, title="Begona ish")

    assert await db.get_task(mine, 2) is None          # boshqa foydalanuvchi ko'ra olmaydi
    assert (await db.get_task(mine, 1))["title"] == "Mening ishim"

    assert len(await db.list_tasks(1, scope="all")) == 1
    assert len(await db.list_tasks(2, scope="all")) == 1


@pytest.mark.asyncio
async def test_scopes(db):
    now = tu.utc_now()
    await db.create_task(1, title="Kechikkan", due_at=now - timedelta(hours=3))
    await db.create_task(1, title="Bugun", due_at=now + timedelta(minutes=30))
    await db.create_task(1, title="Ertaga", due_at=tu.start_of_day(TZ, 1) + timedelta(hours=10))
    await db.create_task(1, title="Vaqtsiz")

    assert {t["title"] for t in await db.list_tasks(1, scope="overdue")} == {"Kechikkan"}
    assert {t["title"] for t in await db.list_tasks(1, scope="tomorrow")} == {"Ertaga"}
    assert {t["title"] for t in await db.list_tasks(1, scope="nodate")} == {"Vaqtsiz"}
    assert {t["title"] for t in await db.list_tasks(1, scope="todayonly")} == {"Bugun"}
    assert len(await db.list_tasks(1, scope="all")) == 4


@pytest.mark.asyncio
async def test_sorting(db):
    now = tu.utc_now()
    await db.create_task(1, title="Past", priority=4, due_at=now + timedelta(hours=1))
    await db.create_task(1, title="Shoshilinch", priority=1, due_at=now + timedelta(hours=5))

    by_time = await db.list_tasks(1, scope="all", sort_mode="time")
    assert [t["title"] for t in by_time] == ["Past", "Shoshilinch"]

    by_priority = await db.list_tasks(1, scope="all", sort_mode="priority")
    assert [t["title"] for t in by_priority] == ["Shoshilinch", "Past"]


# -------------------------------------------------------------------- eslatma

@pytest.mark.asyncio
async def test_reminder_plan(db):
    due = tu.utc_now() + timedelta(hours=3)
    parsed = ParsedTask(title="Uchrashuv", priority=1, due_at=due, has_time=True,
                        remind_offsets=[60, 10])
    task_id = await service.create_from_parsed(db, 1, parsed)

    rows = await db._fetchall("SELECT * FROM reminders WHERE task_id = ?", (task_id,))
    kinds = sorted(row["kind"] for row in rows)
    assert kinds == ["main", "overdue", "pre", "pre"]

    # bazada sekund aniqligida saqlanadi, shuning uchun 1 sekund bag'rikenglik
    fire_times = sorted(tu.parse(row["fire_at"]) for row in rows)
    assert abs((fire_times[0] - (due - timedelta(minutes=60))).total_seconds()) <= 1
    assert abs((fire_times[1] - (due - timedelta(minutes=10))).total_seconds()) <= 1


@pytest.mark.asyncio
async def test_past_due_has_no_reminders(db):
    parsed = ParsedTask(title="O'tgan", due_at=tu.utc_now() - timedelta(hours=5), has_time=True,
                        remind_offsets=[30])
    task_id = await service.create_from_parsed(db, 1, parsed)
    rows = await db._fetchall("SELECT * FROM reminders WHERE task_id = ?", (task_id,))
    assert rows == []


@pytest.mark.asyncio
async def test_draft_has_no_reminders_until_saved(db):
    parsed = ParsedTask(title="Qoralama", due_at=tu.utc_now() + timedelta(hours=2),
                        has_time=True, remind_offsets=[30])
    task_id = await service.create_from_parsed(db, 1, parsed, status=STATUS_DRAFT, batch="b1")

    assert await db._fetchall("SELECT * FROM reminders WHERE task_id = ?", (task_id,)) == []
    assert len(await db.list_drafts(1, "b1")) == 1

    await service.activate_draft(db, task_id, 1)
    task = await db.get_task(task_id, 1)
    assert task["status"] == STATUS_PENDING
    assert len(await db._fetchall("SELECT * FROM reminders WHERE task_id = ?", (task_id,))) > 0


@pytest.mark.asyncio
async def test_due_reminders_queue(db):
    parsed = ParsedTask(title="Hozir", due_at=tu.utc_now() + timedelta(seconds=1), has_time=True)
    task_id = await service.create_from_parsed(db, 1, parsed)
    await db.conn.execute(
        "UPDATE reminders SET fire_at = ? WHERE task_id = ?",
        (tu.dump(tu.utc_now() - timedelta(seconds=5)), task_id),
    )
    await db.conn.commit()

    queue = await db.due_reminders()
    assert len(queue) == 1
    assert queue[0]["title"] == "Hozir"
    assert queue[0]["id"] == task_id           # t.* dan kelgan vazifa id si

    await db.mark_reminder_sent(queue[0]["reminder_id"])
    assert await db.due_reminders() == []


@pytest.mark.asyncio
async def test_snooze_moves_due_and_reminder(db):
    parsed = ParsedTask(title="Keyinroq", due_at=tu.utc_now() + timedelta(minutes=5), has_time=True)
    task_id = await service.create_from_parsed(db, 1, parsed)

    target = await service.snooze(db, task_id, 1, 60, TZ)
    task = await db.get_task(task_id, 1)
    assert abs((tu.parse(task["due_at"]) - target).total_seconds()) < 2

    rows = await db._fetchall("SELECT * FROM reminders WHERE task_id = ? AND sent = 0", (task_id,))
    assert len(rows) == 1 and rows[0]["kind"] == "snooze"


# ----------------------------------------------------------------- bajarilish

@pytest.mark.asyncio
async def test_complete_simple(db):
    task_id = await db.create_task(1, title="Oddiy", due_at=tu.utc_now() + timedelta(hours=1))
    await service.plan_reminders(db, task_id, 1)

    task = await db.get_task(task_id, 1)
    assert await service.complete(db, task, TZ) is None

    done = await db.get_task(task_id, 1)
    assert done["status"] == STATUS_DONE and done["completed_at"]
    assert await db._fetchall("SELECT * FROM reminders WHERE task_id = ? AND sent = 0", (task_id,)) == []


@pytest.mark.asyncio
async def test_complete_recurring_moves_forward(db):
    due = tu.utc_now() + timedelta(minutes=10)
    task_id = await db.create_task(1, title="Har kuni", due_at=due, recurrence="daily")
    task = await db.get_task(task_id, 1)

    next_due = await service.complete(db, task, TZ)
    assert next_due is not None and next_due > due

    original = await db.get_task(task_id, 1)
    assert original["status"] == STATUS_PENDING          # asosiy vazifa yashaydi

    history = await db.list_tasks(1, scope="done")
    assert len(history) == 1 and history[0]["title"] == "Har kuni"


@pytest.mark.asyncio
async def test_stats(db):
    await db.create_task(1, title="Bajarilgan", status=STATUS_DONE)
    await db.update_task(2 if False else 1, 1, completed_at=tu.utc_now())
    await db.create_task(1, title="Kechikkan", priority=1, due_at=tu.utc_now() - timedelta(hours=2))

    data = await db.stats(1, TZ)
    assert data["total"] == 2
    assert data["overdue"] == 1
    assert data["p1"] == 1


# -------------------------------------------------------------- AI normalizatsiya

def test_analyzer_normalizes_ai_output():
    analyzer = Analyzer(gemini=None)  # type: ignore[arg-type]
    local = tu.local_now(TZ) + timedelta(days=1)
    item = {
        "title": "  Shifokorga borish  ",
        "notes": "",
        "priority": 99,                       # chegaradan tashqari
        "due_at": local.strftime("%Y-%m-%d %H:%M"),
        "has_time": True,
        "recurrence": "har kuni",             # noto'g'ri qiymat
        "category": "yo'q",                   # ro'yxatda yo'q
        "remind_before_minutes": [60, 60, -5, 99999],
    }
    task = analyzer._normalize(item, TZ, "shifokorga borish")

    assert task.title == "Shifokorga borish"
    assert task.priority == 4                  # 99 -> 4 gacha qisqartiriladi
    assert task.recurrence == "none"
    assert task.category is None
    assert task.notes is None
    assert task.remind_offsets == [60]
    assert tu.to_local(task.due_at, TZ).strftime("%Y-%m-%d %H:%M") == local.strftime("%Y-%m-%d %H:%M")


def test_analyzer_falls_back_to_heuristic_time():
    analyzer = Analyzer(gemini=None)  # type: ignore[arg-type]
    item = {"title": "Uchrashuv", "priority": 2, "due_at": "", "has_time": False,
            "recurrence": "none"}
    task = analyzer._normalize(item, TZ, "ertaga soat 14:00 da uchrashuv")

    assert task.due_at is not None
    assert tu.to_local(task.due_at, TZ).hour == 14


def test_offsets_are_serialized(tmp_path):
    task = ParsedTask(title="X", remind_offsets=[60, 10])
    assert json.dumps(task.remind_offsets) == "[60, 10]"
