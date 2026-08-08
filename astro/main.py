"""
Точка входа: запускает Flask-интерфейс (в фоновом потоке) и Telegram-бота.
Запуск: python main.py
"""
import asyncio
import io
import logging
import os
import threading
import zipfile
from datetime import date, datetime, timedelta

from flask import Flask, jsonify, redirect, render_template, request, send_file, url_for

from config import FLASK_PORT, FLASK_SECRET_KEY, OUTPUT_CARDS_DIR, setup_logging
from database import (
    get_available_dates,
    get_posts_for_date,
    get_setting,
    init_db,
    set_setting,
    upsert_post,
)
from astrology import generate_daily_horoscope, ZODIAC_SIGNS
from card_generator import generate_all_cards_for_date, ensure_fonts

setup_logging()
logger = logging.getLogger(__name__)

# ── Flask приложение ──────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

# Глобальная ссылка на Telegram-приложение (устанавливается в main())
_telegram_app = None


@app.route("/")
def index():
    available_dates = get_available_dates()
    channel_id   = get_setting("channel_id",    "")
    posting_time = get_setting("posting_time",  "09:00")
    return render_template(
        "index.html",
        available_dates=available_dates,
        channel_id=channel_id,
        posting_time=posting_time,
        today=date.today().isoformat(),
    )


@app.route("/generate", methods=["POST"])
def generate():
    """Сгенерировать прогнозы и карточки за диапазон дат."""
    start_str = request.form.get("start_date", "").strip()
    end_str   = request.form.get("end_date",   "").strip()

    try:
        start = datetime.strptime(start_str, "%Y-%m-%d").date()
        end   = datetime.strptime(end_str,   "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Неверный формат даты"}), 400

    if end < start:
        return jsonify({"error": "Конечная дата раньше начальной"}), 400

    if (end - start).days > 30:
        return jsonify({"error": "Диапазон не может превышать 31 день"}), 400

    generated = []
    cur = start
    while cur <= end:
        date_str   = cur.isoformat()
        horoscopes = {sign: generate_daily_horoscope(sign, date_str) for sign in ZODIAC_SIGNS}
        card_paths = generate_all_cards_for_date(date_str, horoscopes)

        for sign in ZODIAC_SIGNS:
            h = horoscopes[sign]
            upsert_post(
                post_date    = date_str,
                sign         = sign,
                general_text = h["general"],
                love_text    = h["love"],
                finance_text = h["finance"],
                health_text  = h["health"],
                card_path    = card_paths.get(sign, ""),
            )
        generated.append(date_str)
        logger.info("Сгенерировано: %s (%d знаков)", date_str, len(ZODIAC_SIGNS))
        cur += timedelta(days=1)

    return jsonify({
        "success": True,
        "message": f"Готово! Сгенерировано {len(generated)} дней: {generated[0]} → {generated[-1]}",
        "dates": generated,
    })


@app.route("/download/<date_str>")
def download_zip(date_str: str):
    """Скачать ZIP-архив с карточками за указанную дату."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return "Неверная дата", 400

    folder = os.path.join(OUTPUT_CARDS_DIR, date_str)
    if not os.path.isdir(folder):
        return f"Нет данных за {date_str}. Сначала сгенерируйте контент.", 404

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in sorted(os.listdir(folder)):
            if fname.endswith(".png"):
                zf.write(os.path.join(folder, fname), fname)

    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"horoscope_{date_str}.zip",
    )


@app.route("/settings", methods=["POST"])
def save_settings():
    """Сохранить настройки автопостинга."""
    channel_id   = request.form.get("channel_id",   "").strip()
    posting_time = request.form.get("posting_time", "09:00").strip()

    set_setting("channel_id",   channel_id)
    set_setting("posting_time", posting_time)

    # Обновить расписание без перезапуска
    if _telegram_app is not None:
        from scheduler import update_schedule
        try:
            update_schedule(_telegram_app, posting_time)
        except Exception as e:
            logger.warning("Не удалось обновить расписание: %s", e)

    logger.info("Настройки сохранены: channel=%s time=%s", channel_id, posting_time)
    return redirect(url_for("index") + "?saved=1")


@app.route("/api/dates")
def api_dates():
    return jsonify(get_available_dates())


@app.route("/api/preview/<date_str>/<sign>")
def api_preview(date_str: str, sign: str):
    """Вернуть JSON с текстами прогноза (для предпросмотра)."""
    from database import get_post
    post = get_post(date_str, sign)
    if not post:
        return jsonify({"error": "Не найдено"}), 404
    return jsonify(post)


# ── Запуск ────────────────────────────────────────────────────────────────────

def run_flask() -> None:
    logger.info("Flask запущен на порту %d", FLASK_PORT)
    app.run(
        host="0.0.0.0",
        port=FLASK_PORT,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


async def main() -> None:
    global _telegram_app

    # Инициализация
    init_db()
    ensure_fonts()

    # Flask в фоновом потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Telegram-бот
    from bot import build_application, run_bot
    telegram_app = build_application()
    _telegram_app = telegram_app

    # Планировщик
    posting_time = get_setting("posting_time", "09:00")
    from scheduler import setup_scheduler
    scheduler = setup_scheduler(telegram_app, posting_time)
    scheduler.start()
    logger.info("Планировщик запущен (время рассылки: %s)", posting_time)

    # Запуск бота (polling)
    await run_bot(telegram_app)

    # Бесконечное ожидание
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановка...")
    finally:
        scheduler.shutdown(wait=False)
        await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
