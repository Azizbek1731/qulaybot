"""Xabarlarni chizish uchun umumiy yordamchilar."""

from __future__ import annotations

import logging
import math

import aiosqlite
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from .. import keyboards, texts
from ..db import STATUS_DRAFT, Database

log = logging.getLogger(__name__)


async def safe_edit(
    callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None
) -> None:
    """Xabarni tahrirlaydi; o'zgarish bo'lmasa jim qoladi."""
    if callback.message is None:
        return
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        # Xabar juda eski bo'lsa yoki tahrirlab bo'lmasa — yangisini yuboramiz
        try:
            await callback.message.answer(text, reply_markup=markup)
        except Exception:  # noqa: BLE001
            log.debug("Xabarni yangilab bo'lmadi", exc_info=True)


def task_markup(task: aiosqlite.Row) -> InlineKeyboardMarkup:
    if task["status"] == STATUS_DRAFT:
        return keyboards.draft_edit_kb(task["id"])
    return keyboards.task_kb(task)


async def show_task(
    target: Message | CallbackQuery, task: aiosqlite.Row, tz: str
) -> None:
    text = texts.task_card(task, tz, draft=task["status"] == STATUS_DRAFT)
    markup = task_markup(task)

    if isinstance(target, CallbackQuery):
        await safe_edit(target, text, markup)
    else:
        await target.answer(text, reply_markup=markup)


async def show_list(
    target: Message | CallbackQuery,
    db: Database,
    user: aiosqlite.Row,
    *,
    scope: str,
    page: int = 0,
    state: FSMContext | None = None,
) -> None:
    page_size = keyboards.PAGE_SIZE
    sort_mode = user["sort_mode"]

    total = await db.count_tasks(user["id"], scope)
    pages = max(1, math.ceil(total / page_size))
    page = min(max(0, page), pages - 1)

    tasks = await db.list_tasks(
        user["id"], scope=scope, sort_mode=sort_mode,
        limit=page_size, offset=page * page_size,
    )

    if state is not None:
        await state.update_data(list_scope=scope, list_page=page)

    if not tasks:
        body = f"{texts.list_header(scope, sort_mode, 0, 0, 1)}\n\n{texts.EMPTY_LIST}"
    else:
        lines = [
            texts.task_line(index, task, user["tz"])
            for index, task in enumerate(tasks, start=1 + page * page_size)
        ]
        body = texts.list_header(scope, sort_mode, total, page, pages) + "\n\n" + "\n".join(lines)

    markup = keyboards.list_kb(tasks, scope=scope, page=page, pages=pages)

    if isinstance(target, CallbackQuery):
        await safe_edit(target, body, markup)
    else:
        await target.answer(body, reply_markup=markup)


async def list_context(state: FSMContext) -> tuple[str, int]:
    data = await state.get_data()
    return data.get("list_scope", "today"), int(data.get("list_page", 0))
