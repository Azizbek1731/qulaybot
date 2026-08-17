"""Matn va ovozli xabarlarni qabul qilib, AI orqali vazifaga aylantirish."""

from __future__ import annotations

import io
import logging
from html import escape

import aiosqlite
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .. import heuristics, keyboards, service, texts
from ..analyzer import MAX_AUDIO_BYTES, Analysis, Analyzer, parsed_from_fallback
from ..db import STATUS_DRAFT, STATUS_PENDING, Database
from .render import show_task

log = logging.getLogger(__name__)

router = Router(name="capture")


@router.message(StateFilter(None), F.voice)
@router.message(StateFilter(None), F.audio)
async def on_voice(
    message: Message,
    state: FSMContext,
    db: Database,
    analyzer: Analyzer,
    user: aiosqlite.Row,
) -> None:
    media = message.voice or message.audio
    if media is None:
        return

    if (media.file_size or 0) > MAX_AUDIO_BYTES:
        await message.answer(texts.VOICE_TOO_BIG)
        return

    placeholder = await message.answer(texts.LISTENING)

    try:
        audio = await _download(message, media.file_id)
    except Exception:  # noqa: BLE001
        log.exception("Ovozli xabarni yuklab bo'lmadi")
        await placeholder.edit_text(texts.AI_FAILED_VOICE)
        return

    mime = getattr(media, "mime_type", None) or "audio/ogg"
    analysis = await analyzer.analyze(tz=user["tz"], audio=audio, audio_mime=mime)

    await _deliver(
        message, placeholder, state, db, user, analysis,
        source="voice", raw_text=analysis.transcript,
    )


@router.message(StateFilter(None), F.text & ~F.text.startswith("/"))
async def on_text(
    message: Message,
    state: FSMContext,
    db: Database,
    analyzer: Analyzer,
    user: aiosqlite.Row,
) -> None:
    text = (message.text or "").strip()
    if not text or text in texts.MENU_BUTTONS:
        return

    placeholder = await message.answer(texts.ANALYZING)
    analysis = await analyzer.analyze(tz=user["tz"], text=text)

    await _deliver(
        message, placeholder, state, db, user, analysis, source="text", raw_text=text
    )


@router.message(StateFilter(None), F.photo | F.document | F.video | F.sticker)
async def on_unsupported(message: Message) -> None:
    await message.answer(
        "📎 Hozircha faqat <b>matn</b> va <b>ovozli xabar</b>ni tushunaman.\n"
        "Vazifangizni yozing yoki aytib yuboring."
    )


@router.callback_query(F.data == "raw:save")
async def on_raw_save(
    callback: CallbackQuery, state: FSMContext, db: Database, user: aiosqlite.Row
) -> None:
    data = await state.get_data()
    raw = data.get("raw_pending")
    if not raw:
        await callback.answer("Matn topilmadi", show_alert=True)
        return

    parsed = parsed_from_fallback(heuristics.fallback_parse(raw, user["tz"]))
    task_id = await service.create_from_parsed(
        db, user["id"], parsed, status=STATUS_PENDING, source="text", raw_text=raw
    )
    await state.update_data(raw_pending=None)

    task = await db.get_task(task_id, user["id"])
    if task is not None:
        await show_task(callback, task, user["tz"])
    await callback.answer("✅ Saqlandi")


# ------------------------------------------------------------------- ichkarida

async def _download(message: Message, file_id: str) -> bytes:
    file = await message.bot.get_file(file_id)
    buffer = io.BytesIO()
    await message.bot.download_file(file.file_path, buffer)
    return buffer.getvalue()


async def _deliver(
    message: Message,
    placeholder: Message,
    state: FSMContext,
    db: Database,
    user: aiosqlite.Row,
    analysis: Analysis,
    *,
    source: str,
    raw_text: str | None,
) -> None:
    """Tahlil natijasini foydalanuvchiga ko'rsatadi va saqlaydi."""

    if not analysis.tasks:
        if source == "voice" and analysis.error:
            await placeholder.edit_text(texts.AI_FAILED_VOICE)
            return

        head = ""
        if analysis.transcript:
            head = f"🎧 <i>«{escape(analysis.transcript)}»</i>\n\n"

        await state.update_data(raw_pending=raw_text or analysis.transcript)
        await placeholder.edit_text(
            head + texts.NO_TASKS_FOUND,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="💾 Baribir saqlash", callback_data="raw:save")]
                ]
            ),
        )
        return

    auto = bool(user["auto_save"])
    status = STATUS_PENDING if auto else STATUS_DRAFT
    batch = str(message.message_id)

    task_ids: list[int] = []
    for parsed in analysis.tasks:
        task_ids.append(
            await service.create_from_parsed(
                db, user["id"], parsed,
                status=status, source=source, raw_text=raw_text, batch=batch,
            )
        )

    count = len(task_ids)
    header_parts: list[str] = []

    if analysis.transcript:
        header_parts.append(f"🎧 <i>«{escape(analysis.transcript)}»</i>")

    if auto:
        header_parts.append(f"✅ <b>{count} ta vazifa saqlandi</b>")
    else:
        header_parts.append(f"🔎 <b>{count} ta vazifa topildi</b> — tasdiqlang:")

    if not analysis.used_ai:
        header_parts.append(
            "⚠️ <i>AI vaqtincha javob bermadi — oddiy tahlil qilindi. "
            "Kerak bo'lsa vaqti va darajasini o'zgartiring.</i>"
        )

    await placeholder.edit_text("\n\n".join(header_parts))

    for task_id in task_ids:
        task = await db.get_task(task_id, user["id"])
        if task is None:
            continue
        markup = (
            keyboards.task_kb(task)
            if auto
            else keyboards.draft_kb(task_id, batch=batch, count=count)
        )
        await message.answer(
            texts.task_card(task, user["tz"], draft=not auto), reply_markup=markup
        )
