"""
Работа с базой данных SQLite: инициализация, CRUD-операции.
"""
import sqlite3
import logging
from contextlib import contextmanager
from typing import Optional, Any

from config import DATABASE_PATH

logger = logging.getLogger(__name__)

# ── Schema ────────────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id     INTEGER UNIQUE NOT NULL,
    username        TEXT,
    first_name      TEXT,
    birth_date      TEXT,       -- ДД.ММ.ГГГГ
    birth_time      TEXT,       -- ЧЧ:ММ
    birth_city      TEXT,
    lat             REAL,
    lon             REAL,
    sun_sign        TEXT,
    moon_sign       TEXT,
    ascendant       TEXT,
    subscribed      INTEGER DEFAULT 1,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scheduled_posts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    post_date       TEXT NOT NULL,   -- YYYY-MM-DD
    sign            TEXT NOT NULL,
    general_text    TEXT,
    love_text       TEXT,
    finance_text    TEXT,
    health_text     TEXT,
    card_path       TEXT,
    posted          INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(post_date, sign)
);

CREATE TABLE IF NOT EXISTS settings (
    key             TEXT PRIMARY KEY,
    value           TEXT
);
"""


@contextmanager
def get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Создать таблицы при первом запуске."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
    logger.info("База данных инициализирована: %s", DATABASE_PATH)


# ── Settings ──────────────────────────────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
    logger.debug("Настройка сохранена: %s=%s", key, value)


# ── Users ─────────────────────────────────────────────────────────────────────

def upsert_user(
    telegram_id: int,
    username: Optional[str],
    first_name: Optional[str],
) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO users(telegram_id, username, first_name) VALUES(?,?,?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username, "
            "first_name=excluded.first_name",
            (telegram_id, username, first_name),
        )


def update_user_birth(
    telegram_id: int,
    birth_date: str,
    birth_time: str,
    birth_city: str,
    lat: float,
    lon: float,
    sun_sign: str,
    moon_sign: str,
    ascendant: str,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE users SET
                birth_date=?, birth_time=?, birth_city=?,
                lat=?, lon=?,
                sun_sign=?, moon_sign=?, ascendant=?,
                subscribed=1
               WHERE telegram_id=?""",
            (birth_date, birth_time, birth_city, lat, lon,
             sun_sign, moon_sign, ascendant, telegram_id),
        )
    logger.info("Данные пользователя %d обновлены", telegram_id)


def get_subscribed_users() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM users WHERE subscribed=1 AND sun_sign IS NOT NULL"
        ).fetchall()
    return [dict(r) for r in rows]


def set_user_subscribed(telegram_id: int, subscribed: bool) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET subscribed=? WHERE telegram_id=?",
            (int(subscribed), telegram_id),
        )


def get_user(telegram_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE telegram_id=?", (telegram_id,)
        ).fetchone()
    return dict(row) if row else None


# ── Scheduled posts ───────────────────────────────────────────────────────────

def upsert_post(
    post_date: str,
    sign: str,
    general_text: str,
    love_text: str,
    finance_text: str,
    health_text: str,
    card_path: str,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO scheduled_posts
                (post_date, sign, general_text, love_text, finance_text, health_text, card_path)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(post_date, sign) DO UPDATE SET
                general_text=excluded.general_text,
                love_text=excluded.love_text,
                finance_text=excluded.finance_text,
                health_text=excluded.health_text,
                card_path=excluded.card_path,
                posted=0""",
            (post_date, sign, general_text, love_text, finance_text, health_text, card_path),
        )


def get_posts_for_date(post_date: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_posts WHERE post_date=? ORDER BY sign",
            (post_date,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_post(post_date: str, sign: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM scheduled_posts WHERE post_date=? AND sign=?",
            (post_date, sign),
        ).fetchone()
    return dict(row) if row else None


def mark_post_sent(post_date: str, sign: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE scheduled_posts SET posted=1 WHERE post_date=? AND sign=?",
            (post_date, sign),
        )


def get_available_dates() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT post_date FROM scheduled_posts ORDER BY post_date DESC"
        ).fetchall()
    return [r["post_date"] for r in rows]
