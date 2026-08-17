"""Eslatma yuborish va kunlik xulosa testlari."""

from __future__ import annotations

from datetime import timedelta

import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app import service
from app import timeutil as tu
from app.analyzer import ParsedTask
from app.db import STATUS_DONE, Database
from app.scheduler import SKIPPED, ReminderScheduler
from tests.test_flow import UID, TZ, FakeSession


@pytest.fixture
async def env(tmp_path):
    db = Database(tmp_path / "sched.db")
    await db.connect()
    await db.ensure_user(UID, full_name="Aziz", default_tz=TZ)
    await db.register_user(UID, "+998901234567", "Aziz")

    session = FakeSession()
    bot = Bot(token="42:TEST", session=session,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    yield db, bot, session, ReminderScheduler(bot, db, tick_seconds=20)

    await bot.session.close()
    await db.close()


async def _overdue_reminder(db: Database, title: str = "Dori ichish") -> int:
    """Vaqti kelgan eslatmasi bor vazifa yaratadi."""
    parsed = ParsedTask(title=title, priority=1, due_at=tu.utc_now() + timedelta(minutes=1),
                        has_time=True, remind_offsets=[30])
    task_id = await service.create_from_parsed(db, UID, parsed)
    await db.conn.execute(
        "UPDATE reminders SET fire_at = ? WHERE task_id = ?",
        (tu.dump(tu.utc_now() - timedelta(seconds=10)), task_id),
    )
    await db.conn.commit()
    return task_id


@pytest.mark.asyncio
async def test_reminder_is_sent_once(env):
    db, bot, session, scheduler = env
    task_id = await _overdue_reminder(db)

    await scheduler._dispatch_reminders()

    sent = [c for c in session.calls if type(c).__name__ == "SendMessage"]
    assert len(sent) >= 1
    assert "Dori ichish" in sent[0].text
    assert sent[0].chat_id == UID

    buttons = {
        b.callback_data
        for row in sent[0].reply_markup.inline_keyboard for b in row
    }
    assert f"t:{task_id}:done" in buttons
    assert f"t:{task_id}:snz:60" in buttons

    rows = await db._fetchall("SELECT * FROM reminders WHERE task_id = ?", (task_id,))
    assert all(r["sent"] != 0 for r in rows if tu.parse(r["fire_at"]) <= tu.utc_now())

    # Ikkinchi marta yuborilmaydi
    session.calls.clear()
    await scheduler._dispatch_reminders()
    assert [c for c in session.calls if type(c).__name__ == "SendMessage"] == []


@pytest.mark.asyncio
async def test_done_task_reminder_skipped(env):
    db, bot, session, scheduler = env
    task_id = await _overdue_reminder(db)
    await db.update_task(task_id, UID, status=STATUS_DONE, completed_at=tu.utc_now())

    await scheduler._dispatch_reminders()

    assert [c for c in session.calls if type(c).__name__ == "SendMessage"] == []
    rows = await db._fetchall("SELECT * FROM reminders WHERE task_id = ?", (task_id,))
    assert any(r["sent"] == SKIPPED for r in rows)


@pytest.mark.asyncio
async def test_notifications_disabled(env):
    db, bot, session, scheduler = env
    await _overdue_reminder(db)
    await db.update_user(UID, notify=0)

    await scheduler._dispatch_reminders()
    assert [c for c in session.calls if type(c).__name__ == "SendMessage"] == []


@pytest.mark.asyncio
async def test_daily_digest(env):
    db, bot, session, scheduler = env

    hour = tu.local_now(TZ).hour
    await db.update_user(UID, digest_hour=hour)
    await db.create_task(UID, title="Yigilish", due_at=tu.utc_now() + timedelta(minutes=90))
    await db.create_task(UID, title="Kechikkan", due_at=tu.utc_now() - timedelta(hours=4))

    await scheduler._send_digests()

    sent = [c for c in session.calls if type(c).__name__ == "SendMessage"]
    assert len(sent) == 1
    assert "Yigilish" in sent[0].text
    assert "Kechikkan" in sent[0].text
    assert (await db.get_user(UID))["last_digest"] == tu.local_now(TZ).date().isoformat()

    # Kuniga bir marta
    session.calls.clear()
    await scheduler._send_digests()
    assert [c for c in session.calls if type(c).__name__ == "SendMessage"] == []


@pytest.mark.asyncio
async def test_digest_not_sent_at_other_hours(env):
    db, bot, session, scheduler = env
    await db.update_user(UID, digest_hour=(tu.local_now(TZ).hour + 3) % 24)
    await db.create_task(UID, title="Yigilish", due_at=tu.utc_now() + timedelta(hours=1))

    await scheduler._send_digests()
    assert [c for c in session.calls if type(c).__name__ == "SendMessage"] == []


@pytest.mark.asyncio
async def test_digest_skipped_when_nothing_to_do(env):
    db, bot, session, scheduler = env
    await db.update_user(UID, digest_hour=tu.local_now(TZ).hour)

    await scheduler._send_digests()
    assert [c for c in session.calls if type(c).__name__ == "SendMessage"] == []
    assert (await db.get_user(UID))["last_digest"] is not None
