"""Tarmoq yordamchilari.

Ba'zi tizimlarda (masalan, macOS'ga rasmiy python.org o'rnatmasi) ildiz
sertifikatlari yo'q bo'ladi va HTTPS so'rovlari ishlamaydi. Shuning uchun
certifi sertifikatlari bilan SSL konteksti yasaymiz.
"""

from __future__ import annotations

import ssl
from functools import lru_cache


@lru_cache(maxsize=1)
def ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # pragma: no cover - certifi bo'lmasa tizim sertifikatlari
        return ssl.create_default_context()
