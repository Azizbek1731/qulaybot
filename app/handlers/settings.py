"""Sozlamalar: avtomatik saqlash, eslatmalar, vaqt mintaqasi, kunlik xulosa."""

from __future__ import annotations

import logging

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import keyboards, texts
from ..db import Database
from .render import safe_edit

log = logging.getLogger(__name__)

router = Router(name="settings")


@router.message(Command("settings"))
@router.message(F.text == texts.BTN_SETTINGS)
async def open_settings(
    message: Message, state: FSMContext, user: aiosqlite.Row
) -> None:
    await state.set_state(None)
    await message.answer(texts.settings_text(user), reply_markup=keyboards.settings_kb(user))


@router.callback_query(F.data.startswith("st:"))
async def on_settings(
    callback: CallbackQuery, db: Database, user: aiosqlite.Row
) -> None:
    parts = callback.data.split(":")
    key = parts[1]
    arg = parts[2] if len(parts) > 2 else None
    user_id = user["id"]

    if key == "auto":
        await db.update_user(user_id, auto_save=0 if user["auto_save"] else 1)
        await _refresh(callback, db, user_id)
        await callback.answer(
            "🤖 Avtomatik saqlash o'chirildi" if user["auto_save"]
            else "🤖 Avtomatik saqlash yoqildi"
        )
        return

    if key == "notify":
        await db.update_user(user_id, notify=0 if user["notify"] else 1)
        await _refresh(callback, db, user_id)
        await callback.answer(
            "🔕 Eslatmalar o'chirildi" if user["notify"] else "🔔 Eslatmalar yoqildi"
        )
        return

    if key == "tz":
        if arg is None:
            await safe_edit(
                callback,
                "🌍 <b>Vaqt mintaqangizni tanlang</b>\n\n"
                "<i>Eslatmalar shu mintaqa bo'yicha yuboriladi.</i>",
                keyboards.tz_kb(),
            )
            await callback.answer()
            return

        tz = ":".join(parts[2:])  # "Asia/Tashkent"
        await db.update_user(user_id, tz=tz)
        await _refresh(callback, db, user_id)
        await callback.answer(f"🌍 {tz}")
        return

    if key == "digest":
        if arg is None:
            await safe_edit(
                callback,
                "🌅 <b>Kunlik xulosa</b>\n\n"
                "Har kuni belgilangan soatda bugungi rejalaringizni yuboraman.",
                keyboards.digest_kb(),
            )
            await callback.answer()
            return

        hour = int(arg)
        await db.update_user(user_id, digest_hour=hour)
        await _refresh(callback, db, user_id)
        await callback.answer(
            "🚫 Kunlik xulosa o'chirildi" if hour < 0 else f"🌅 Har kuni {hour:02d}:00"
        )
        return

    if key == "wipe":
        await safe_edit(
            callback,
            "⚠️ <b>Diqqat!</b>\n\nBarcha vazifalaringiz va eslatmalaringiz "
            "butunlay o'chiriladi. Bu amalni qaytarib bo'lmaydi.",
            keyboards.wipe_confirm_kb(),
        )
        await callback.answer()
        return

    if key == "wipeyes":
        await db.delete_user_data(user_id)
        await _refresh(callback, db, user_id)
        await callback.answer("🗑 Barcha vazifalar o'chirildi", show_alert=True)
        return

    if key == "back":
        await _refresh(callback, db, user_id)
        await callback.answer()
        return

    await callback.answer()


async def _refresh(callback: CallbackQuery, db: Database, user_id: int) -> None:
    fresh = await db.get_user(user_id)
    if fresh is None:
        return
    await safe_edit(callback, texts.settings_text(fresh), keyboards.settings_kb(fresh))
