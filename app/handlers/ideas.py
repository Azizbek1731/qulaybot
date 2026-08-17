"""💡 Muammo va yechim — g'oyalarni yozib borish bo'limi.

Yangi fikr yoki muammo paydo bo'lganda shu yerga qo'shiladi. Yechimini keyin
yozish, AI dan taklif so'rash yoki g'oyani vazifaga aylantirish mumkin.
"""

from __future__ import annotations

import io
import logging
import math

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import keyboards, service, texts
from ..analyzer import Analyzer, ParsedTask
from ..db import IDEA_OPEN, IDEA_SOLVED, Database
from ..states import Idea
from .render import safe_edit, show_task

log = logging.getLogger(__name__)

router = Router(name="ideas")

MAX_LEN = 2000


# ---------------------------------------------------------------------- ro'yxat

@router.message(Command("ideas"))
@router.message(F.text == texts.BTN_IDEAS)
async def open_ideas(
    message: Message, state: FSMContext, db: Database, user: aiosqlite.Row
) -> None:
    await state.set_state(None)
    if await db.count_ideas(user["id"]) == 0:
        await message.answer(
            texts.IDEAS_INTRO,
            reply_markup=keyboards.ideas_list_kb([], status="all", page=0, pages=1),
        )
        return
    await _show_list(message, db, user, status="all", page=0, state=state)


@router.callback_query(F.data.startswith("il:"))
async def on_ideas_list(
    callback: CallbackQuery, db: Database, user: aiosqlite.Row, state: FSMContext
) -> None:
    _, status, page = callback.data.split(":", 2)

    if status == "back":
        data = await state.get_data()
        status = data.get("ideas_status", "all")
        page = data.get("ideas_page", 0)

    await _show_list(callback, db, user, status=status, page=int(page), state=state)
    await callback.answer()


async def _show_list(
    target: Message | CallbackQuery,
    db: Database,
    user: aiosqlite.Row,
    *,
    status: str,
    page: int,
    state: FSMContext,
) -> None:
    page_size = keyboards.PAGE_SIZE
    total = await db.count_ideas(user["id"], status)
    pages = max(1, math.ceil(total / page_size))
    page = min(max(0, page), pages - 1)

    ideas = await db.list_ideas(
        user["id"], status=status, limit=page_size, offset=page * page_size
    )
    await state.update_data(ideas_status=status, ideas_page=page)

    if not ideas:
        body = f"{texts.ideas_header(status, 0, 0, 1)}\n\n{texts.EMPTY_IDEAS}"
    else:
        lines = [
            texts.idea_line(index, idea)
            for index, idea in enumerate(ideas, start=1 + page * page_size)
        ]
        body = texts.ideas_header(status, total, page, pages) + "\n\n" + "\n\n".join(lines)

    markup = keyboards.ideas_list_kb(ideas, status=status, page=page, pages=pages)

    if isinstance(target, CallbackQuery):
        await safe_edit(target, body, markup)
    else:
        await target.answer(body, reply_markup=markup)


# ------------------------------------------------------------- yangi g'oya (FSM)

@router.callback_query(F.data == "inew")
async def new_idea(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Idea.waiting_problem)
    await safe_edit(callback, texts.ASK_PROBLEM, None)
    await callback.answer()


@router.message(Idea.waiting_problem, F.text)
async def got_problem_text(message: Message, state: FSMContext) -> None:
    await _ask_solution(message, state, message.text.strip()[:MAX_LEN], source="text")


@router.message(Idea.waiting_problem, F.voice | F.audio)
async def got_problem_voice(
    message: Message, state: FSMContext, analyzer: Analyzer
) -> None:
    media = message.voice or message.audio
    placeholder = await message.answer(texts.LISTENING)

    try:
        file = await message.bot.get_file(media.file_id)
        buffer = io.BytesIO()
        await message.bot.download_file(file.file_path, buffer)
        text = await analyzer.transcribe(
            buffer.getvalue(), audio_mime=getattr(media, "mime_type", None) or "audio/ogg"
        )
    except Exception:  # noqa: BLE001
        log.exception("G'oya uchun ovozni yuklab bo'lmadi")
        text = None

    if not text:
        await placeholder.edit_text(texts.AI_FAILED_VOICE)
        return

    await placeholder.edit_text(f"🎧 <i>«{texts.escape(text)}»</i>")
    await _ask_solution(message, state, text[:MAX_LEN], source="voice")


async def _ask_solution(
    message: Message, state: FSMContext, problem: str, *, source: str
) -> None:
    if not problem:
        await message.answer(texts.ASK_PROBLEM)
        return
    await state.update_data(idea_problem=problem, idea_source=source)
    await state.set_state(Idea.waiting_solution)
    await message.answer(texts.ASK_SOLUTION, reply_markup=keyboards.solution_kb())


@router.message(Idea.waiting_solution, F.text)
async def got_solution(
    message: Message, state: FSMContext, db: Database, user: aiosqlite.Row
) -> None:
    data = await state.get_data()
    idea_id = await db.create_idea(
        user["id"],
        problem=data.get("idea_problem", ""),
        solution=message.text.strip()[:MAX_LEN],
        source=data.get("idea_source", "text"),
    )
    await _finish(message, state, db, user, idea_id, "✅ G'oya va yechim saqlandi")


@router.callback_query(Idea.waiting_solution, F.data == "isol:skip")
async def skip_solution(
    callback: CallbackQuery, state: FSMContext, db: Database, user: aiosqlite.Row
) -> None:
    data = await state.get_data()
    idea_id = await db.create_idea(
        user["id"],
        problem=data.get("idea_problem", ""),
        source=data.get("idea_source", "text"),
    )
    await safe_edit(callback, "💡 <b>G'oya saqlandi</b>", None)
    await callback.answer("💡 Saqlandi")
    await _finish(callback.message, state, db, user, idea_id, None)


@router.callback_query(Idea.waiting_solution, F.data == "isol:ai")
async def ai_solution_for_new(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    user: aiosqlite.Row,
    analyzer: Analyzer,
) -> None:
    data = await state.get_data()
    problem = data.get("idea_problem", "")

    await safe_edit(callback, texts.AI_THINKING, None)
    await callback.answer()

    suggestion = await analyzer.suggest_solution(problem)
    idea_id = await db.create_idea(
        user["id"],
        problem=problem,
        solution=suggestion,
        source=data.get("idea_source", "text"),
    )
    if suggestion is None and callback.message is not None:
        await callback.message.answer(texts.AI_FAILED)

    await _finish(callback.message, state, db, user, idea_id, None)


async def _finish(
    message: Message | None,
    state: FSMContext,
    db: Database,
    user: aiosqlite.Row,
    idea_id: int,
    notice: str | None,
) -> None:
    await state.set_state(None)
    await state.update_data(idea_problem=None)

    idea = await db.get_idea(idea_id, user["id"])
    if idea is None or message is None:
        return
    if notice:
        await message.answer(notice)
    await message.answer(
        texts.idea_card(idea, user["tz"]), reply_markup=keyboards.idea_kb(idea)
    )


# ------------------------------------------------------------------ g'oya amallar

@router.callback_query(F.data.startswith("i:"))
async def on_idea_action(
    callback: CallbackQuery,
    db: Database,
    user: aiosqlite.Row,
    state: FSMContext,
    analyzer: Analyzer,
) -> None:
    parts = callback.data.split(":")
    idea_id = int(parts[1])
    action = parts[2]

    idea = await db.get_idea(idea_id, user["id"])
    if idea is None:
        await callback.answer(texts.IDEA_NOT_FOUND, show_alert=True)
        return

    if action == "open":
        await safe_edit(
            callback, texts.idea_card(idea, user["tz"]), keyboards.idea_kb(idea)
        )
        await callback.answer()
        return

    if action == "sol":
        await state.set_state(Idea.waiting_edit_solution)
        await state.update_data(idea_id=idea_id)
        await safe_edit(callback, texts.ASK_SOLUTION, None)
        await callback.answer()
        return

    if action == "ai":
        await safe_edit(callback, texts.AI_THINKING, None)
        await callback.answer()

        suggestion = await analyzer.suggest_solution(idea["problem"])
        if suggestion is None:
            await _rerender(callback, db, idea_id, user)
            if callback.message is not None:
                await callback.message.answer(texts.AI_FAILED)
            return

        await db.update_idea(idea_id, user["id"], solution=suggestion, status=IDEA_SOLVED)
        await _rerender(callback, db, idea_id, user)
        return

    if action == "toggle":
        new_status = IDEA_OPEN if idea["status"] == IDEA_SOLVED else IDEA_SOLVED
        await db.update_idea(idea_id, user["id"], status=new_status)
        await _rerender(callback, db, idea_id, user)
        await callback.answer("✅ Yechildi" if new_status == IDEA_SOLVED else "↩️ Qaytarildi")
        return

    if action == "totask":
        title = idea["problem"].splitlines()[0][:200]
        task_id = await service.create_from_parsed(
            db,
            user["id"],
            ParsedTask(title=title, notes=idea["solution"], priority=3),
            source="manual",
            raw_text=idea["problem"],
        )
        task = await db.get_task(task_id, user["id"])
        await callback.answer("🔄 Vazifaga aylantirildi")
        if task is not None and callback.message is not None:
            await callback.message.answer(
                "🔄 <b>G'oya vazifaga aylantirildi.</b> Endi unga vaqt belgilang:"
            )
            await show_task(callback.message, task, user["tz"])
        return

    if action == "del":
        await safe_edit(
            callback,
            f"🗑 <b>O'chirilsinmi?</b>\n\n{texts.escape(idea['problem'][:200])}",
            keyboards.idea_delete_kb(idea_id),
        )
        await callback.answer()
        return

    if action == "delyes":
        await db.delete_idea(idea_id, user["id"])
        data = await state.get_data()
        await _show_list(
            callback, db, user,
            status=data.get("ideas_status", "all"),
            page=int(data.get("ideas_page", 0)),
            state=state,
        )
        await callback.answer("🗑 O'chirildi")
        return

    await callback.answer()


@router.message(Idea.waiting_edit_solution, F.text)
async def edit_solution(
    message: Message, state: FSMContext, db: Database, user: aiosqlite.Row
) -> None:
    data = await state.get_data()
    idea_id = int(data.get("idea_id", 0))

    await db.update_idea(
        idea_id, user["id"],
        solution=message.text.strip()[:MAX_LEN],
        status=IDEA_SOLVED,
    )
    await state.set_state(None)

    idea = await db.get_idea(idea_id, user["id"])
    if idea is None:
        await message.answer(texts.IDEA_NOT_FOUND)
        return
    await message.answer(
        texts.idea_card(idea, user["tz"]), reply_markup=keyboards.idea_kb(idea)
    )


async def _rerender(
    callback: CallbackQuery, db: Database, idea_id: int, user: aiosqlite.Row
) -> None:
    fresh = await db.get_idea(idea_id, user["id"])
    if fresh is not None:
        await safe_edit(
            callback, texts.idea_card(fresh, user["tz"]), keyboards.idea_kb(fresh)
        )
