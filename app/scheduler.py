"""Fon jarayoni: eslatmalarni yuborish va kunlik xulosa.

Har `tick_seconds` sekundda bazadagi navbatdagi eslatmalar tekshiriladi.
Bunday yondashuv bot qayta ishga tushganda ham hech narsani yo'qotmaydi —
jadval xotirada emas, bazada saqlanadi.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from . import keyboards, texts, timeutil as tu
from .db import STATUS_PENDING, Database

log = logging.getLogger(__name__)

SENT = 1
SKIPPED = 2


class ReminderScheduler:
    def __init__(self, bot: Bot, db: Database, tick_seconds: int = 20) -> None:
        self._bot = bot
        self._db = db
        self._tick = max(5, tick_seconds)
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="reminder-scheduler")
            log.info("Eslatma xizmati ishga tushdi (har %s sekund)", self._tick)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    # --------------------------------------------------------------- ichkarida

    async def _run(self) -> None:
        # Bot endigina ko'tarilgan bo'lsa, ulanish barqarorlashishini kutamiz
        await asyncio.sleep(3)
        cleanup_counter = 0

        while True:
            try:
                await self._dispatch_reminders()
                await self._send_digests()

                cleanup_counter += 1
                if cleanup_counter * self._tick > 3600:  # soatiga bir marta
                    cleanup_counter = 0
                    removed = await self._db.purge_stale_drafts()
                    if removed:
                        log.info("%s ta eskirgan qoralama tozalandi", removed)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - fon jarayoni to'xtab qolmasligi kerak
                log.exception("Eslatma siklida kutilmagan xatolik")

            await asyncio.sleep(self._tick)

    async def _dispatch_reminders(self) -> None:
        rows = await self._db.due_reminders(limit=40)
        if not rows:
            return

        for row in rows:
            reminder_id = row["reminder_id"]

            if row["status"] != STATUS_PENDING:
                await self._db.mark_reminder_sent(reminder_id, SKIPPED)
                continue

            user = await self._db.get_user(row["user_id"])
            if user is None or not user["notify"] or user["registered_at"] is None:
                await self._db.mark_reminder_sent(reminder_id, SKIPPED)
                continue

            try:
                await self._bot.send_message(
                    chat_id=row["user_id"],
                    text=texts.reminder_text(row, user["tz"], row["kind"]),
                    reply_markup=keyboards.reminder_kb(row["id"]),
                )
                await self._db.mark_reminder_sent(reminder_id, SENT)
            except TelegramRetryAfter as exc:
                log.warning("Telegram limiti: %s sekund kutamiz", exc.retry_after)
                await asyncio.sleep(exc.retry_after + 1)
                return
            except TelegramForbiddenError:
                log.info("Foydalanuvchi %s botni bloklagan — eslatmalar o'chirildi", row["user_id"])
                await self._db.update_user(row["user_id"], notify=0)
                await self._db.mark_reminder_sent(reminder_id, SKIPPED)
            except Exception:  # noqa: BLE001
                log.exception("Eslatma yuborilmadi (task=%s)", row["id"])
                await self._db.mark_reminder_sent(reminder_id, SKIPPED)

            await asyncio.sleep(0.05)  # Telegram limitlarini hurmat qilamiz

    async def _send_digests(self) -> None:
        for user in await self._db.active_users():
            digest_hour = user["digest_hour"]
            if digest_hour is None or digest_hour < 0:
                continue

            local = tu.local_now(user["tz"])
            today = local.date().isoformat()

            if local.hour != digest_hour or user["last_digest"] == today:
                continue

            tasks = await self._db.list_tasks(
                user["id"], scope="todayonly", sort_mode="time", limit=20
            )
            overdue = await self._db.list_tasks(
                user["id"], scope="overdue", sort_mode="smart", limit=20
            )

            # Ish yo'q bo'lsa bezovta qilmaymiz
            if not tasks and not overdue:
                await self._db.update_user(user["id"], last_digest=today)
                continue

            try:
                await self._bot.send_message(
                    chat_id=user["id"],
                    text=texts.digest_text(tasks, overdue, user["tz"]),
                    reply_markup=keyboards.list_kb(
                        tasks[: keyboards.PAGE_SIZE], scope="today", page=0, pages=1
                    ),
                )
            except TelegramForbiddenError:
                await self._db.update_user(user["id"], notify=0)
            except Exception:  # noqa: BLE001
                log.exception("Kunlik xulosa yuborilmadi (user=%s)", user["id"])

            await self._db.update_user(user["id"], last_digest=today)
            await asyncio.sleep(0.05)
