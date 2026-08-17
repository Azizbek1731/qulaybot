"""Telegram tugmalari (inline va reply klaviaturalar)."""

from __future__ import annotations

import aiosqlite
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from . import texts
from .texts import PRIORITY_EMOJI

PAGE_SIZE = 8

TZ_OPTIONS = [
    ("🇺🇿 Toshkent", "Asia/Tashkent"),
    ("🇰🇿 Almati", "Asia/Almaty"),
    ("🇷🇺 Moskva", "Europe/Moscow"),
    ("🇦🇪 Dubay", "Asia/Dubai"),
    ("🇹🇷 Istanbul", "Europe/Istanbul"),
    ("🇩🇪 Berlin", "Europe/Berlin"),
    ("🇬🇧 London", "Europe/London"),
    ("🇰🇷 Seul", "Asia/Seoul"),
    ("🇺🇸 Nyu-York", "America/New_York"),
]

TIME_PRESETS = [
    ("⏱ 1 soatdan keyin", "1h"),
    ("⏱ 3 soatdan keyin", "3h"),
    ("🌇 Bugun 19:00", "te"),
    ("🌅 Ertaga 09:00", "em"),
    ("🌆 Ertaga 19:00", "ee"),
    ("📆 Indinga 09:00", "2d"),
    ("🗓 Keyingi hafta", "nw"),
    ("✍️ Qo'lda kiritish", "man"),
]

RECURRENCE_PRESETS = [
    ("🚫 Takrorlanmaydi", "none"),
    ("📅 Har kuni", "daily"),
    ("💼 Ish kunlari", "weekdays"),
    ("🗓 Har hafta", "weekly"),
    ("📆 Har oy", "monthly"),
    ("🎂 Har yili", "yearly"),
]


def contact_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Telefon raqamingizni yuboring",
    )


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_TASKS), KeyboardButton(text=texts.BTN_TODAY)],
            [KeyboardButton(text=texts.BTN_NEW), KeyboardButton(text=texts.BTN_IDEAS)],
            [KeyboardButton(text=texts.BTN_STATS), KeyboardButton(text=texts.BTN_SETTINGS)],
            [KeyboardButton(text=texts.BTN_HELP), KeyboardButton(text=texts.BTN_ADMIN)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Yozing yoki ovozli xabar yuboring...",
    )


# ------------------------------------------------------------------ vazifalar

def draft_kb(task_id: int, *, batch: str | None = None, count: int = 1) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="✅ Saqlash", callback_data=f"t:{task_id}:save"),
            InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"t:{task_id}:edit"),
            InlineKeyboardButton(text="❌ Bekor", callback_data=f"t:{task_id}:drop"),
        ]
    ]
    if batch and count > 1:
        rows.append(
            [InlineKeyboardButton(text=f"✅ Hammasini saqlash ({count})", callback_data=f"b:{batch}:save")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def draft_edit_kb(task_id: int) -> InlineKeyboardMarkup:
    """Saqlanmagan qoralamani tahrirlash tugmalari."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❗️ Daraja", callback_data=f"t:{task_id}:prio"),
                InlineKeyboardButton(text="⏰ Vaqt", callback_data=f"t:{task_id}:time"),
            ],
            [
                InlineKeyboardButton(text="✏️ Nomi", callback_data=f"t:{task_id}:title"),
                InlineKeyboardButton(text="🔁 Takror", callback_data=f"t:{task_id}:rec"),
            ],
            [
                InlineKeyboardButton(text="✅ Saqlash", callback_data=f"t:{task_id}:save"),
                InlineKeyboardButton(text="❌ Bekor", callback_data=f"t:{task_id}:drop"),
            ],
        ]
    )


def task_kb(task: aiosqlite.Row) -> InlineKeyboardMarkup:
    task_id = task["id"]
    if task["status"] == "done":
        rows = [
            [
                InlineKeyboardButton(text="↩️ Qaytarish", callback_data=f"t:{task_id}:undone"),
                InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"t:{task_id}:del"),
            ],
            [InlineKeyboardButton(text="⬅️ Ro'yxatga", callback_data="back:list")],
        ]
    else:
        rows = [
            [
                InlineKeyboardButton(text="✅ Bajardim", callback_data=f"t:{task_id}:done"),
                InlineKeyboardButton(text="⏰ Vaqt", callback_data=f"t:{task_id}:time"),
            ],
            [
                InlineKeyboardButton(text="❗️ Daraja", callback_data=f"t:{task_id}:prio"),
                InlineKeyboardButton(text="🔁 Takror", callback_data=f"t:{task_id}:rec"),
            ],
            [
                InlineKeyboardButton(text="✏️ Nomi", callback_data=f"t:{task_id}:title"),
                InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"t:{task_id}:del"),
            ],
            [InlineKeyboardButton(text="⬅️ Ro'yxatga", callback_data="back:list")],
        ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def priority_kb(task_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{PRIORITY_EMOJI[p]} {texts.PRIORITY_NAME[p]}",
                callback_data=f"t:{task_id}:prio:{p}",
            )
        ]
        for p in (1, 2, 3, 4)
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"t:{task_id}:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def time_kb(task_id: int, *, allow_clear: bool = True) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"t:{task_id}:time:{code}")
        for label, code in TIME_PRESETS
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    if allow_clear:
        rows.append(
            [InlineKeyboardButton(text="🚫 Vaqtni olib tashlash", callback_data=f"t:{task_id}:time:clr")]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"t:{task_id}:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def recurrence_kb(task_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"t:{task_id}:rec:{code}")]
        for label, code in RECURRENCE_PRESETS
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"t:{task_id}:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_delete_kb(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Ha, o'chirilsin", callback_data=f"t:{task_id}:delyes"),
                InlineKeyboardButton(text="⬅️ Yo'q", callback_data=f"t:{task_id}:open"),
            ]
        ]
    )


def list_kb(
    tasks: list[aiosqlite.Row],
    *,
    scope: str,
    page: int,
    pages: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for index, task in enumerate(tasks, start=1 + page * PAGE_SIZE):
        title = task["title"]
        label = f"{index}. {PRIORITY_EMOJI.get(task['priority'], '🟡')} {title}"
        if len(label) > 44:
            label = label[:43] + "…"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"t:{task['id']}:open")])

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"l:{scope}:{page - 1}"))
    if pages > 1:
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop"))
    if page + 1 < pages:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"l:{scope}:{page + 1}"))
    if nav:
        rows.append(nav)

    def scope_btn(code: str, label: str) -> InlineKeyboardButton:
        mark = "• " if code == scope else ""
        return InlineKeyboardButton(text=f"{mark}{label}", callback_data=f"l:{code}:0")

    rows.append([
        scope_btn("today", "🗓 Bugun"),
        scope_btn("tomorrow", "📆 Ertaga"),
        scope_btn("week", "🗒 Hafta"),
    ])
    rows.append([
        scope_btn("overdue", "⚠️ O'tgan"),
        scope_btn("all", "📋 Barchasi"),
        scope_btn("done", "✅ Bajarilgan"),
    ])
    rows.append([InlineKeyboardButton(text="🔀 Saralash", callback_data="sortmenu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def sort_kb(current: str, scope: str) -> InlineKeyboardMarkup:
    options = [
        ("🧠 Aqlli (tavsiya)", "smart"),
        ("⏰ Vaqt bo'yicha", "time"),
        ("❗️ Daraja bo'yicha", "priority"),
        ("🆕 Yangi qo'shilgan", "created"),
    ]
    rows = [
        [InlineKeyboardButton(
            text=("• " if code == current else "") + label,
            callback_data=f"sort:{code}",
        )]
        for label, code in options
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"l:{scope}:0")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reminder_kb(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Bajardim", callback_data=f"t:{task_id}:done"),
                InlineKeyboardButton(text="👀 Ko'rish", callback_data=f"t:{task_id}:open"),
            ],
            [
                InlineKeyboardButton(text="⏰ 10 daq", callback_data=f"t:{task_id}:snz:10"),
                InlineKeyboardButton(text="⏰ 1 soat", callback_data=f"t:{task_id}:snz:60"),
                InlineKeyboardButton(text="🌅 Ertaga", callback_data=f"t:{task_id}:snz:tom"),
            ],
        ]
    )


# ------------------------------------------------------------------ sozlamalar

def settings_kb(user: aiosqlite.Row) -> InlineKeyboardMarkup:
    auto = "✅" if user["auto_save"] else "❌"
    notify = "✅" if user["notify"] else "❌"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{auto} Avtomatik saqlash", callback_data="st:auto")],
            [InlineKeyboardButton(text=f"{notify} Eslatmalar", callback_data="st:notify")],
            [InlineKeyboardButton(text="🌍 Vaqt mintaqasi", callback_data="st:tz")],
            [InlineKeyboardButton(text="🌅 Kunlik xulosa vaqti", callback_data="st:digest")],
            [InlineKeyboardButton(text="🗑 Barcha vazifalarni o'chirish", callback_data="st:wipe")],
        ]
    )


def tz_kb() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"st:tz:{value}")
        for label, value in TZ_OPTIONS
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="st:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def digest_kb() -> InlineKeyboardMarkup:
    hours = [6, 7, 8, 9, 10, 12, 18, 21]
    buttons = [
        InlineKeyboardButton(text=f"{h:02d}:00", callback_data=f"st:digest:{h}") for h in hours
    ]
    rows = [buttons[i : i + 4] for i in range(0, len(buttons), 4)]
    rows.append([InlineKeyboardButton(text="🚫 O'chirish", callback_data="st:digest:-1")])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="st:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def wipe_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Ha, hammasini o'chir", callback_data="st:wipeyes")],
            [InlineKeyboardButton(text="⬅️ Yo'q, qaytish", callback_data="st:back")],
        ]
    )


def new_task_priority_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"{PRIORITY_EMOJI[p]} {texts.PRIORITY_NAME[p]}", callback_data=f"new:prio:{p}"
        )]
        for p in (1, 2, 3, 4)
    ]
    rows.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="new:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def new_task_time_kb() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"new:time:{code}")
        for label, code in TIME_PRESETS
        if code != "man"
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text="🚫 Vaqtsiz saqlash", callback_data="new:time:clr")])
    rows.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="new:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# --------------------------------------------------------- muammo va yechim

def ideas_list_kb(
    ideas: list[aiosqlite.Row], *, status: str, page: int, pages: int
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for index, idea in enumerate(ideas, start=1 + page * PAGE_SIZE):
        mark = "✅" if idea["status"] == "solved" else "💡"
        label = f"{index}. {mark} {idea['problem'].splitlines()[0]}"
        if len(label) > 44:
            label = label[:43] + "…"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"i:{idea['id']}:open")])

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"il:{status}:{page - 1}"))
    if pages > 1:
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop"))
    if page + 1 < pages:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"il:{status}:{page + 1}"))
    if nav:
        rows.append(nav)

    def status_btn(code: str, label: str) -> InlineKeyboardButton:
        mark = "• " if code == status else ""
        return InlineKeyboardButton(text=f"{mark}{label}", callback_data=f"il:{code}:0")

    rows.append([
        status_btn("all", "📋 Barchasi"),
        status_btn("open", "💡 Yechilmagan"),
        status_btn("solved", "✅ Yechilgan"),
    ])
    rows.append([InlineKeyboardButton(text="➕ Yangi g'oya", callback_data="inew")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def idea_kb(idea: aiosqlite.Row) -> InlineKeyboardMarkup:
    idea_id = idea["id"]
    solved = idea["status"] == "solved"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Yechim yozish" if not idea["solution"] else "✏️ Yechimni o'zgartirish",
                    callback_data=f"i:{idea_id}:sol",
                ),
            ],
            [
                InlineKeyboardButton(text="🤖 AI taklifi", callback_data=f"i:{idea_id}:ai"),
                InlineKeyboardButton(
                    text="↩️ Yechilmagan" if solved else "✅ Yechildi",
                    callback_data=f"i:{idea_id}:toggle",
                ),
            ],
            [
                InlineKeyboardButton(text="🔄 Vazifaga", callback_data=f"i:{idea_id}:totask"),
                InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"i:{idea_id}:del"),
            ],
            [InlineKeyboardButton(text="⬅️ Ro'yxatga", callback_data="il:back:0")],
        ]
    )


def idea_delete_kb(idea_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Ha, o'chirilsin", callback_data=f"i:{idea_id}:delyes"),
                InlineKeyboardButton(text="⬅️ Yo'q", callback_data=f"i:{idea_id}:open"),
            ]
        ]
    )


def solution_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🤖 AI yechim taklif qilsin", callback_data="isol:ai")],
            [InlineKeyboardButton(text="⏭ Hozircha yo'q", callback_data="isol:skip")],
        ]
    )


def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✉️ @firstpremiumuser ga yozish",
                    url="https://t.me/firstpremiumuser",
                )
            ]
        ]
    )
