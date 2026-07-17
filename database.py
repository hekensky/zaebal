"""
Слой работы с базой данных (SQLite, через aiosqlite).
Хранит все сделки трейдера: активные (ждут ТВХ/тейка/стопа) и закрытые (история).
"""

import datetime as dt
from dataclasses import dataclass
from typing import Optional

import aiosqlite

DB_PATH = "journal.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    ticker        TEXT NOT NULL,
    direction     TEXT NOT NULL,          -- LONG / SHORT
    entry         REAL NOT NULL,          -- ТВХ
    stop_loss     REAL NOT NULL,
    take_profit   REAL NOT NULL,
    comment_open  TEXT,                   -- почему открыл
    status        TEXT NOT NULL DEFAULT 'active',  -- active / tp / sl / missed / cancelled
    comment_close TEXT,                   -- почему закрылась так, как закрылась
    photo_file_id TEXT,                   -- скрин PnL (для tp / sl)
    created_at    TEXT NOT NULL,
    closed_at     TEXT
);
"""


@dataclass
class Position:
    id: int
    user_id: int
    ticker: str
    direction: str
    entry: float
    stop_loss: float
    take_profit: float
    comment_open: Optional[str]
    status: str
    comment_close: Optional[str]
    photo_file_id: Optional[str]
    created_at: str
    closed_at: Optional[str]

    @property
    def risk_reward(self) -> float:
        """Плановое соотношение прибыль/риск, посчитанное при открытии."""
        risk = abs(self.entry - self.stop_loss)
        reward = abs(self.take_profit - self.entry)
        if risk == 0:
            return 0.0
        return round(reward / risk, 2)


def _row_to_position(row: aiosqlite.Row) -> Position:
    return Position(
        id=row["id"],
        user_id=row["user_id"],
        ticker=row["ticker"],
        direction=row["direction"],
        entry=row["entry"],
        stop_loss=row["stop_loss"],
        take_profit=row["take_profit"],
        comment_open=row["comment_open"],
        status=row["status"],
        comment_close=row["comment_close"],
        photo_file_id=row["photo_file_id"],
        created_at=row["created_at"],
        closed_at=row["closed_at"],
    )


async def init_db(db_path: str = DB_PATH) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(SCHEMA)
        await db.commit()


async def add_position(
    db_path: str,
    user_id: int,
    ticker: str,
    direction: str,
    entry: float,
    stop_loss: float,
    take_profit: float,
    comment_open: str,
) -> int:
    now = dt.datetime.now().isoformat(timespec="seconds")
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            """INSERT INTO positions
               (user_id, ticker, direction, entry, stop_loss, take_profit,
                comment_open, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)""",
            (user_id, ticker.upper(), direction, entry, stop_loss, take_profit,
             comment_open, now),
        )
        await db.commit()
        return cur.lastrowid


async def get_position(db_path: str, position_id: int) -> Optional[Position]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM positions WHERE id = ?", (position_id,))
        row = await cur.fetchone()
        return _row_to_position(row) if row else None


async def get_active_positions(db_path: str, user_id: int) -> list[Position]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM positions WHERE user_id = ? AND status = 'active' "
            "ORDER BY created_at DESC",
            (user_id,),
        )
        rows = await cur.fetchall()
        return [_row_to_position(r) for r in rows]


async def get_history(
    db_path: str, user_id: int, limit: int = 5, offset: int = 0
) -> list[Position]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM positions WHERE user_id = ? AND status != 'active' "
            "ORDER BY closed_at DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        )
        rows = await cur.fetchall()
        return [_row_to_position(r) for r in rows]


async def count_history(db_path: str, user_id: int) -> int:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM positions WHERE user_id = ? AND status != 'active'",
            (user_id,),
        )
        row = await cur.fetchone()
        return row[0]


async def close_position(
    db_path: str,
    position_id: int,
    status: str,
    comment_close: Optional[str],
    photo_file_id: Optional[str],
) -> None:
    now = dt.datetime.now().isoformat(timespec="seconds")
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """UPDATE positions
               SET status = ?, comment_close = ?, photo_file_id = ?, closed_at = ?
               WHERE id = ?""",
            (status, comment_close, photo_file_id, now, position_id),
        )
        await db.commit()


async def delete_position(db_path: str, position_id: int) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM positions WHERE id = ?", (position_id,))
        await db.commit()


async def get_stats(db_path: str, user_id: int) -> dict:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT status, COUNT(*) as cnt FROM positions WHERE user_id = ? "
            "GROUP BY status",
            (user_id,),
        )
        rows = await cur.fetchall()
    counts = {r["status"]: r["cnt"] for r in rows}
    tp = counts.get("tp", 0)
    sl = counts.get("sl", 0)
    missed = counts.get("missed", 0)
    active = counts.get("active", 0)
    closed_trades = tp + sl
    winrate = round(tp / closed_trades * 100, 1) if closed_trades else 0.0
    return {
        "active": active,
        "tp": tp,
        "sl": sl,
        "missed": missed,
        "closed_trades": closed_trades,
        "winrate": winrate,
    }
