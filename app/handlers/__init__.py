"""Handler routerlari.

Tartib muhim: umumiy (matn/ovoz) handler eng oxirida turadi, aks holda u
menyu tugmalari va sehrgar bosqichlarini ham "yutib" yuboradi.
"""

from __future__ import annotations

from aiogram import Router

from . import capture, ideas, newtask, settings, start, tasks

ROUTERS: tuple[Router, ...] = (
    start.router,
    settings.router,
    newtask.router,
    ideas.router,
    tasks.router,
    capture.router,
)

__all__ = ["ROUTERS"]
