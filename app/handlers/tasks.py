"""Vazifalar ro'yxati va vazifa ustidagi barcha amallar."""

from __future__ import annotations

import logging

import aiosqlite
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import heuristics, keyboards, service, texts, timeutil as tu
from ..db import STATUS_DRAFT, Database
from ..states import TaskEdit
from .render import list_context, safe_edit, show_list, show_task

log = logging.getLogger(__name__)

router = Router(name="tasks")


async def _rerender(
    callback: CallbackQuery, db: Database, task_id: int, user: aiosqlite.Row
) -> aiosqlite.Row | None:
    """Vazifa kartochkasini bazadagi yangi holat bilan qayta chizadi."""
    fresh = await db.get_task(task_id, user["id"])
    if fresh is not None:
        await show_task(callback, fresh, user["tz"])
    return fresh


# --------------------------------------------------------------------- ro'yxat

@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data.startswith("l:"))
async def on_list(
    callback: CallbackQuery, db: Database, user: aiosqlite.Row, state: FSMContext
) -> None:
    _, scope, page = callback.data.split(":", 2)
    await show_list(callback, db, user, scope=scope, page=int(page), state=state)
    await callback.answer()


@router.callback_query(F.data == "back:list")
async def on_back(
    callback: CallbackQuery, db: Database, user: aiosqlite.Row, state: FSMContext
) -> None:
    scope, page = await list_context(state)
    await show_list(callback, db, user, scope=scope, page=page, state=state)
    await callback.answer()


@router.callback_query(F.data == "sortmenu")
async def on_sort_menu(
    callback: CallbackQuery, user: aiosqlite.Row, state: FSMContext
) -> None:
    scope, _ = await list_context(state)
    await safe_edit(
        callback,
        "🔀 <b>Saralash tartibi</b>\n\n"
        "🧠 <i>Aqlli</i> — muddati yaqinlari va muhimlari yuqorida\n"
        "⏰ <i>Vaqt</i> — faqat muddat bo'yicha\n"
        "❗️ <i>Daraja</i> — avval shoshilinchlari\n"
        "🆕 <i>Yangi</i> — oxirgi qo'shilganlar",
        keyboards.sort_kb(user["sort_mode"], scope),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sort:"))
async def on_sort(
    callback: CallbackQuery, db: Database, user: aiosqlite.Row, state: FSMContext
) -> None:
    mode = callback.data.split(":", 1)[1]
    await db.update_user(user["id"], sort_mode=mode)
    fresh = await db.get_user(user["id"])
    scope, page = await list_context(state)
    await show_list(callback, db, fresh, scope=scope, page=page, state=state)
    await callback.answer(f"🔀 Saralash: {texts.SORT_NAME.get(mode, mode)}")


# ------------------------------------------------------------ qoralamalar (AI)

@router.callback_query(F.data.startswith("b:"))
async def on_batch_save(
    callback: CallbackQuery, db: Database, user: aiosqlite.Row
) -> None:
    _, batch, _action = callback.data.split(":", 2)
    drafts = await db.list_drafts(user["id"], batch)

    for draft in drafts:
        await service.activate_draft(db, draft["id"], user["id"])

    if callback.message is not None:
        await safe_edit(callback, f"✅ <b>{len(drafts)} ta vazifa saqlandi</b>", None)
    await callback.answer(f"✅ {len(drafts)} ta vazifa saqlandi")


# --------------------------------------------------------------- vazifa amallar

@router.callback_query(F.data.startswith("t:"))
async def on_task_action(
    callback: CallbackQuery,
    db: Database,
    user: aiosqlite.Row,
    state: FSMContext,
) -> None:
    parts = callback.data.split(":")
    task_id = int(parts[1])
    action = parts[2]
    arg = parts[3] if len(parts) > 3 else None

    task = await db.get_task(task_id, user["id"])
    if task is None:
        await callback.answer(texts.TASK_NOT_FOUND, show_alert=True)
        return

    tz = user["tz"]

    # -- ko'rish
    if action == "open":
        await show_task(callback, task, tz)
        await callback.answer()
        return

    # -- bajarildi / qaytarish
    if action == "done":
        next_due = await service.complete(db, task, tz)
        fresh = await db.get_task(task_id, user["id"])
        if fresh is not None:
            await show_task(callback, fresh, tz)
        if next_due is not None:
            await callback.answer(f"✅ Bajarildi! Keyingisi: {tu.fmt_datetime(next_due, tz)}")
        else:
            await callback.answer("✅ Bajarildi. Barakalla!")
        return

    if action == "undone":
        await service.uncomplete(db, task)
        fresh = await db.get_task(task_id, user["id"])
        if fresh is not None:
            await show_task(callback, fresh, tz)
        await callback.answer("↩️ Bajarilmagan holatga qaytarildi")
        return

    # -- o'chirish
    if action == "del":
        await safe_edit(
            callback,
            f"🗑 <b>{texts.escape(task['title'])}</b>\n\nRostdan o'chirilsinmi?",
            keyboards.confirm_delete_kb(task_id),
        )
        await callback.answer()
        return

    if action == "delyes":
        await db.delete_task(task_id, user["id"])
        scope, page = await list_context(state)
        await show_list(callback, db, user, scope=scope, page=page, state=state)
        await callback.answer("🗑 O'chirildi")
        return

    # -- muhimlik darajasi
    if action == "prio":
        if arg is None:
            await safe_edit(
                callback,
                f"❗️ <b>Muhimlik darajasi</b>\n\n{texts.escape(task['title'])}\n\n"
                f"Hozirgi: {texts.priority_label(task['priority'])}",
                keyboards.priority_kb(task_id),
            )
            await callback.answer()
            return

        await db.update_task(task_id, user["id"], priority=int(arg))
        await service.plan_reminders(db, task_id, user["id"])
        await _rerender(callback, db, task_id, user)
        await callback.answer(f"Daraja: {texts.PRIORITY_NAME[int(arg)]}")
        return

    # -- vaqt
    if action == "time":
        if arg is None:
            await safe_edit(
                callback,
                f"⏰ <b>Muddatni tanlang</b>\n\n{texts.escape(task['title'])}\n\n"
                f"Hozirgi: {tu.fmt_datetime(tu.parse(task['due_at']), tz, has_time=bool(task['has_time']))}",
                keyboards.time_kb(task_id),
            )
            await callback.answer()
            return

        if arg == "man":
            await state.set_state(TaskEdit.waiting_time)
            await state.update_data(task_id=task_id)
            await safe_edit(callback, texts.ASK_TIME, None)
            await callback.answer()
            return

        due, has_time = service.preset_due(arg, tz)
        await service.set_due(db, task_id, user["id"], due, has_time=has_time)
        await _rerender(callback, db, task_id, user)
        await callback.answer(
            "🚫 Vaqt olib tashlandi" if due is None else f"⏰ {tu.fmt_datetime(due, tz)}"
        )
        return

    # -- takrorlanish
    if action == "rec":
        if arg is None:
            await safe_edit(
                callback,
                f"🔁 <b>Takrorlanish</b>\n\n{texts.escape(task['title'])}",
                keyboards.recurrence_kb(task_id),
            )
            await callback.answer()
            return

        await db.update_task(task_id, user["id"], recurrence=arg)
        await _rerender(callback, db, task_id, user)
        await callback.answer("🔁 Yangilandi")
        return

    # -- nomini o'zgartirish
    if action == "title":
        await state.set_state(TaskEdit.waiting_title)
        await state.update_data(task_id=task_id)
        await safe_edit(callback, texts.ASK_TITLE, None)
        await callback.answer()
        return

    # -- qoralamani saqlash / bekor qilish
    if action == "save":
        fresh = await service.activate_draft(db, task_id, user["id"])
        if fresh is not None:
            await show_task(callback, fresh, tz)
        await callback.answer("✅ Saqlandi")
        return

    if action == "drop":
        await db.delete_task(task_id, user["id"])
        await safe_edit(callback, "❌ <i>Bekor qilindi</i>", None)
        await callback.answer("Bekor qilindi")
        return

    # -- keyinroq eslatish
    if action == "snz":
        minutes = -1 if arg == "tom" else int(arg or 10)
        target = await service.snooze(db, task_id, user["id"], minutes, tz)
        fresh = await db.get_task(task_id, user["id"])
        await safe_edit(
            callback,
            f"😴 <b>{texts.escape(task['title'])}</b>\n\n"
            f"⏰ Yangi vaqt: <b>{tu.fmt_datetime(target, tz)}</b> "
            f"<i>({tu.fmt_relative(target)})</i>",
            keyboards.task_kb(fresh) if fresh is not None else None,
        )
        await callback.answer("⏰ Keyinroq eslataman")
        return

    await callback.answer()


# ----------------------------------------------------------- tahrirlash (FSM)

@router.message(TaskEdit.waiting_title, F.text)
async def on_new_title(
    message: Message, state: FSMContext, db: Database, user: aiosqlite.Row
) -> None:
    data = await state.get_data()
    task_id = int(data.get("task_id", 0))

    title = heuristics.clean_title(message.text, limit=200)
    await db.update_task(task_id, user["id"], title=title)
    await state.set_state(None)

    task = await db.get_task(task_id, user["id"])
    if task is None:
        await message.answer(texts.TASK_NOT_FOUND)
        return
    await show_task(message, task, user["tz"])


@router.message(TaskEdit.waiting_time, F.text)
async def on_new_time(
    message: Message, state: FSMContext, db: Database, user: aiosqlite.Row
) -> None:
    data = await state.get_data()
    task_id = int(data.get("task_id", 0))

    due, has_time = heuristics.parse_datetime(message.text, user["tz"])
    if due is None:
        await message.answer(texts.TIME_NOT_UNDERSTOOD)
        return

    task = await db.get_task(task_id, user["id"])
    if task is None:
        await state.set_state(None)
        await message.answer(texts.TASK_NOT_FOUND)
        return

    if task["status"] == STATUS_DRAFT:
        await db.update_task(task_id, user["id"], due_at=due, has_time=int(has_time))
    else:
        await service.set_due(db, task_id, user["id"], due, has_time=has_time)

    await state.set_state(None)
    fresh = await db.get_task(task_id, user["id"])
    await message.answer(f"⏰ Muddat: <b>{tu.fmt_datetime(due, user['tz'], has_time=has_time)}</b>")
    if fresh is not None:
        await show_task(message, fresh, user["tz"])
