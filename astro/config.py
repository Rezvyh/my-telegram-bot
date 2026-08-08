"""
Конфигурация приложения. Значения берутся из переменных окружения (.env).
"""
import os
import logging
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID: str = os.getenv("TELEGRAM_CHANNEL_ID", "")

# ── Scheduling ────────────────────────────────────────────────────────────────
POSTING_TIME: str = os.getenv("POSTING_TIME", "09:00")

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH: str = os.path.join(BASE_DIR, os.getenv("DATABASE_PATH", "astro.db"))
OUTPUT_CARDS_DIR: str = os.path.join(BASE_DIR, os.getenv("OUTPUT_CARDS_DIR", "output_cards"))
FONTS_DIR: str = os.path.join(BASE_DIR, os.getenv("FONTS_DIR", "fonts"))

# ── Flask ─────────────────────────────────────────────────────────────────────
FLASK_PORT: int = int(os.getenv("FLASK_PORT", "8000"))
FLASK_SECRET_KEY: str = os.getenv("FLASK_SECRET_KEY", "astro-secret-key-change-me")

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Глушим избыточные логи сторонних библиотек
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("geopy").setLevel(logging.WARNING)
