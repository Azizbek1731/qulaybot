"""Google Gemini API klienti.

Matn yoki ovozli xabarni tahlil qilib, tuzilgan (structured) JSON qaytaradi:
vazifa nomi, muhimlik darajasi, muddati, takrorlanishi va h.k.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

import aiohttp

from .net import ssl_context

log = logging.getLogger(__name__)

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"

SYSTEM_PROMPT = """\
Sen — o'zbek tilida ishlaydigan shaxsiy yordamchi (task manager) yadrosisan.
Foydalanuvchi matn yoki ovozli xabar orqali "esimda tursin" degan narsalarini aytadi.
Sening vazifang — undagi HAR BIR bajarilishi kerak bo'lgan ishni ajratib olish va
ularni tuzilgan ma'lumotga aylantirish.

QOIDALAR:
1. Bitta xabarda bir nechta vazifa bo'lishi mumkin — har birini alohida element qil.
   Ammo bitta ishni sun'iy ravishda bo'lakma.
2. `title` — qisqa, aniq, buyruq shaklidagi ish nomi o'zbek tilida (maks. 80 belgi).
   Ortiqcha so'zlarni ("esimda tursin", "kerak edi") olib tashla.
3. `notes` — qo'shimcha tafsilotlar bo'lsa (manzil, ism, telefon, izoh). Bo'lmasa "".
4. `priority` — muhimlik darajasi:
   1 = shoshilinch (bugun/hozir bo'lishi shart, jarima, muddat tugayapti, sog'liq, muhim uchrashuv)
   2 = yuqori (aniq muddati bor va kechiktirib bo'lmaydi)
   3 = o'rta (oddiy reja, standart holat)
   4 = past (bo'sh vaqtda, "qachondir", g'oya, istak)
   Foydalanuvchi "muhim", "shoshilinch", "albatta" desa — darajani oshir.
5. `due_at` — "YYYY-MM-DD HH:MM" formatida, FOYDALANUVCHI MAHALLIY VAQTIDA.
   Vaqt umuman aniqlanmasa "" qaytar. Nisbiy iboralarni hisobla:
   "ertaga" = +1 kun, "indinga" = +2 kun, "kelasi hafta" = +7 kun,
   "2 soatdan keyin" = hozir + 2 soat, hafta kunlari = eng yaqin kelasi shu kun.
   Sana aytilib, soat aytilmasa — soatni 09:00 qilib qo'y va `has_time` = false.
   Kun qismi aytilsa: ertalab=08:00, tushda=13:00, kechqurun=19:00, kechasi=21:00.
6. `has_time` — foydalanuvchi aniq soatni aytgan bo'lsa true, aks holda false.
7. `recurrence` — takrorlanish: none | daily | weekdays | weekly | monthly | yearly.
   "har kuni", "har dushanba", "har oy" kabi iboralarda to'g'ri qiymatni tanla.
8. `category` — bittasi: ish, shaxsiy, sogliq, moliya, oila, talim, xarid, boshqa.
9. `remind_before_minutes` — vazifadan necha daqiqa oldin eslatish kerakligi.
   Odatda: shoshilinch [60, 10], yuqori [60], o'rta [30], past [0].
   Uchrashuv/samolyot/poyezd kabi hodisalarda kattaroq qiymat ber (masalan [1440, 120]).
10. Agar xabarda hech qanday bajariladigan ish bo'lmasa (shunchaki salomlashish,
    savol) — `tasks` bo'sh massiv bo'lsin.
11. Ovozli xabar bo'lsa, `transcript` maydoniga to'liq matnni yoz.
12. Foydalanuvchi qaysi tilda gapirsa ham (o'zbek, rus, ingliz), natijani
    O'ZBEK tilida yoz.
"""

TASK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "transcript": {
            "type": "string",
            "description": "Ovozli xabarning to'liq matni, matnli xabarda bo'sh",
        },
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "notes": {"type": "string"},
                    "priority": {"type": "integer"},
                    "due_at": {"type": "string"},
                    "has_time": {"type": "boolean"},
                    "recurrence": {
                        "type": "string",
                        "enum": ["none", "daily", "weekdays", "weekly", "monthly", "yearly"],
                    },
                    "category": {"type": "string"},
                    "remind_before_minutes": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["title", "priority", "due_at", "has_time", "recurrence"],
                "propertyOrdering": [
                    "title", "notes", "priority", "due_at", "has_time",
                    "recurrence", "category", "remind_before_minutes",
                ],
            },
        },
    },
    "required": ["tasks"],
    "propertyOrdering": ["transcript", "tasks"],
}


class GeminiError(RuntimeError):
    """Gemini bilan bog'liq har qanday xatolik."""


# Matn uchun: tez va aniq. Ovoz uchun: o'zbek nutqini yaxshi tushunadigan modellar.
DEFAULT_TEXT_MODELS = ("gemini-3.1-flash-lite", "gemini-3.7-flash", "gemini-flash-latest")
DEFAULT_VOICE_MODELS = ("gemini-3.7-flash", "gemini-flash-latest", "gemini-3-flash-preview")


def thinking_config(model: str) -> dict[str, Any]:
    """Gemini 3.x `thinkingLevel`, eskiroq modellar `thinkingBudget` ishlatadi."""
    if model.startswith("gemini-3"):
        return {"thinkingLevel": "low"}
    return {"thinkingBudget": 0}


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        *,
        text_models: tuple[str, ...] | list[str] = DEFAULT_TEXT_MODELS,
        voice_models: tuple[str, ...] | list[str] = DEFAULT_VOICE_MODELS,
        timeout: int = 90,
        max_retries: int = 2,
    ) -> None:
        self._api_key = api_key
        # Ro'yxatdagi model band bo'lsa (503) yoki xato bersa — keyingisiga o'tamiz
        self._text_models = [m for m in text_models if m] or list(DEFAULT_TEXT_MODELS)
        self._voice_models = [m for m in voice_models if m] or list(DEFAULT_VOICE_MODELS)
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._max_retries = max_retries
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(ssl=ssl_context(), limit=20)
            self._session = aiohttp.ClientSession(timeout=self._timeout, connector=connector)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------ public

    async def extract_tasks(
        self,
        *,
        user_prompt: str,
        audio: bytes | None = None,
        audio_mime: str = "audio/ogg",
    ) -> dict[str, Any]:
        """Xabarni tahlil qilib, {"transcript": ..., "tasks": [...]} qaytaradi."""
        parts: list[dict[str, Any]] = [{"text": user_prompt}]
        if audio is not None:
            parts.append(
                {
                    "inlineData": {
                        "mimeType": audio_mime,
                        "data": base64.b64encode(audio).decode("ascii"),
                    }
                }
            )

        def build_payload(model: str) -> dict[str, Any]:
            return {
                "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": {
                    "temperature": 0.2,
                    "topP": 0.9,
                    "maxOutputTokens": 8192,
                    "responseMimeType": "application/json",
                    "responseSchema": TASK_SCHEMA,
                    "thinkingConfig": thinking_config(model),
                },
            }

        models = self._voice_models if audio is not None else self._text_models
        raw = await self._request(build_payload, models)
        return self._parse_response(raw)

    async def generate_text(
        self,
        prompt: str,
        *,
        audio: bytes | None = None,
        audio_mime: str = "audio/ogg",
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> str:
        """Oddiy (sxemasiz) matnli javob — transkripsiya va maslahat uchun."""
        parts: list[dict[str, Any]] = [{"text": prompt}]
        if audio is not None:
            parts.append(
                {
                    "inlineData": {
                        "mimeType": audio_mime,
                        "data": base64.b64encode(audio).decode("ascii"),
                    }
                }
            )

        def build_payload(model: str) -> dict[str, Any]:
            payload: dict[str, Any] = {
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": {
                    "temperature": 0.4,
                    "maxOutputTokens": max_tokens,
                    "thinkingConfig": thinking_config(model),
                },
            }
            if system:
                payload["systemInstruction"] = {"parts": [{"text": system}]}
            return payload

        models = self._voice_models if audio is not None else self._text_models
        raw = await self._request(build_payload, models)

        candidates = raw.get("candidates") or []
        if not candidates:
            raise GeminiError("Gemini bo'sh javob qaytardi")

        text = "".join(
            part.get("text", "")
            for part in candidates[0].get("content", {}).get("parts", [])
        ).strip()

        if not text:
            raise GeminiError("Gemini matn qaytarmadi")
        return text

    # ----------------------------------------------------------------- private

    async def _request(self, build_payload, models: list[str]) -> dict[str, Any]:
        headers = {"x-goog-api-key": self._api_key, "Content-Type": "application/json"}
        session = await self._get_session()
        last_error: Exception | None = None

        for model in models:
            url = f"{API_ROOT}/{model}:generateContent"
            payload = build_payload(model)

            for attempt in range(1, self._max_retries + 1):
                try:
                    async with session.post(url, json=payload, headers=headers) as resp:
                        body = await resp.text()
                        if resp.status == 200:
                            if model != models[0]:
                                log.info("Zaxira model ishlatildi: %s", model)
                            return json.loads(body)

                        message = f"Gemini HTTP {resp.status} ({model}): {body[:300]}"
                        last_error = GeminiError(message)
                        log.warning(message)

                        # 503 = model band; 4xx = model mos emas.
                        # Ikkalasida ham shu model bilan qayta urinmay, keyingisiga o'tamiz.
                        if resp.status in (400, 401, 403, 404, 503):
                            break
                        if resp.status not in (408, 429, 500, 502, 504):
                            raise GeminiError(message)
                except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as exc:
                    last_error = exc
                    log.warning("Gemini so'rovi uzildi (%s): %s", model, exc)

                if attempt < self._max_retries:
                    await asyncio.sleep(1.0 * attempt)

        raise GeminiError(f"Gemini javob bermadi: {last_error}")

    @staticmethod
    def _parse_response(raw: dict[str, Any]) -> dict[str, Any]:
        feedback = raw.get("promptFeedback", {})
        if feedback.get("blockReason"):
            raise GeminiError(f"So'rov bloklandi: {feedback['blockReason']}")

        candidates = raw.get("candidates") or []
        if not candidates:
            raise GeminiError("Gemini bo'sh javob qaytardi")

        candidate = candidates[0]
        finish = candidate.get("finishReason")
        if finish in ("SAFETY", "RECITATION", "PROHIBITED_CONTENT"):
            raise GeminiError(f"Javob to'xtatildi: {finish}")

        text = "".join(
            part.get("text", "")
            for part in candidate.get("content", {}).get("parts", [])
        ).strip()

        if not text:
            raise GeminiError(f"Gemini matn qaytarmadi (finishReason={finish})")

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise GeminiError(f"JSON o'qib bo'lmadi: {exc}; javob: {text[:300]}") from exc

        if not isinstance(data, dict):
            raise GeminiError("Kutilmagan JSON tuzilmasi")

        data.setdefault("tasks", [])
        return data
