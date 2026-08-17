"""Bot matnlari va vazifa kartochkalarini chiroyli ko'rinishga keltirish."""

from __future__ import annotations

import json
from html import escape

import aiosqlite

from . import timeutil as tu

PRIORITY_EMOJI = {1: "🔴", 2: "🟠", 3: "🟡", 4: "🟢"}
PRIORITY_NAME = {1: "Shoshilinch", 2: "Yuqori", 3: "O'rta", 4: "Past"}

CATEGORY_EMOJI = {
    "ish": "💼", "shaxsiy": "🙋", "sogliq": "🏥", "moliya": "💰",
    "oila": "👨‍👩‍👧", "talim": "📚", "xarid": "🛒", "boshqa": "📌",
}
CATEGORY_NAME = {
    "ish": "Ish", "shaxsiy": "Shaxsiy", "sogliq": "Sog'liq", "moliya": "Moliya",
    "oila": "Oila", "talim": "Ta'lim", "xarid": "Xarid", "boshqa": "Boshqa",
}

RECURRENCE_NAME = {
    "none": "", "daily": "Har kuni", "weekdays": "Ish kunlari",
    "weekly": "Har hafta", "monthly": "Har oy", "yearly": "Har yili",
}

SCOPE_NAME = {
    "today": "Bugun", "tomorrow": "Ertaga", "week": "Bu hafta",
    "overdue": "Muddati o'tgan", "nodate": "Vaqtsiz", "all": "Barchasi",
    "done": "Bajarilgan",
}

SORT_NAME = {"smart": "Aqlli", "time": "Vaqt", "priority": "Daraja", "created": "Yangi"}

# ------------------------------------------------------------------- tugmalar

BTN_TASKS = "📋 Vazifalarim"
BTN_NEW = "➕ Yangi vazifa"
BTN_TODAY = "🗓 Bugun"
BTN_IDEAS = "💡 Muammo va yechim"
BTN_STATS = "📊 Statistika"
BTN_SETTINGS = "⚙️ Sozlamalar"
BTN_HELP = "❓ Yordam"
BTN_ADMIN = "✉️ Adminga yozish"

MENU_BUTTONS = {
    BTN_TASKS, BTN_NEW, BTN_TODAY, BTN_IDEAS,
    BTN_STATS, BTN_SETTINGS, BTN_HELP, BTN_ADMIN,
}

AUTHOR = "Azizbek Atoyev"
ADMIN_USERNAME = "firstpremiumuser"

# -------------------------------------------------------------------- matnlar

WELCOME_NEW = (
    "👋 <b>Assalomu alaykum!</b>\n"
    "<i>👨‍💻 Azizbek Atoyev tomonidan yaratilgan</i>\n\n"
    "Men — sizning shaxsiy eslatma yordamchingizman. Xayolingizdagi ishlarni "
    "menga <b>yozib</b> yoki <b>ovozli xabar</b> qilib yuboring — sun'iy intellekt "
    "ularni tushunib, muhimlik darajasi va vaqti bo'yicha tartiblab beradi, "
    "kerakli paytda esa eslatib turadi.\n\n"
    "🔐 Boshlash uchun telefon raqamingizni yuboring — hisobingiz shu raqamga "
    "bog'lanadi va ma'lumotlaringiz faqat sizga ko'rinadi.\n\n"
    "Pastdagi «📱 Raqamni yuborish» tugmasini bosing."
)

CONTACT_FOREIGN = (
    "⚠️ Iltimos, <b>o'zingizning</b> raqamingizni yuboring. "
    "Buning uchun «📱 Raqamni yuborish» tugmasidan foydalaning."
)

NEED_REGISTER = (
    "🔐 Botdan foydalanish uchun avval ro'yxatdan o'ting.\n"
    "/start buyrug'ini bosing va telefon raqamingizni yuboring."
)

REGISTERED = (
    "✅ <b>Ro'yxatdan o'tdingiz!</b>\n"
    "📱 Raqam: <code>{phone}</code>\n"
    "🌍 Vaqt mintaqasi: <code>{tz}</code>\n\n"
    "Endi shunchaki yozing yoki ovozli xabar yuboring. Masalan:\n"
    "• <i>«Ertaga soat 3 da shifokorga borishim kerak, muhim»</i>\n"
    "• <i>«Har dushanba ertalab hisobot yuborish»</i>\n"
    "• <i>«2 soatdan keyin Azizga qo'ng'iroq qilish»</i>\n\n"
    "Menyudan foydalanib vazifalaringizni boshqarishingiz mumkin. "
    "To'liq qo'llanma: /help"
)

HELP = (
    "❓ <b>Qo'llanma</b>\n"
    "<i>👨‍💻 Azizbek Atoyev tomonidan yaratilgan</i>\n\n"
    "<b>1. Vazifa qo'shish</b>\n"
    "• Shunchaki matn yozing yoki 🎤 ovozli xabar yuboring — AI o'zi tushunadi.\n"
    "• Yoki «➕ Yangi vazifa» tugmasi orqali qo'lda kiriting.\n\n"
    "<b>2. Muhimlik darajalari</b>\n"
    "🔴 Shoshilinch · 🟠 Yuqori · 🟡 O'rta · 🟢 Past\n"
    "AI darajani o'zi belgilaydi, siz istalgan payt o'zgartirasiz.\n\n"
    "<b>3. Eslatmalar</b>\n"
    "Vaqti kelganda bot xabar yuboradi. Darajaga qarab oldindan ham "
    "ogohlantiradi (masalan, 1 soat oldin). Eslatmada «⏰ Keyinroq» tugmasi bor.\n\n"
    "<b>4. Saralash</b>\n"
    "Ro'yxatda: 🧠 Aqlli · ⏰ Vaqt · ❗️ Daraja · 🆕 Yangi tartiblari va "
    "Bugun / Ertaga / Hafta / Muddati o'tgan filtrlari bor.\n\n"
    "<b>5. 💡 Muammo va yechim</b>\n"
    "Yangi fikr yoki muammo paydo bo'lsa — «💡 Muammo va yechim» bo'limiga "
    "yozib qo'ying. Yechimini keyin qo'shasiz yoki 🤖 AI dan taklif so'raysiz. "
    "G'oyani bir bosishda vazifaga ham aylantirsa bo'ladi.\n\n"
    "<b>Buyruqlar</b>\n"
    "/start — boshlash · /tasks — vazifalar · /new — yangi vazifa\n"
    "/ideas — muammo va yechimlar · /today — bugungi ishlar\n"
    "/stats — statistika · /settings — sozlamalar · /admin — adminga yozish\n"
    "/help — shu qo'llanma\n\n"
    "<i>Savol yoki taklifingiz bo'lsa: @firstpremiumuser</i>"
)

ADMIN_TEXT = (
    "✉️ <b>Adminga yozish</b>\n\n"
    "Savol, taklif yoki muammo yuzasidan to'g'ridan-to'g'ri murojaat qiling:\n"
    "👤 @firstpremiumuser\n\n"
    "<i>👨‍💻 Bot muallifi: Azizbek Atoyev</i>"
)

ANALYZING = "🧠 <i>Tahlil qilinmoqda...</i>"
LISTENING = "🎧 <i>Ovozli xabar tinglanmoqda...</i>"

NO_TASKS_FOUND = (
    "🤔 Xabaringizda aniq bajariladigan ish topilmadi.\n"
    "Agar shunday bo'lsa ham saqlashni xohlasangiz — pastdagi tugmani bosing."
)

AI_FAILED_VOICE = (
    "😔 Ovozli xabarni tahlil qilib bo'lmadi.\n"
    "Iltimos, birozdan so'ng qayta urinib ko'ring yoki matn ko'rinishida yozing."
)

VOICE_TOO_BIG = "⚠️ Ovozli xabar juda katta (18 MB dan ortiq). Qisqaroq yuboring."

ASK_TITLE = "✍️ Vazifa nomini yozing:\n\n<i>Bekor qilish: /cancel</i>"
ASK_TIME = (
    "⏰ Vaqtni yozing yoki tugmalardan tanlang.\n\n"
    "Masalan: <i>ertaga soat 15:00</i>, <i>2 soatdan keyin</i>, "
    "<i>25.12 09:00</i>, <i>juma kechqurun</i>\n\n"
    "<i>Bekor qilish: /cancel</i>"
)
TIME_NOT_UNDERSTOOD = (
    "🤷 Vaqtni tushunmadim. Yana urinib ko'ring: <i>ertaga soat 9 da</i>, "
    "<i>30 daqiqadan keyin</i>, <i>25.12 18:30</i>"
)

EMPTY_LIST = "📭 Bu bo'limda vazifa yo'q."
TASK_NOT_FOUND = "🚫 Vazifa topilmadi (o'chirilgan bo'lishi mumkin)."


IDEAS_INTRO = (
    "💡 <b>Muammo va yechim</b>\n\n"
    "Bu yerga xayolingizga kelgan g'oyalarni, hal qilinishi kerak bo'lgan "
    "muammolarni yozib boring. Yechimini keyinroq qo'shasiz — yoki 🤖 AI dan "
    "taklif so'raysiz.\n\n"
    "Yozib ham, ovozli xabar qilib ham yuborishingiz mumkin."
)

ASK_PROBLEM = (
    "💡 <b>Muammo yoki g'oyangizni yozing</b>\n\n"
    "Matn yoki 🎤 ovozli xabar yuboring.\n"
    "<i>Bekor qilish: /cancel</i>"
)

ASK_SOLUTION = (
    "✅ <b>Yechimni yozing</b>\n\n"
    "Agar hozircha yechim yo'q bo'lsa — «⏭ Hozircha yo'q» tugmasini bosing, "
    "yoki 🤖 AI dan taklif so'rang.\n"
    "<i>Bekor qilish: /cancel</i>"
)

IDEA_NOT_FOUND = "🚫 G'oya topilmadi (o'chirilgan bo'lishi mumkin)."
EMPTY_IDEAS = "📭 Hozircha g'oya yo'q. «➕ Yangi g'oya» tugmasi bilan qo'shing."
AI_THINKING = "🤖 <i>AI yechim o'ylayapti...</i>"
AI_FAILED = "😔 AI hozir javob bera olmadi. Birozdan so'ng urinib ko'ring."


def idea_card(idea: aiosqlite.Row, tz: str) -> str:
    """Bitta g'oyaning to'liq kartochkasi."""
    solved = idea["status"] == "solved"
    created = tu.parse(idea["created_at"])

    lines = [
        f"{'✅' if solved else '💡'} <b>Muammo / G'oya</b>",
        escape(idea["problem"]),
        "",
    ]

    if idea["solution"]:
        lines.append("🔑 <b>Yechim</b>")
        lines.append(escape(idea["solution"]))
    else:
        lines.append("🔑 <i>Yechim hali yozilmagan</i>")

    lines.append("")
    lines.append(f"🕐 <i>{tu.fmt_datetime(created, tz)}</i>")
    return "\n".join(lines)


def idea_line(index: int, idea: aiosqlite.Row) -> str:
    """Ro'yxatdagi bitta qator."""
    mark = "✅" if idea["status"] == "solved" else "💡"
    problem = idea["problem"].replace("\n", " ")
    if len(problem) > 70:
        problem = problem[:69] + "…"
    text = f"{index}. {mark} <b>{escape(problem)}</b>"
    if idea["solution"]:
        solution = idea["solution"].replace("\n", " ")
        if len(solution) > 60:
            solution = solution[:59] + "…"
        text += f"\n     🔑 <i>{escape(solution)}</i>"
    return text


def ideas_header(status: str, total: int, page: int, pages: int) -> str:
    name = {"all": "Barchasi", "open": "Yechilmagan", "solved": "Yechilgan"}.get(status, "Barchasi")
    header = f"💡 <b>Muammo va yechim</b> · {name} · {total} ta"
    if pages > 1:
        header += f"\n<i>{page + 1}/{pages}-sahifa</i>"
    return header


def priority_label(priority: int) -> str:
    return f"{PRIORITY_EMOJI.get(priority, '🟡')} {PRIORITY_NAME.get(priority, 'O’rta')}"


def offsets_label(raw: str | None) -> str:
    try:
        offsets = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return ""
    if not offsets:
        return ""
    parts = []
    for minutes in sorted(offsets, reverse=True):
        if minutes >= 1440:
            parts.append(f"{minutes // 1440} kun")
        elif minutes >= 60:
            parts.append(f"{minutes // 60} soat")
        else:
            parts.append(f"{minutes} daq")
    return " · ".join(parts) + " oldin"


def task_card(task: aiosqlite.Row, tz: str, *, draft: bool = False) -> str:
    """Bitta vazifaning to'liq kartochkasi."""
    due = tu.parse(task["due_at"])
    has_time = bool(task["has_time"])
    overdue = due is not None and due < tu.utc_now() and task["status"] == "pending"

    lines = [f"{PRIORITY_EMOJI.get(task['priority'], '🟡')} <b>{escape(task['title'])}</b>"]

    if task["notes"]:
        lines.append(f"<i>{escape(task['notes'])}</i>")

    lines.append("")

    if due is not None:
        when = tu.fmt_datetime(due, tz, has_time=has_time)
        relative = tu.fmt_relative(due)
        icon = "⚠️" if overdue else "📅"
        lines.append(f"{icon} <b>{when}</b>  <i>({relative})</i>")
    else:
        lines.append("📅 Vaqt belgilanmagan")

    lines.append(f"❗️ Daraja: {priority_label(task['priority'])}")

    recurrence = RECURRENCE_NAME.get(task["recurrence"] or "none", "")
    if recurrence:
        lines.append(f"🔁 {recurrence}")

    if task["category"]:
        emoji = CATEGORY_EMOJI.get(task["category"], "📌")
        lines.append(f"{emoji} {CATEGORY_NAME.get(task['category'], task['category'])}")

    if due is not None and task["status"] == "pending":
        hint = offsets_label(task["remind_offsets"])
        if hint:
            lines.append(f"🔔 Eslatma: {hint}")

    if task["status"] == "done":
        done_at = tu.parse(task["completed_at"])
        lines.append(f"✅ Bajarilgan: {tu.fmt_datetime(done_at, tz)}")

    if draft:
        lines.append("")
        lines.append("<i>Saqlashni tasdiqlang yoki tahrirlang:</i>")

    return "\n".join(lines)


def task_line(index: int, task: aiosqlite.Row, tz: str) -> str:
    """Ro'yxatdagi bitta qator."""
    due = tu.parse(task["due_at"])
    overdue = due is not None and due < tu.utc_now()
    emoji = PRIORITY_EMOJI.get(task["priority"], "🟡")
    when = tu.fmt_datetime(due, tz, has_time=bool(task["has_time"])) if due else "—"
    mark = "⚠️ " if overdue else ""
    return f"{index}. {emoji} {mark}<b>{escape(task['title'])}</b>\n     <i>{when}</i>"


def list_header(scope: str, sort_mode: str, total: int, page: int, pages: int) -> str:
    title = SCOPE_NAME.get(scope, "Barchasi")
    header = f"📋 <b>{title}</b> · {total} ta · saralash: {SORT_NAME.get(sort_mode, 'Aqlli')}"
    if pages > 1:
        header += f"\n<i>{page + 1}/{pages}-sahifa</i>"
    return header


def stats_text(data: dict[str, int], tz: str) -> str:
    total = data.get("total", 0)
    done = data.get("done", 0)
    rate = round(done / total * 100) if total else 0
    bar_filled = round(rate / 10)
    bar = "█" * bar_filled + "░" * (10 - bar_filled)

    return (
        "📊 <b>Statistika</b>\n\n"
        f"📌 Jami vazifalar: <b>{total}</b>\n"
        f"⏳ Bajarilmagan: <b>{data.get('pending', 0)}</b>\n"
        f"✅ Bajarilgan: <b>{done}</b>\n"
        f"⚠️ Muddati o'tgan: <b>{data.get('overdue', 0)}</b>\n\n"
        f"🗓 Bugun bajarilgan: <b>{data.get('done_today', 0)}</b>\n"
        f"📆 Oxirgi 7 kunda: <b>{data.get('done_week', 0)}</b>\n\n"
        "<b>Darajalar bo'yicha (bajarilmagan):</b>\n"
        f"🔴 Shoshilinch: {data.get('p1', 0)}\n"
        f"🟠 Yuqori: {data.get('p2', 0)}\n"
        f"🟡 O'rta: {data.get('p3', 0)}\n"
        f"🟢 Past: {data.get('p4', 0)}\n\n"
        f"<b>Bajarilish darajasi:</b>\n{bar} {rate}%"
    )


def settings_text(user: aiosqlite.Row) -> str:
    return (
        "⚙️ <b>Sozlamalar</b>\n\n"
        f"📱 Raqam: <code>{escape(user['phone'] or '—')}</code>\n"
        f"🌍 Vaqt mintaqasi: <code>{user['tz']}</code>\n"
        f"🕐 Mahalliy vaqt: <b>{tu.local_now(user['tz']):%H:%M, %d.%m.%Y}</b>\n\n"
        f"🤖 Avtomatik saqlash: <b>{'yoqilgan' if user['auto_save'] else 'o‘chirilgan'}</b>\n"
        f"   <i>{'AI tahlil qilib, darrov saqlaydi' if user['auto_save'] else 'Saqlashdan oldin tasdiq so‘raladi'}</i>\n"
        f"🔔 Eslatmalar: <b>{'yoqilgan' if user['notify'] else 'o‘chirilgan'}</b>\n"
        f"🌅 Kunlik xulosa: <b>{user['digest_hour']:02d}:00</b>\n"
    )


def reminder_text(task: aiosqlite.Row, tz: str, kind: str) -> str:
    due = tu.parse(task["due_at"])
    head = {
        "pre": "🔔 <b>Tez orada:</b>",
        "main": "⏰ <b>Vaqti keldi!</b>",
        "snooze": "🔔 <b>Eslatma</b>",
        "overdue": "⚠️ <b>Muddati o'tdi!</b>",
    }.get(kind, "🔔 <b>Eslatma</b>")

    lines = [head, "", f"{PRIORITY_EMOJI.get(task['priority'], '🟡')} <b>{escape(task['title'])}</b>"]
    if task["notes"]:
        lines.append(f"<i>{escape(task['notes'])}</i>")
    if due is not None:
        lines.append("")
        lines.append(f"📅 {tu.fmt_datetime(due, tz, has_time=bool(task['has_time']))}"
                     f"  <i>({tu.fmt_relative(due)})</i>")
    return "\n".join(lines)


def digest_text(tasks: list[aiosqlite.Row], overdue: list[aiosqlite.Row], tz: str) -> str:
    now = tu.local_now(tz)
    weekday = tu.WEEKDAYS_UZ[now.weekday()].capitalize()
    lines = ["🌅 <b>Xayrli tong!</b>", f"<i>{now.day}-{tu.MONTHS_UZ[now.month - 1]}, {weekday}</i>", ""]

    if overdue:
        lines.append(f"⚠️ <b>Muddati o'tgan ({len(overdue)} ta):</b>")
        for task in overdue[:5]:
            lines.append(f"   {PRIORITY_EMOJI.get(task['priority'], '🟡')} {escape(task['title'])}")
        lines.append("")

    if tasks:
        lines.append(f"📋 <b>Bugungi rejalar ({len(tasks)} ta):</b>")
        for task in tasks[:10]:
            due = tu.parse(task["due_at"])
            time_part = tu.to_local(due, tz).strftime("%H:%M") if due and task["has_time"] else "—"
            lines.append(
                f"   {PRIORITY_EMOJI.get(task['priority'], '🟡')} <b>{time_part}</b> "
                f"{escape(task['title'])}"
            )
    elif not overdue:
        lines.append("😌 Bugunga rejalashtirilgan ish yo'q. Yaxshi kun tilayman!")

    lines.append("")
    lines.append("<i>Omad tilayman! 💪</i>")
    return "\n".join(lines)
