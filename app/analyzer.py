"""AI tahlil qatlami.

Gemini javobini tekshiradi, tozalaydi va bazaga yozishga tayyor ko'rinishga
keltiradi. Gemini ishlamasa — `heuristics` moduli orqali zaxira tahlil qiladi.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from . import heuristics, timeutil as tu
from .db import PRIORITY_MEDIUM
from .gemini import GeminiClient, GeminiError

log = logging.getLogger(__name__)

VALID_RECURRENCE = {"none", "daily", "weekdays", "weekly", "monthly", "yearly"}

CATEGORIES = {"ish", "shaxsiy", "sogliq", "moliya", "oila", "talim", "xarid", "boshqa"}

# Muhimlik darajasiga qarab standart eslatma oldindan-ogohlantirishlari (daqiqa)
DEFAULT_OFFSETS = {1: [60, 10], 2: [60], 3: [30], 4: [0]}

MAX_AUDIO_BYTES = 18 * 1024 * 1024


@dataclass
class ParsedTask:
    title: str
    priority: int = PRIORITY_MEDIUM
    due_at: datetime | None = None       # UTC
    has_time: bool = False
    notes: str | None = None
    recurrence: str = "none"
    category: str | None = None
    remind_offsets: list[int] = field(default_factory=list)


@dataclass
class Analysis:
    tasks: list[ParsedTask]
    transcript: str | None = None
    used_ai: bool = True
    error: str | None = None


class Analyzer:
    def __init__(self, gemini: GeminiClient) -> None:
        self._gemini = gemini

    async def analyze(
        self,
        *,
        tz: str,
        text: str | None = None,
        audio: bytes | None = None,
        audio_mime: str = "audio/ogg",
    ) -> Analysis:
        prompt = self._build_prompt(tz, text=text, is_voice=audio is not None)

        try:
            raw = await self._gemini.extract_tasks(
                user_prompt=prompt, audio=audio, audio_mime=audio_mime
            )
        except GeminiError as exc:
            log.warning("AI tahlil ishlamadi, zaxira rejim: %s", exc)
            if text:
                data = heuristics.fallback_parse(text, tz)
                return Analysis(
                    tasks=[self._from_fallback(data)], used_ai=False, error=str(exc)
                )
            return Analysis(tasks=[], used_ai=False, error=str(exc))

        transcript = (raw.get("transcript") or "").strip() or None
        source_text = text or transcript or ""

        tasks: list[ParsedTask] = []
        for item in raw.get("tasks") or []:
            parsed = self._normalize(item, tz, source_text)
            if parsed is not None:
                tasks.append(parsed)

        return Analysis(tasks=tasks, transcript=transcript, used_ai=True)

    async def transcribe(self, audio: bytes, *, audio_mime: str = "audio/ogg") -> str | None:
        """Ovozli xabarni so'zma-so'z matnga o'giradi (g'oyalar bo'limi uchun)."""
        try:
            return await self._gemini.generate_text(
                "Quyidagi ovozli xabarni so'zma-so'z matnga o'gir. "
                "Faqat matnning o'zini qaytar, hech qanday izoh qo'shma.",
                audio=audio,
                audio_mime=audio_mime,
                max_tokens=2048,
            )
        except GeminiError as exc:
            log.warning("Transkripsiya ishlamadi: %s", exc)
            return None

    async def suggest_solution(self, problem: str) -> str | None:
        """Muammoga qisqa, amaliy yechim taklif qiladi."""
        try:
            return await self._gemini.generate_text(
                f"Muammo yoki g'oya:\n\"\"\"\n{problem}\n\"\"\"",
                system=(
                    "Sen — amaliy maslahatchisan. Foydalanuvchi muammosi yoki g'oyasiga "
                    "3-5 ta ANIQ, bajarish mumkin bo'lgan qadam taklif qil. "
                    "O'zbek tilida, har bir qadam bitta qatorda, «• » belgisi bilan boshlansin. "
                    "Umumiy gaplar («harakat qiling», «o'ylab ko'ring») emas, aniq amallar yoz. "
                    "Jami 700 belgidan oshmasin. Sarlavha yozma, darrov qadamlardan boshla."
                ),
                max_tokens=1024,
            )
        except GeminiError as exc:
            log.warning("AI yechim taklifi ishlamadi: %s", exc)
            return None

    # ----------------------------------------------------------------- private

    @staticmethod
    def _build_prompt(tz: str, *, text: str | None, is_voice: bool) -> str:
        now = tu.local_now(tz)
        weekday = tu.WEEKDAYS_UZ[now.weekday()]
        header = (
            f"Hozirgi mahalliy vaqt: {now:%Y-%m-%d %H:%M} ({weekday}).\n"
            f"Foydalanuvchi vaqt mintaqasi: {tz}.\n"
        )
        if is_voice:
            return header + "Quyidagi ovozli xabarni tinglab tahlil qil."
        return header + f"Foydalanuvchi xabari:\n\"\"\"\n{text}\n\"\"\""

    def _normalize(self, item: dict[str, Any], tz: str, source_text: str) -> ParsedTask | None:
        title = str(item.get("title") or "").strip()
        if not title:
            return None
        title = heuristics.clean_title(title, limit=200)

        try:
            priority = int(item.get("priority", PRIORITY_MEDIUM))
        except (TypeError, ValueError):
            priority = PRIORITY_MEDIUM
        priority = min(4, max(1, priority))

        has_time = bool(item.get("has_time"))
        due_at = self._parse_due(item.get("due_at"), tz)

        if due_at is None and source_text:
            # AI vaqtni topa olmadi — oddiy tahlil bilan yana bir bor urinib ko'ramiz
            fallback_due, fallback_has_time = heuristics.parse_datetime(source_text, tz)
            if fallback_due is not None:
                due_at, has_time = fallback_due, fallback_has_time

        recurrence = str(item.get("recurrence") or "none").lower()
        if recurrence not in VALID_RECURRENCE:
            recurrence = "none"

        category = str(item.get("category") or "").strip().lower() or None
        if category not in CATEGORIES:
            category = None

        notes = str(item.get("notes") or "").strip() or None
        if notes and notes.lower() == title.lower():
            notes = None

        return ParsedTask(
            title=title,
            priority=priority,
            due_at=due_at,
            has_time=has_time,
            notes=notes[:600] if notes else None,
            recurrence=recurrence,
            category=category,
            remind_offsets=self._normalize_offsets(item.get("remind_before_minutes"), priority),
        )

    @staticmethod
    def _parse_due(value: Any, tz: str) -> datetime | None:
        if not value or not isinstance(value, str):
            return None
        text = value.strip().replace("T", " ")
        candidates = (
            (text, "%Y-%m-%d %H:%M:%S"),
            (text, "%Y-%m-%d %H:%M"),
            (text[:16], "%Y-%m-%d %H:%M"),
            (text[:10], "%Y-%m-%d"),
        )
        for candidate, fmt in candidates:
            try:
                local = datetime.strptime(candidate, fmt)
            except ValueError:
                continue
            if fmt == "%Y-%m-%d":
                local = local.replace(hour=9)  # sanasi aytilgan, soati aytilmagan
            return tu.to_utc(local, tz)
        return None

    @staticmethod
    def _normalize_offsets(value: Any, priority: int) -> list[int]:
        offsets: list[int] = []
        if isinstance(value, list):
            for item in value:
                try:
                    minutes = int(item)
                except (TypeError, ValueError):
                    continue
                if 0 < minutes <= 20_160:  # 14 kungacha
                    offsets.append(minutes)
        if not offsets:
            offsets = [m for m in DEFAULT_OFFSETS.get(priority, [30]) if m > 0]
        return sorted(set(offsets), reverse=True)[:4]

    @staticmethod
    def _from_fallback(data: dict[str, Any]) -> ParsedTask:
        return parsed_from_fallback(data)


def parsed_from_fallback(data: dict[str, Any]) -> ParsedTask:
    """`heuristics.fallback_parse` natijasini ParsedTask ga aylantiradi."""
    priority = int(data.get("priority", PRIORITY_MEDIUM))
    return ParsedTask(
        title=data["title"],
        priority=priority,
        due_at=data.get("due_at"),
        has_time=bool(data.get("has_time")),
        notes=data.get("notes"),
        recurrence=data.get("recurrence", "none"),
        category=data.get("category"),
        remind_offsets=[m for m in DEFAULT_OFFSETS.get(priority, [30]) if m > 0],
    )
