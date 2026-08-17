"""FSM holatlari."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class TaskEdit(StatesGroup):
    """Mavjud vazifani tahrirlash."""

    waiting_title = State()
    waiting_time = State()


class NewTask(StatesGroup):
    """Qo'lda yangi vazifa yaratish sehrgari."""

    waiting_title = State()
    waiting_priority = State()
    waiting_time = State()


class Idea(StatesGroup):
    """💡 Muammo va yechim bo'limi."""

    waiting_problem = State()
    waiting_solution = State()
    waiting_edit_solution = State()
