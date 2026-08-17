"""SQLite ma'lumotlar bazasi qatlami.

Har bir so'rov `user_id` bo'yicha filtrlanadi — foydalanuvchilar ma'lumotlari
bir-biridan to'liq ajratilgan.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence

import aiosqlite

from . import timeutil as tu

log = logging.getLogger(__name__)

PRIORITY_URGENT = 1
PRIORITY_HIGH = 2
PRIORITY_MEDIUM = 3
PRIORITY_LOW = 4

STATUS_DRAFT = "draft"
STATUS_PENDING = "pending"
STATUS_DONE = "done"
STATUS_CANCELLED = "cancelled"

IDEA_OPEN = "open"
IDEA_SOLVED = "solved"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY,
    phone           TEXT,
    full_name       TEXT,
    username        TEXT,
    tz              TEXT    NOT NULL DEFAULT 'Asia/Tashkent',
    auto_save       INTEGER NOT NULL DEFAULT 1,
    notify          INTEGER NOT NULL DEFAULT 1,
    digest_hour     INTEGER NOT NULL DEFAULT 8,
    sort_mode       TEXT    NOT NULL DEFAULT 'smart',
    last_digest     TEXT,
    registered_at   TEXT,
    created_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    title           TEXT    NOT NULL,
    notes           TEXT,
    priority        INTEGER NOT NULL DEFAULT 3,
    due_at          TEXT,
    has_time        INTEGER NOT NULL DEFAULT 1,
    recurrence      TEXT    NOT NULL DEFAULT 'none',
    category        TEXT,
    status          TEXT    NOT NULL DEFAULT 'pending',
    source          TEXT    NOT NULL DEFAULT 'text',
    raw_text        TEXT,
    remind_offsets  TEXT    NOT NULL DEFAULT '[]',
    batch           TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    completed_at    TEXT,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reminders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         INTEGER NOT NULL,
    user_id         INTEGER NOT NULL,
    fire_at         TEXT    NOT NULL,
    kind            TEXT    NOT NULL DEFAULT 'main',
    sent            INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ideas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    problem         TEXT    NOT NULL,
    solution        TEXT,
    status          TEXT    NOT NULL DEFAULT 'open',
    source          TEXT    NOT NULL DEFAULT 'text',
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ideas_user       ON ideas (user_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks (user_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_due        ON tasks (due_at);
CREATE INDEX IF NOT EXISTS idx_rem_queue        ON reminders (sent, fire_at);
CREATE INDEX IF NOT EXISTS idx_rem_task         ON reminders (task_id);
"""

SORT_SQL = {
    # Muddati o'tganlar va yaqinlar tepada, daraja hisobga olinadi
    "smart": "ORDER BY (due_at IS NULL) ASC, due_at ASC, priority ASC",
    "time": "ORDER BY (due_at IS NULL) ASC, due_at ASC, id ASC",
    "priority": "ORDER BY priority ASC, (due_at IS NULL) ASC, due_at ASC",
    "created": "ORDER BY created_at DESC, id DESC",
}


class Database:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------ setup

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.executescript(SCHEMA)
        await self._migrate()
        await self._conn.commit()
        log.info("Ma'lumotlar bazasi tayyor: %s", self._path)

    async def _migrate(self) -> None:
        """Eski bazalarga yangi ustunlarni qo'shadi."""
        wanted = {
            "tasks": {
                "remind_offsets": "TEXT NOT NULL DEFAULT '[]'",
                "category": "TEXT",
                "recurrence": "TEXT NOT NULL DEFAULT 'none'",
                "batch": "TEXT",
            },
            "users": {
                "sort_mode": "TEXT NOT NULL DEFAULT 'smart'",
                "digest_hour": "INTEGER NOT NULL DEFAULT 8",
                "last_digest": "TEXT",
            },
        }
        for table, columns in wanted.items():
            async with self.conn.execute(f"PRAGMA table_info({table})") as cur:
                existing = {row["name"] for row in await cur.fetchall()}
            for name, ddl in columns.items():
                if name not in existing:
                    log.info("Migratsiya: %s.%s ustuni qo'shildi", table, name)
                    await self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Baza ulanmagan: avval connect() chaqiring")
        return self._conn

    async def _fetchone(self, sql: str, params: Sequence[Any] = ()) -> aiosqlite.Row | None:
        async with self.conn.execute(sql, params) as cur:
            return await cur.fetchone()

    async def _fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[aiosqlite.Row]:
        async with self.conn.execute(sql, params) as cur:
            return list(await cur.fetchall())

    # ------------------------------------------------------------------ users

    async def get_user(self, user_id: int) -> aiosqlite.Row | None:
        return await self._fetchone("SELECT * FROM users WHERE id = ?", (user_id,))

    async def ensure_user(
        self,
        user_id: int,
        *,
        full_name: str | None = None,
        username: str | None = None,
        default_tz: str = "Asia/Tashkent",
    ) -> aiosqlite.Row:
        now = tu.dump(tu.utc_now())
        await self.conn.execute(
            """
            INSERT INTO users (id, full_name, username, tz, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                full_name = COALESCE(excluded.full_name, users.full_name),
                username  = excluded.username
            """,
            (user_id, full_name, username, default_tz, now),
        )
        await self.conn.commit()
        user = await self.get_user(user_id)
        assert user is not None
        return user

    async def register_user(self, user_id: int, phone: str, full_name: str | None) -> None:
        await self.conn.execute(
            "UPDATE users SET phone = ?, full_name = COALESCE(?, full_name), registered_at = ? WHERE id = ?",
            (phone, full_name, tu.dump(tu.utc_now()), user_id),
        )
        await self.conn.commit()

    async def update_user(self, user_id: int, **fields: Any) -> None:
        allowed = {"tz", "auto_save", "notify", "digest_hour", "sort_mode", "last_digest", "phone"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        sets = ", ".join(f"{k} = ?" for k in updates)
        await self.conn.execute(
            f"UPDATE users SET {sets} WHERE id = ?", (*updates.values(), user_id)
        )
        await self.conn.commit()

    async def active_users(self) -> list[aiosqlite.Row]:
        return await self._fetchall(
            "SELECT * FROM users WHERE registered_at IS NOT NULL AND notify = 1"
        )

    async def delete_user_data(self, user_id: int) -> None:
        await self.conn.execute("DELETE FROM reminders WHERE user_id = ?", (user_id,))
        await self.conn.execute("DELETE FROM tasks WHERE user_id = ?", (user_id,))
        await self.conn.execute("DELETE FROM ideas WHERE user_id = ?", (user_id,))
        await self.conn.commit()

    # ------------------------------------------------------------------ tasks

    async def create_task(
        self,
        user_id: int,
        *,
        title: str,
        notes: str | None = None,
        priority: int = PRIORITY_MEDIUM,
        due_at: datetime | None = None,
        has_time: bool = True,
        recurrence: str = "none",
        category: str | None = None,
        status: str = STATUS_PENDING,
        source: str = "text",
        raw_text: str | None = None,
        remind_offsets: Sequence[int] | None = None,
        batch: str | None = None,
    ) -> int:
        now = tu.dump(tu.utc_now())
        cur = await self.conn.execute(
            """
            INSERT INTO tasks (user_id, title, notes, priority, due_at, has_time, recurrence,
                               category, status, source, raw_text, remind_offsets,
                               batch, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, title.strip()[:300], notes, priority, tu.dump(due_at), int(has_time),
                recurrence, category, status, source, raw_text,
                json.dumps(list(remind_offsets or [])), batch, now, now,
            ),
        )
        await self.conn.commit()
        return int(cur.lastrowid)

    async def get_task(self, task_id: int, user_id: int) -> aiosqlite.Row | None:
        """Vazifa faqat egasiga qaytariladi."""
        return await self._fetchone(
            "SELECT * FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id)
        )

    async def update_task(self, task_id: int, user_id: int, **fields: Any) -> None:
        allowed = {
            "title", "notes", "priority", "due_at", "has_time", "recurrence",
            "category", "status", "completed_at", "remind_offsets",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        if isinstance(updates.get("remind_offsets"), (list, tuple)):
            updates["remind_offsets"] = json.dumps(list(updates["remind_offsets"]))
        for key in ("due_at", "completed_at"):
            if isinstance(updates.get(key), datetime):
                updates[key] = tu.dump(updates[key])
        if isinstance(updates.get("has_time"), bool):
            updates["has_time"] = int(updates["has_time"])
        updates["updated_at"] = tu.dump(tu.utc_now())
        sets = ", ".join(f"{k} = ?" for k in updates)
        await self.conn.execute(
            f"UPDATE tasks SET {sets} WHERE id = ? AND user_id = ?",
            (*updates.values(), task_id, user_id),
        )
        await self.conn.commit()

    async def delete_task(self, task_id: int, user_id: int) -> None:
        await self.conn.execute(
            "DELETE FROM reminders WHERE task_id = ? AND user_id = ?", (task_id, user_id)
        )
        await self.conn.execute(
            "DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id)
        )
        await self.conn.commit()

    async def list_tasks(
        self,
        user_id: int,
        *,
        scope: str = "all",
        sort_mode: str = "smart",
        limit: int = 100,
        offset: int = 0,
    ) -> list[aiosqlite.Row]:
        """scope: today | tomorrow | week | overdue | nodate | done | all"""
        user = await self.get_user(user_id)
        tz = user["tz"] if user else "Asia/Tashkent"
        now = tu.dump(tu.utc_now())

        where = ["user_id = ?"]
        params: list[Any] = [user_id]

        if scope == "done":
            where.append("status = ?")
            params.append(STATUS_DONE)
        else:
            where.append("status = ?")
            params.append(STATUS_PENDING)

        if scope == "today":
            # bugungi + muddati o'tib ketgan ishlar
            where.append("due_at IS NOT NULL AND due_at < ?")
            params.append(tu.dump(tu.end_of_day(tz)))
        elif scope == "todayonly":
            # bugungi, hali muddati o'tmagan ishlar (kunlik xulosa uchun)
            where.append("due_at >= ? AND due_at < ?")
            params += [now, tu.dump(tu.end_of_day(tz))]
        elif scope == "tomorrow":
            where.append("due_at >= ? AND due_at < ?")
            params += [tu.dump(tu.start_of_day(tz, 1)), tu.dump(tu.end_of_day(tz, 1))]
        elif scope == "week":
            where.append("due_at IS NOT NULL AND due_at < ?")
            params.append(tu.dump(tu.end_of_day(tz, 7)))
        elif scope == "overdue":
            where.append("due_at IS NOT NULL AND due_at < ?")
            params.append(now)
        elif scope == "nodate":
            where.append("due_at IS NULL")

        order = SORT_SQL.get(sort_mode, SORT_SQL["smart"])
        if scope == "done":
            order = "ORDER BY completed_at DESC, id DESC"

        sql = f"SELECT * FROM tasks WHERE {' AND '.join(where)} {order} LIMIT ? OFFSET ?"
        return await self._fetchall(sql, (*params, limit, offset))

    async def list_drafts(self, user_id: int, batch: str) -> list[aiosqlite.Row]:
        return await self._fetchall(
            "SELECT * FROM tasks WHERE user_id = ? AND batch = ? AND status = ? ORDER BY id",
            (user_id, batch, STATUS_DRAFT),
        )

    async def count_tasks(self, user_id: int, scope: str = "all") -> int:
        rows = await self.list_tasks(user_id, scope=scope, limit=10_000)
        return len(rows)

    async def stats(self, user_id: int, tz: str) -> dict[str, int]:
        now = tu.dump(tu.utc_now())
        row = await self._fetchone(
            """
            SELECT
                SUM(status = 'pending')                                    AS pending,
                SUM(status = 'done')                                       AS done,
                SUM(status = 'done'    AND completed_at >= ?)              AS done_today,
                SUM(status = 'done'    AND completed_at >= ?)              AS done_week,
                SUM(status = 'pending' AND due_at IS NOT NULL AND due_at < ?) AS overdue,
                SUM(status = 'pending' AND due_at IS NOT NULL AND due_at < ?) AS today_left,
                SUM(status = 'pending' AND priority = 1)                   AS p1,
                SUM(status = 'pending' AND priority = 2)                   AS p2,
                SUM(status = 'pending' AND priority = 3)                   AS p3,
                SUM(status = 'pending' AND priority = 4)                   AS p4,
                COUNT(*)                                                   AS total
            FROM tasks WHERE user_id = ? AND status != 'draft'
            """,
            (
                tu.dump(tu.start_of_day(tz)),
                tu.dump(tu.start_of_day(tz, -6)),
                now,
                tu.dump(tu.end_of_day(tz)),
                user_id,
            ),
        )
        return {k: int(row[k] or 0) for k in row.keys()} if row else {}

    async def purge_stale_drafts(self, older_than_hours: int = 24) -> int:
        cutoff = tu.dump(tu.utc_now() - timedelta(hours=older_than_hours))
        cur = await self.conn.execute(
            "DELETE FROM tasks WHERE status = ? AND created_at < ?",
            (STATUS_DRAFT, cutoff),
        )
        await self.conn.commit()
        return cur.rowcount or 0

    # ------------------------------------------------- g'oyalar (muammo/yechim)

    async def create_idea(
        self,
        user_id: int,
        *,
        problem: str,
        solution: str | None = None,
        source: str = "text",
    ) -> int:
        now = tu.dump(tu.utc_now())
        cur = await self.conn.execute(
            """
            INSERT INTO ideas (user_id, problem, solution, status, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, problem.strip()[:2000], (solution or None),
                IDEA_SOLVED if solution else IDEA_OPEN, source, now, now,
            ),
        )
        await self.conn.commit()
        return int(cur.lastrowid)

    async def get_idea(self, idea_id: int, user_id: int) -> aiosqlite.Row | None:
        """G'oya faqat egasiga qaytariladi."""
        return await self._fetchone(
            "SELECT * FROM ideas WHERE id = ? AND user_id = ?", (idea_id, user_id)
        )

    async def update_idea(self, idea_id: int, user_id: int, **fields: Any) -> None:
        allowed = {"problem", "solution", "status"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        updates["updated_at"] = tu.dump(tu.utc_now())
        sets = ", ".join(f"{k} = ?" for k in updates)
        await self.conn.execute(
            f"UPDATE ideas SET {sets} WHERE id = ? AND user_id = ?",
            (*updates.values(), idea_id, user_id),
        )
        await self.conn.commit()

    async def delete_idea(self, idea_id: int, user_id: int) -> None:
        await self.conn.execute(
            "DELETE FROM ideas WHERE id = ? AND user_id = ?", (idea_id, user_id)
        )
        await self.conn.commit()

    async def list_ideas(
        self, user_id: int, *, status: str = "all", limit: int = 100, offset: int = 0
    ) -> list[aiosqlite.Row]:
        where = ["user_id = ?"]
        params: list[Any] = [user_id]
        if status in (IDEA_OPEN, IDEA_SOLVED):
            where.append("status = ?")
            params.append(status)
        return await self._fetchall(
            f"SELECT * FROM ideas WHERE {' AND '.join(where)} "
            "ORDER BY (status = 'solved') ASC, id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )

    async def count_ideas(self, user_id: int, status: str = "all") -> int:
        return len(await self.list_ideas(user_id, status=status, limit=10_000))

    # -------------------------------------------------------------- reminders

    async def clear_reminders(self, task_id: int) -> None:
        await self.conn.execute(
            "DELETE FROM reminders WHERE task_id = ? AND sent = 0", (task_id,)
        )
        await self.conn.commit()

    async def add_reminders(self, task_id: int, user_id: int, moments: Iterable[tuple[datetime, str]]) -> None:
        now = tu.dump(tu.utc_now())
        rows = [(task_id, user_id, tu.dump(dt), kind, now) for dt, kind in moments]
        if not rows:
            return
        await self.conn.executemany(
            "INSERT INTO reminders (task_id, user_id, fire_at, kind, created_at) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        await self.conn.commit()

    async def due_reminders(self, limit: int = 50) -> list[aiosqlite.Row]:
        return await self._fetchall(
            """
            SELECT r.id AS reminder_id, r.kind, r.fire_at, t.*
            FROM reminders r
            JOIN tasks t ON t.id = r.task_id
            WHERE r.sent = 0 AND r.fire_at <= ?
            ORDER BY r.fire_at ASC
            LIMIT ?
            """,
            (tu.dump(tu.utc_now()), limit),
        )

    async def mark_reminder_sent(self, reminder_id: int, state: int = 1) -> None:
        await self.conn.execute(
            "UPDATE reminders SET sent = ? WHERE id = ?", (state, reminder_id)
        )
        await self.conn.commit()
