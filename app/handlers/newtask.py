"""Qo'lda yangi vazifa qo'shish (AI'siz, bosqichma-bosqich)."""

from __future__ import annotations

import logging

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import heuristics, keyboards, service, texts, timeutil as tu
from ..analyzer import DEFAULT_OFFSETS, ParsedTask
from ..db import PRIORITY_MEDIUM, Database
from ..states import NewTask
from .render import safe_edit, show_task

log = logging.getLogger(__name__)

router = Router(name="newtask")


@router.message(Command("new"))
@router.message(F.text == texts.BTN_NEW)
async def start_wizard(message: Message, state: FSMContext) -> None:
    await state.set_state(NewTask.waiting_title)
    await state.update_data(new_title=None, new_priority=PRIORITY_MEDIUM)
    await message.answer(
        "➕ <b>Yangi vazifa</b>\n\n"
        f"{texts.ASK_TITLE}\n\n"
        "<i>Bekor qilish uchun /cancel</i>"
    )


@router.message(NewTask.waiting_title, F.text)
async def got_title(message: Message, state: FSMContext) -> None:
    title = heuristics.clean_title(message.text, limit=200)
    await state.update_data(new_title=title)
    await state.set_state(NewTask.waiting_priority)
    await message.answer(
        f"📝 <b>{title}</b>\n\n❗️ Muhimlik darajasini tanlang:",
        reply_markup=keyboards.new_task_priority_kb(),
    )


@router.callback_query(NewTask.waiting_priority, F.data.startswith("new:prio:"))
async def got_priority(callback: CallbackQuery, state: FSMContext) -> None:
    priority = int(callback.data.rsplit(":", 1)[1])
    await state.update_data(new_priority=priority)
    await state.set_state(NewTask.waiting_time)

    data = await state.get_data()
    await safe_edit(
        callback,
        f"📝 <b>{texts.escape(data.get('new_title', ''))}</b>\n"
        f"❗️ {texts.priority_label(priority)}\n\n"
        f"{texts.ASK_TIME}",
        keyboards.new_task_time_kb(),
    )
    await callback.answer()


@router.callback_query(NewTask.waiting_time, F.data.startswith("new:time:"))
async def got_time_preset(
    callback: CallbackQuery, state: FSMContext, db: Database, user: aiosqlite.Row
) -> None:
    code = callback.data.rsplit(":", 1)[1]
    due, has_time = service.preset_due(code, user["tz"])
    await _create(callback, state, db, user, due, has_time)


@router.message(NewTask.waiting_time, F.text)
async def got_time_text(
    message: Message, state: FSMContext, db: Database, user: aiosqlite.Row
) -> None:
    due, has_time = heuristics.parse_datetime(message.text, user["tz"])
    if due is None:
        await message.answer(texts.TIME_NOT_UNDERSTOOD)
        return
    await _create(message, state, db, user, due, has_time)


@router.callback_query(F.data == "new:cancel")
async def cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    await safe_edit(callback, "❌ <i>Bekor qilindi</i>", None)
    await callback.answer()


async def _create(
    target: Message | CallbackQuery,
    state: FSMContext,
    db: Database,
    user: aiosqlite.Row,
    due,
    has_time: bool,
) -> None:
    data = await state.get_data()
    title = data.get("new_title") or "Nomsiz vazifa"
    priority = int(data.get("new_priority", PRIORITY_MEDIUM))

    parsed = ParsedTask(
        title=title,
        priority=priority,
        due_at=due,
        has_time=has_time,
        remind_offsets=[m for m in DEFAULT_OFFSETS.get(priority, [30]) if m > 0],
    )
    task_id = await service.create_from_parsed(db, user["id"], parsed, source="manual")

    await state.set_state(None)
    await state.update_data(new_title=None)

    task = await db.get_task(task_id, user["id"])
    if task is None:
        return

    if isinstance(target, CallbackQuery):
        await safe_edit(target, "✅ <b>Vazifa qo'shildi</b>", None)
        await target.answer("✅ Qo'shildi")
        if target.message is not None:
            await show_task(target.message, task, user["tz"])
    else:
        await target.answer(
            f"✅ <b>Vazifa qo'shildi</b> — {tu.fmt_datetime(due, user['tz'], has_time=has_time)}"
        )
        await show_task(target, task, user["tz"])
