"""To'liq oqim testi: Telegram serveri o'rniga soxta sessiya ishlatiladi.

Bu yerda haqiqiy handlerlar, middleware, tugmalar va baza birgalikda tekshiriladi:
ro'yxatdan o'tish → xabar yuborish → AI natijasi → ro'yxat → bajarish.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    Chat,
    Contact,
    File,
    Message,
    Update,
    User,
    Voice,
)

from app import handlers
from app import timeutil as tu
from app.analyzer import Analysis, ParsedTask
from app.config import Config
from app.db import STATUS_DONE, STATUS_PENDING, Database
from app.middleware import UserMiddleware

UID = 555
TZ = "Asia/Tashkent"


class FakeSession(BaseSession):
    """Telegram API o'rniga ishlaydigan soxta sessiya."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[Any] = []
        self._message_id = 1000

    async def close(self) -> None:  # pragma: no cover
        pass

    async def stream_content(self, *args: Any, **kwargs: Any):  # pragma: no cover
        yield b""

    async def make_request(self, bot: Bot, method: Any, timeout: int | None = None) -> Any:
        self.calls.append(method)
        name = type(method).__name__

        if name in ("SendMessage", "EditMessageText"):
            self._message_id += 1
            return Message(
                message_id=self._message_id,
                date=datetime.now(timezone.utc),
                chat=Chat(id=UID, type="private"),
                text=getattr(method, "text", ""),
            ).as_(bot)

        if name == "GetFile":
            return File(
                file_id=method.file_id,
                file_unique_id="uniq",
                file_path="voice/file_1.oga",
                file_size=2048,
            )

        if name == "GetMe":
            return User(id=1, is_bot=True, first_name="Bot", username="test_bot")

        return True

    # Yuborilgan matnlarni qulay tekshirish uchun
    def texts(self) -> list[str]:
        return [getattr(c, "text", "") or "" for c in self.calls]

    def last_text(self) -> str:
        for call in reversed(self.calls):
            text = getattr(call, "text", None)
            if text:
                return text
        return ""

    def keyboards(self) -> list[Any]:
        return [c.reply_markup for c in self.calls if getattr(c, "reply_markup", None)]

    def callback_datas(self) -> set[str]:
        found: set[str] = set()
        for markup in self.keyboards():
            for row in getattr(markup, "inline_keyboard", []) or []:
                for button in row:
                    if button.callback_data:
                        found.add(button.callback_data)
        return found


class StubAnalyzer:
    """AI o'rnida oldindan belgilangan natijani qaytaradi."""

    def __init__(self, analysis: Analysis) -> None:
        self.analysis = analysis
        self.calls: list[dict[str, Any]] = []

    async def analyze(self, **kwargs: Any) -> Analysis:
        self.calls.append(kwargs)
        return self.analysis

    async def transcribe(self, audio: bytes, **kwargs: Any) -> str:
        return "ovozdan olingan matn"

    async def suggest_solution(self, problem: str) -> str:
        return "• Birinchi qadam\n• Ikkinchi qadam"


@pytest.fixture
async def env(tmp_path):
    db = Database(tmp_path / "flow.db")
    await db.connect()

    session = FakeSession()
    bot = Bot(
        token="42:TEST",
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    analysis = Analysis(
        tasks=[
            ParsedTask(
                title="Shifokorga borish",
                priority=1,
                due_at=tu.utc_now() + timedelta(hours=5),
                has_time=True,
                category="sogliq",
                remind_offsets=[60, 10],
            ),
            ParsedTask(title="Sut olish", priority=3, category="xarid", remind_offsets=[30]),
        ],
        transcript=None,
    )
    analyzer = StubAnalyzer(analysis)

    config = Config(
        bot_token="42:TEST",
        gemini_api_key="x",
        gemini_text_models=("m",),
        gemini_voice_models=("m",),
        db_path=tmp_path / "flow.db",
        default_tz=TZ,
        tick_seconds=20,
        log_level="INFO",
    )

    dp = Dispatcher(storage=MemoryStorage(), db=db, analyzer=analyzer, config=config)
    middleware = UserMiddleware(db, TZ)
    dp.message.middleware(middleware)
    dp.callback_query.middleware(middleware)
    # aiogram routerlari modul darajasida yagona obyekt — har bir test uchun
    # ularni yangi dispatcherga qayta ulaymiz
    for router in handlers.ROUTERS:
        router._parent_router = None
    dp.include_routers(*handlers.ROUTERS)

    yield dp, bot, db, session, analyzer

    await bot.session.close()
    await db.close()


# --------------------------------------------------------------- yordamchilar

_update_id = 0
_message_id = 0


def make_message(text: str | None = None, contact: Contact | None = None) -> Update:
    global _update_id, _message_id
    _update_id += 1
    _message_id += 1
    return Update(
        update_id=_update_id,
        message=Message(
            message_id=_message_id,
            date=datetime.now(timezone.utc),
            chat=Chat(id=UID, type="private"),
            from_user=User(id=UID, is_bot=False, first_name="Aziz"),
            text=text,
            contact=contact,
        ),
    )


def make_voice(duration: int = 5) -> Update:
    global _update_id, _message_id
    _update_id += 1
    _message_id += 1
    return Update(
        update_id=_update_id,
        message=Message(
            message_id=_message_id,
            date=datetime.now(timezone.utc),
            chat=Chat(id=UID, type="private"),
            from_user=User(id=UID, is_bot=False, first_name="Aziz"),
            voice=Voice(
                file_id="voice-file-id",
                file_unique_id="uniq",
                duration=duration,
                mime_type="audio/ogg",
                file_size=2048,
            ),
        ),
    )


def make_callback(data: str, user_id: int = UID) -> Update:
    global _update_id, _message_id
    _update_id += 1
    _message_id += 1
    return Update(
        update_id=_update_id,
        callback_query=CallbackQuery(
            id=f"cb{_update_id}",
            from_user=User(id=user_id, is_bot=False, first_name="Aziz"),
            chat_instance="chat-instance",
            data=data,
            message=Message(
                message_id=_message_id,
                date=datetime.now(timezone.utc),
                chat=Chat(id=UID, type="private"),
                from_user=User(id=1, is_bot=True, first_name="Bot"),
                text="eski xabar",
            ),
        ),
    )


# --------------------------------------------------------------------- testlar

@pytest.mark.asyncio
async def test_registration_required_before_use(env):
    dp, bot, db, session, _ = env

    await dp.feed_update(bot, make_message("ertaga yigilish bor"))
    assert "ro'yxatdan o'ting" in session.last_text().lower()
    assert await db.count_tasks(UID, "all") == 0    # hech narsa saqlanmadi


@pytest.mark.asyncio
async def test_foreign_contact_rejected(env):
    dp, bot, db, session, _ = env

    await dp.feed_update(bot, make_message("/start"))
    await dp.feed_update(
        bot,
        make_message(contact=Contact(phone_number="+998900000000", first_name="Begona", user_id=999)),
    )

    user = await db.get_user(UID)
    assert user["registered_at"] is None
    assert "o'zingizning" in session.last_text()


@pytest.mark.asyncio
async def test_full_flow(env):
    dp, bot, db, session, analyzer = env

    # 1. /start → telefon so'raladi
    await dp.feed_update(bot, make_message("/start"))
    assert "telefon raqamingizni yuboring" in session.last_text().lower()

    # 2. Kontakt yuborish → ro'yxatdan o'tish
    await dp.feed_update(
        bot,
        make_message(contact=Contact(phone_number="998901234567", first_name="Aziz", user_id=UID)),
    )
    user = await db.get_user(UID)
    assert user["registered_at"] is not None
    assert user["phone"] == "+998901234567"

    # 3. Matnli xabar → AI ikkita vazifa qaytaradi, avtomatik saqlanadi
    session.calls.clear()
    await dp.feed_update(bot, make_message("ertaga shifokorga borish va sut olish"))

    assert analyzer.calls and analyzer.calls[0]["tz"] == TZ
    tasks = await db.list_tasks(UID, scope="all")
    assert len(tasks) == 2
    assert {t["title"] for t in tasks} == {"Shifokorga borish", "Sut olish"}
    assert all(t["status"] == STATUS_PENDING for t in tasks)
    assert "2 ta vazifa saqlandi" in " ".join(session.texts())

    # Eslatmalar rejalashtirildi (vaqti bor vazifa uchun)
    with_due = next(t for t in tasks if t["title"] == "Shifokorga borish")
    reminders = await db._fetchall(
        "SELECT * FROM reminders WHERE task_id = ?", (with_due["id"],)
    )
    assert len(reminders) >= 3

    # 4. Ro'yxatni ochish
    session.calls.clear()
    await dp.feed_update(bot, make_message("📋 Vazifalarim"))
    assert "Shifokorga borish" in session.last_text()
    assert f"t:{with_due['id']}:open" in session.callback_datas()

    # 5. Vazifa kartochkasini ochish
    session.calls.clear()
    await dp.feed_update(bot, make_callback(f"t:{with_due['id']}:open"))
    assert "Shifokorga borish" in session.last_text()
    assert f"t:{with_due['id']}:done" in session.callback_datas()

    # 6. Darajani o'zgartirish
    await dp.feed_update(bot, make_callback(f"t:{with_due['id']}:prio:4"))
    assert (await db.get_task(with_due["id"], UID))["priority"] == 4

    # 7. Vaqtni tayyor tugma bilan o'zgartirish (ertaga 09:00)
    await dp.feed_update(bot, make_callback(f"t:{with_due['id']}:time:em"))
    updated = await db.get_task(with_due["id"], UID)
    assert tu.to_local(tu.parse(updated["due_at"]), TZ).hour == 9

    # 8. Bajarildi
    await dp.feed_update(bot, make_callback(f"t:{with_due['id']}:done"))
    assert (await db.get_task(with_due["id"], UID))["status"] == STATUS_DONE

    # 9. O'chirish (tasdiq bilan)
    other = next(t for t in tasks if t["title"] == "Sut olish")
    await dp.feed_update(bot, make_callback(f"t:{other['id']}:del"))
    await dp.feed_update(bot, make_callback(f"t:{other['id']}:delyes"))
    assert await db.get_task(other["id"], UID) is None


@pytest.mark.asyncio
async def test_manual_confirmation_mode(env):
    dp, bot, db, session, _ = env

    await dp.feed_update(bot, make_message("/start"))
    await dp.feed_update(
        bot, make_message(contact=Contact(phone_number="998901234567", first_name="A", user_id=UID))
    )
    await db.update_user(UID, auto_save=0)          # qo'lda tasdiqlash rejimi

    session.calls.clear()
    await dp.feed_update(bot, make_message("ikkita ish bor"))

    drafts = await db.list_tasks(UID, scope="all")
    assert drafts == []                              # hali saqlanmagan (qoralama)
    assert "tasdiqlang" in session.last_text().lower() or "topildi" in " ".join(session.texts())

    batch_button = next(d for d in session.callback_datas() if d.startswith("b:"))
    await dp.feed_update(bot, make_callback(batch_button))

    saved = await db.list_tasks(UID, scope="all")
    assert len(saved) == 2 and all(t["status"] == STATUS_PENDING for t in saved)


@pytest.mark.asyncio
async def test_manual_wizard_creates_task(env):
    dp, bot, db, session, _ = env

    await dp.feed_update(bot, make_message("/start"))
    await dp.feed_update(
        bot, make_message(contact=Contact(phone_number="998901234567", first_name="A", user_id=UID))
    )

    await dp.feed_update(bot, make_message("➕ Yangi vazifa"))
    await dp.feed_update(bot, make_message("Bankka borish"))
    await dp.feed_update(bot, make_callback("new:prio:2"))
    await dp.feed_update(bot, make_callback("new:time:em"))

    tasks = await db.list_tasks(UID, scope="all")
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Bankka borish"
    assert tasks[0]["priority"] == 2
    assert tasks[0]["source"] == "manual"
    assert tu.to_local(tu.parse(tasks[0]["due_at"]), TZ).hour == 9


@pytest.mark.asyncio
async def test_settings_toggles(env):
    dp, bot, db, session, _ = env

    await dp.feed_update(bot, make_message("/start"))
    await dp.feed_update(
        bot, make_message(contact=Contact(phone_number="998901234567", first_name="A", user_id=UID))
    )

    await dp.feed_update(bot, make_message("⚙️ Sozlamalar"))
    assert "Sozlamalar" in session.last_text()

    await dp.feed_update(bot, make_callback("st:auto"))
    assert (await db.get_user(UID))["auto_save"] == 0

    await dp.feed_update(bot, make_callback("st:notify"))
    assert (await db.get_user(UID))["notify"] == 0

    await dp.feed_update(bot, make_callback("st:tz:Europe/Moscow"))
    assert (await db.get_user(UID))["tz"] == "Europe/Moscow"

    await dp.feed_update(bot, make_callback("st:digest:7"))
    assert (await db.get_user(UID))["digest_hour"] == 7

    await dp.feed_update(bot, make_callback("st:wipeyes"))
    assert await db.count_tasks(UID, "all") == 0


@pytest.mark.asyncio
async def test_sorting_and_filters(env):
    dp, bot, db, session, _ = env

    await dp.feed_update(bot, make_message("/start"))
    await dp.feed_update(
        bot, make_message(contact=Contact(phone_number="998901234567", first_name="A", user_id=UID))
    )

    await dp.feed_update(bot, make_callback("sort:priority"))
    assert (await db.get_user(UID))["sort_mode"] == "priority"

    session.calls.clear()
    await dp.feed_update(bot, make_callback("l:overdue:0"))
    assert "Muddati o'tgan" in session.last_text()


@pytest.mark.asyncio
async def test_snooze_from_reminder(env):
    dp, bot, db, session, _ = env

    await dp.feed_update(bot, make_message("/start"))
    await dp.feed_update(
        bot, make_message(contact=Contact(phone_number="998901234567", first_name="A", user_id=UID))
    )

    task_id = await db.create_task(UID, title="Dori ichish", due_at=tu.utc_now())
    await dp.feed_update(bot, make_callback(f"t:{task_id}:snz:60"))

    task = await db.get_task(task_id, UID)
    delta = (tu.parse(task["due_at"]) - tu.utc_now()).total_seconds()
    assert 3500 < delta < 3700


@pytest.mark.asyncio
async def test_other_user_cannot_touch_my_task(env):
    dp, bot, db, session, _ = env

    await dp.feed_update(bot, make_message("/start"))
    await dp.feed_update(
        bot, make_message(contact=Contact(phone_number="998901234567", first_name="A", user_id=UID))
    )
    task_id = await db.create_task(UID, title="Maxfiy ish")

    # Boshqa foydalanuvchi begona vazifa ustida amal bajarmoqchi bo'ladi
    await db.ensure_user(777, full_name="Begona", default_tz=TZ)
    await db.register_user(777, "+998900000000", "Begona")

    await dp.feed_update(bot, make_callback(f"t:{task_id}:delyes", user_id=777))
    assert await db.get_task(task_id, UID) is not None    # vazifa joyida qoldi


# ------------------------------------------------------ 💡 Muammo va yechim

async def _register(dp, bot):
    await dp.feed_update(bot, make_message("/start"))
    await dp.feed_update(
        bot, make_message(contact=Contact(phone_number="998901234567", first_name="A", user_id=UID))
    )


@pytest.mark.asyncio
async def test_idea_full_flow(env):
    dp, bot, db, session, _ = env
    await _register(dp, bot)

    # Bo'sh bo'lim ochiladi
    session.calls.clear()
    await dp.feed_update(bot, make_message("💡 Muammo va yechim"))
    assert "Muammo va yechim" in session.last_text()
    assert "inew" in session.callback_datas()

    # Yangi g'oya: muammo → yechim
    await dp.feed_update(bot, make_callback("inew"))
    await dp.feed_update(bot, make_message("Mijozlar javobni kech oladi"))
    await dp.feed_update(bot, make_message("Avtomatik javob shabloni qilish"))

    ideas = await db.list_ideas(UID)
    assert len(ideas) == 1
    assert ideas[0]["problem"] == "Mijozlar javobni kech oladi"
    assert ideas[0]["solution"] == "Avtomatik javob shabloni qilish"
    assert ideas[0]["status"] == "solved"

    idea_id = ideas[0]["id"]

    # Holatni almashtirish
    await dp.feed_update(bot, make_callback(f"i:{idea_id}:toggle"))
    assert (await db.get_idea(idea_id, UID))["status"] == "open"

    # Yechimni tahrirlash
    await dp.feed_update(bot, make_callback(f"i:{idea_id}:sol"))
    await dp.feed_update(bot, make_message("Yangi yechim matni"))
    updated = await db.get_idea(idea_id, UID)
    assert updated["solution"] == "Yangi yechim matni"
    assert updated["status"] == "solved"

    # Vazifaga aylantirish
    await dp.feed_update(bot, make_callback(f"i:{idea_id}:totask"))
    tasks = await db.list_tasks(UID, scope="all")
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Mijozlar javobni kech oladi"
    assert tasks[0]["notes"] == "Yangi yechim matni"

    # O'chirish
    await dp.feed_update(bot, make_callback(f"i:{idea_id}:del"))
    await dp.feed_update(bot, make_callback(f"i:{idea_id}:delyes"))
    assert await db.get_idea(idea_id, UID) is None


@pytest.mark.asyncio
async def test_idea_without_solution_and_ai_suggestion(env):
    dp, bot, db, session, _ = env
    await _register(dp, bot)

    # Yechimsiz saqlash
    await dp.feed_update(bot, make_callback("inew"))
    await dp.feed_update(bot, make_message("Vaqtni rejalashtira olmayapman"))
    await dp.feed_update(bot, make_callback("isol:skip"))

    ideas = await db.list_ideas(UID)
    assert len(ideas) == 1 and ideas[0]["solution"] is None and ideas[0]["status"] == "open"

    # AI yechim taklif qiladi
    await dp.feed_update(bot, make_callback(f"i:{ideas[0]['id']}:ai"))
    idea = await db.get_idea(ideas[0]["id"], UID)
    assert "Birinchi qadam" in idea["solution"]
    assert idea["status"] == "solved"


@pytest.mark.asyncio
async def test_idea_from_voice(env):
    dp, bot, db, session, _ = env
    await _register(dp, bot)

    await dp.feed_update(bot, make_callback("inew"))
    await dp.feed_update(bot, make_voice())
    await dp.feed_update(bot, make_callback("isol:ai"))

    ideas = await db.list_ideas(UID)
    assert len(ideas) == 1
    assert ideas[0]["problem"] == "ovozdan olingan matn"
    assert ideas[0]["source"] == "voice"


@pytest.mark.asyncio
async def test_ideas_are_private(env):
    dp, bot, db, session, _ = env
    await _register(dp, bot)

    idea_id = await db.create_idea(UID, problem="Maxfiy g'oya")
    await db.ensure_user(777, full_name="Begona", default_tz=TZ)
    await db.register_user(777, "+998900000000", "Begona")

    await dp.feed_update(bot, make_callback(f"i:{idea_id}:delyes", user_id=777))
    assert await db.get_idea(idea_id, UID) is not None
    assert await db.list_ideas(777) == []


@pytest.mark.asyncio
async def test_admin_contact(env):
    dp, bot, db, session, _ = env
    await _register(dp, bot)

    session.calls.clear()
    await dp.feed_update(bot, make_message("✉️ Adminga yozish"))
    assert "@firstpremiumuser" in session.last_text()

    urls = [
        b.url
        for markup in session.keyboards()
        for row in getattr(markup, "inline_keyboard", []) or []
        for b in row
        if b.url
    ]
    assert "https://t.me/firstpremiumuser" in urls


@pytest.mark.asyncio
async def test_author_is_shown(env):
    dp, bot, db, session, _ = env

    await dp.feed_update(bot, make_message("/start"))
    assert "Azizbek Atoyev" in session.last_text()

    await dp.feed_update(
        bot, make_message(contact=Contact(phone_number="998901234567", first_name="A", user_id=UID))
    )
    session.calls.clear()
    await dp.feed_update(bot, make_message("❓ Yordam"))
    assert "Azizbek Atoyev" in session.last_text()
