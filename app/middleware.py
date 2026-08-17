"""Middleware: foydalanuvchini bazadan yuklash va ro'yxatdan o'tishni tekshirish."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from . import keyboards, texts
from .db import Database

log = logging.getLogger(__name__)


class UserMiddleware(BaseMiddleware):
    """Har bir yangilanishga `user` (baza yozuvi) qo'shadi.

    Ro'yxatdan o'tmagan foydalanuvchi faqat /start va kontakt yuborishi mumkin —
    qolgan hamma narsa to'sib qo'yiladi. Shu tufayli har bir foydalanuvchi
    faqat o'z ma'lumotlari bilan ishlaydi.
    """

    def __init__(self, db: Database, default_tz: str) -> None:
        self._db = db
        self._default_tz = default_tz

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return None

        user = await self._db.get_user(tg_user.id)
        if user is None:
            user = await self._db.ensure_user(
                tg_user.id,
                full_name=tg_user.full_name,
                username=tg_user.username,
                default_tz=self._default_tz,
            )

        if user["registered_at"] is None and not self._is_allowed(event):
            await self._ask_registration(event)
            return None

        data["user"] = user
        return await handler(event, data)

    @staticmethod
    def _is_allowed(event: TelegramObject) -> bool:
        if isinstance(event, Message):
            if event.contact is not None:
                return True
            return bool(event.text and event.text.startswith("/start"))
        return False

    @staticmethod
    async def _ask_registration(event: TelegramObject) -> None:
        try:
            if isinstance(event, Message):
                await event.answer(texts.NEED_REGISTER, reply_markup=keyboards.contact_kb())
            elif isinstance(event, CallbackQuery):
                await event.answer(texts.NEED_REGISTER.replace("<b>", "").replace("</b>", ""),
                                   show_alert=True)
        except Exception:  # noqa: BLE001
            log.debug("Ro'yxatdan o'tish so'rovi yuborilmadi", exc_info=True)
