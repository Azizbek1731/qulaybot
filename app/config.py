"""Konfiguratsiya: .env faylidan sozlamalarni o'qish."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .gemini import DEFAULT_TEXT_MODELS, DEFAULT_VOICE_MODELS

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Config:
    bot_token: str
    gemini_api_key: str
    gemini_text_models: tuple[str, ...]
    gemini_voice_models: tuple[str, ...]
    db_path: Path
    default_tz: str
    tick_seconds: int
    log_level: str


def _models(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return tuple(m.strip() for m in raw.split(",") if m.strip())


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"{name} topilmadi. .env faylini yarating (.env.example dan nusxa oling) "
            f"va {name} qiymatini kiriting."
        )
    return value


def load_config() -> Config:
    db_path = Path(os.getenv("DB_PATH", "data/bot.db"))
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return Config(
        bot_token=_require("BOT_TOKEN"),
        gemini_api_key=_require("GEMINI_API_KEY"),
        gemini_text_models=_models("GEMINI_TEXT_MODELS", DEFAULT_TEXT_MODELS),
        gemini_voice_models=_models("GEMINI_VOICE_MODELS", DEFAULT_VOICE_MODELS),
        db_path=db_path,
        default_tz=os.getenv("DEFAULT_TZ", "Asia/Tashkent").strip(),
        tick_seconds=int(os.getenv("TICK_SECONDS", "20")),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
    )
