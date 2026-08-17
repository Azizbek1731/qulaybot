"""Ro'yxatdan o'tish, asosiy menyu, yordam va statistika."""

from __future__ import annotations

import logging
import re

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from .. import keyboards, texts
from ..config import Config
from ..db import Database
from .render import show_list

log = logging.getLogger(__name__)

router = Router(name="start")


def _normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    return f"+{digits}" if digits else raw


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user: aiosqlite.Row) -> None:
    await state.clear()

    if user["registered_at"]:
        await message.answer(
            f"👋 Yana xush kelibsiz, <b>{message.from_user.first_name}</b>!\n"
            "<i>👨‍💻 Azizbek Atoyev tomonidan yaratilgan</i>\n\n"
            "Nima qilishim kerakligini yozing yoki ovozli xabar yuboring.",
            reply_markup=keyboards.main_menu(),
        )
        return

    await message.answer(texts.WELCOME_NEW, reply_markup=keyboards.contact_kb())


@router.message(F.contact)
async def on_contact(
    message: Message, db: Database, user: aiosqlite.Row, config: Config
) -> None:
    contact = message.contact

    # Boshqa odamning kontaktini yuborish orqali ro'yxatdan o'tib bo'lmaydi
    if contact.user_id != message.from_user.id:
        await message.answer(texts.CONTACT_FOREIGN, reply_markup=keyboards.contact_kb())
        return

    if user["registered_at"]:
        await db.update_user(message.from_user.id, phone=_normalize_phone(contact.phone_number))
        await message.answer("✅ Telefon raqamingiz yangilandi.", reply_markup=keyboards.main_menu())
        return

    phone = _normalize_phone(contact.phone_number)
    await db.register_user(message.from_user.id, phone, message.from_user.full_name)
    log.info("Yangi foydalanuvchi ro'yxatdan o'tdi: %s", message.from_user.id)

    await message.answer(
        texts.REGISTERED.format(phone=phone, tz=user["tz"] or config.default_tz),
        reply_markup=keyboards.main_menu(),
    )


@router.message(Command("help"))
@router.message(F.text == texts.BTN_HELP)
async def cmd_help(message: Message, state: FSMContext) -> None:
    await state.set_state(None)
    await message.answer(texts.HELP, reply_markup=keyboards.main_menu())


@router.message(Command("admin"))
@router.message(F.text == texts.BTN_ADMIN)
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.set_state(None)
    await message.answer(texts.ADMIN_TEXT, reply_markup=keyboards.admin_kb())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.set_state(None)
    await message.answer("↩️ Bekor qilindi.", reply_markup=keyboards.main_menu())


@router.message(Command("stats"))
@router.message(F.text == texts.BTN_STATS)
async def cmd_stats(
    message: Message, state: FSMContext, db: Database, user: aiosqlite.Row
) -> None:
    await state.set_state(None)
    data = await db.stats(user["id"], user["tz"])
    await message.answer(texts.stats_text(data, user["tz"]), reply_markup=keyboards.main_menu())


@router.message(Command("tasks"))
@router.message(F.text == texts.BTN_TASKS)
async def cmd_tasks(
    message: Message, db: Database, user: aiosqlite.Row, state: FSMContext
) -> None:
    await state.set_state(None)
    await show_list(message, db, user, scope="all", page=0, state=state)


@router.message(Command("today"))
@router.message(F.text == texts.BTN_TODAY)
async def cmd_today(
    message: Message, db: Database, user: aiosqlite.Row, state: FSMContext
) -> None:
    await state.set_state(None)
    await show_list(message, db, user, scope="today", page=0, state=state)
