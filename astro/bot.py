"""
Telegram-бот для сбора данных пользователей и индивидуальной рассылки.
Использует python-telegram-bot v20+ (async/await).
"""
import logging
import re
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

from config import TELEGRAM_BOT_TOKEN
from astrology import (
    get_city_coordinates,
    calculate_natal_chart,
    get_sun_sign_by_date,
    SIGN_META,
)
from database import upsert_user, update_user_birth, get_user, set_user_subscribed

logger = logging.getLogger(__name__)

# ── Состояния диалога ─────────────────────────────────────────────────────────
BIRTH_DATE, BIRTH_TIME, BIRTH_CITY = range(3)


# ── Валидация ─────────────────────────────────────────────────────────────────

def _valid_date(s: str) -> bool:
    try:
        datetime.strptime(s.strip(), "%d.%m.%Y")
        return True
    except ValueError:
        return False


def _valid_time(s: str) -> bool:
    return bool(re.match(r"^\d{1,2}:\d{2}$", s.strip()))


# ── Хэндлеры ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    upsert_user(user.id, user.username, user.first_name)
    name = user.first_name or "друг"

    await update.message.reply_text(
        f"✨ Привет, {name}!\n\n"
        "Я помогу составить твою натальную карту и каждый день присылать "
        "персональный астрологический прогноз.\n\n"
        "Для начала мне нужна дата рождения.\n"
        "Введи её в формате <b>ДД.ММ.ГГГГ</b>:",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    return BIRTH_DATE


async def receive_birth_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not _valid_date(text):
        await update.message.reply_text(
            "Неверный формат. Введи дату в виде <b>ДД.ММ.ГГГГ</b>, например: <code>15.06.1990</code>",
            parse_mode="HTML",
        )
        return BIRTH_DATE

    context.user_data["birth_date"] = text
    await update.message.reply_text(
        "Отлично! Теперь введи <b>время рождения</b> в формате <b>ЧЧ:ММ</b> (по местному времени).\n\n"
        "Если точное время неизвестно — введи <code>12:00</code>",
        parse_mode="HTML",
    )
    return BIRTH_TIME


async def receive_birth_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not _valid_time(text):
        await update.message.reply_text(
            "Неверный формат. Введи время в виде <b>ЧЧ:ММ</b>, например: <code>14:30</code>",
            parse_mode="HTML",
        )
        return BIRTH_TIME

    context.user_data["birth_time"] = text
    await update.message.reply_text(
        "Почти готово! Напиши <b>город рождения</b> (на русском или английском):",
        parse_mode="HTML",
    )
    return BIRTH_CITY


async def receive_birth_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user      = update.effective_user
    city_name = update.message.text.strip()
    bd        = context.user_data["birth_date"]
    bt        = context.user_data["birth_time"]

    await update.message.reply_text("🔭 Вычисляю натальную карту…", reply_markup=ReplyKeyboardRemove())

    # Геокодирование
    lat, lon = get_city_coordinates(city_name)

    if lat is None:
        # Если город не найден — используем приближение по знаку Солнца
        logger.warning("Город не найден: %s", city_name)
        lat, lon = 55.75, 37.62   # Москва по умолчанию
        await update.message.reply_text(
            f"⚠️ Город <b>{city_name}</b> не найден. Использую координаты по умолчанию.\n"
            "Знак Луны и Асцендент могут быть неточными.",
            parse_mode="HTML",
        )

    # Расчёт натальной карты
    chart = calculate_natal_chart(bd, bt, lat, lon)
    sun_sign  = chart["sun_sign"]
    moon_sign = chart["moon_sign"]
    ascendant = chart["ascendant"]

    meta_sun  = SIGN_META.get(sun_sign, {})
    meta_moon = SIGN_META.get(moon_sign, {})
    meta_asc  = SIGN_META.get(ascendant, {})

    # Сохранить в БД
    update_user_birth(
        telegram_id=user.id,
        birth_date=bd,
        birth_time=bt,
        birth_city=city_name,
        lat=lat,
        lon=lon,
        sun_sign=sun_sign,
        moon_sign=moon_sign,
        ascendant=ascendant,
    )

    # Отправить результат
    reply = (
        f"🌟 <b>Твоя натальная карта</b>\n\n"
        f"☀️ <b>Знак Солнца:</b> {meta_sun.get('symbol','')} {sun_sign}\n"
        f"   <i>Планета: {meta_sun.get('planet','')}, стихия: {meta_sun.get('element','')}</i>\n\n"
        f"🌙 <b>Знак Луны:</b> {meta_moon.get('symbol','')} {moon_sign}\n"
        f"   <i>Планета: {meta_moon.get('planet','')}, стихия: {meta_moon.get('element','')}</i>\n\n"
        f"⬆️ <b>Асцендент:</b> {meta_asc.get('symbol','')} {ascendant}\n"
        f"   <i>Планета: {meta_asc.get('planet','')}, стихия: {meta_asc.get('element','')}</i>\n\n"
        f"Место рождения: {city_name}\n"
        f"Дата: {bd}  Время: {bt}\n\n"
        f"✅ Ты подписан(а) на ежедневную рассылку!\n"
        f"Каждое утро буду присылать тебе персональный прогноз для знака <b>{sun_sign}</b>."
    )
    await update.message.reply_text(reply, parse_mode="HTML")
    logger.info("Натальная карта рассчитана для %d (%s)", user.id, sun_sign)
    return ConversationHandler.END


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Регистрация отменена. Напиши /start чтобы начать снова.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def cmd_mycard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать текущую натальную карту пользователя."""
    user_db = get_user(update.effective_user.id)
    if not user_db or not user_db.get("sun_sign"):
        await update.message.reply_text(
            "У тебя ещё нет натальной карты. Напиши /start чтобы создать её."
        )
        return

    meta = SIGN_META.get(user_db["sun_sign"], {})
    await update.message.reply_text(
        f"🌟 <b>Твоя натальная карта</b>\n\n"
        f"☀️ Солнце: {meta.get('symbol','')} <b>{user_db['sun_sign']}</b>\n"
        f"🌙 Луна: {user_db.get('moon_sign','—')}\n"
        f"⬆️ Асцендент: {user_db.get('ascendant','—')}\n\n"
        f"📍 Город: {user_db.get('birth_city','—')}\n"
        f"📅 Дата: {user_db.get('birth_date','—')}  ⏰ Время: {user_db.get('birth_time','—')}",
        parse_mode="HTML",
    )


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Прогноз на сегодня для пользователя."""
    from datetime import date
    from astrology import generate_daily_horoscope

    user_db = get_user(update.effective_user.id)
    if not user_db or not user_db.get("sun_sign"):
        await update.message.reply_text(
            "Сначала зарегистрируйся: /start"
        )
        return

    sign  = user_db["sun_sign"]
    today = date.today().isoformat()
    h     = generate_daily_horoscope(sign, today)
    meta  = SIGN_META.get(sign, {})

    # Ищем готовую карточку
    from database import get_post
    post  = get_post(today, sign)
    text  = (
        f"{meta.get('symbol','')} <b>{sign}</b> — {today}\n\n"
        f"<b>◆ Общее:</b> {h['general']}\n\n"
        f"<b>◆ Любовь:</b> {h['love']}\n\n"
        f"<b>◆ Финансы:</b> {h['finance']}\n\n"
        f"<b>◆ Здоровье:</b> {h['health']}"
    )

    import os
    if post and post.get("card_path") and os.path.exists(post["card_path"]):
        with open(post["card_path"], "rb") as f:
            await update.message.reply_photo(photo=f, caption=text, parse_mode="HTML")
    else:
        await update.message.reply_text(text, parse_mode="HTML")


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_db = get_user(update.effective_user.id)
    if not user_db or not user_db.get("sun_sign"):
        await update.message.reply_text("Сначала зарегистрируйся: /start")
        return
    set_user_subscribed(update.effective_user.id, True)
    await update.message.reply_text("✅ Рассылка включена! Прогнозы будут приходить каждое утро.")


async def cmd_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    set_user_subscribed(update.effective_user.id, False)
    await update.message.reply_text(
        "🔕 Рассылка отключена. Чтобы включить снова — /subscribe"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "<b>Команды бота:</b>\n\n"
        "/start — создать натальную карту\n"
        "/today — прогноз на сегодня\n"
        "/mycard — моя натальная карта\n"
        "/subscribe — включить рассылку\n"
        "/unsubscribe — отключить рассылку\n"
        "/help — справка",
        parse_mode="HTML",
    )


# ── Сборка приложения ─────────────────────────────────────────────────────────

def build_application() -> Application:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан!")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # ConversationHandler для /start
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            BIRTH_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_birth_date)],
            BIRTH_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_birth_time)],
            BIRTH_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_birth_city)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("today",       cmd_today))
    app.add_handler(CommandHandler("mycard",      cmd_mycard))
    app.add_handler(CommandHandler("subscribe",   cmd_subscribe))
    app.add_handler(CommandHandler("unsubscribe", cmd_unsubscribe))
    app.add_handler(CommandHandler("help",        cmd_help))

    return app


async def run_bot(app: Application) -> None:
    """Запустить бот (polling) — вызывается из main.py."""
    commands = [
        BotCommand("start",       "Создать натальную карту"),
        BotCommand("today",       "Прогноз на сегодня"),
        BotCommand("mycard",      "Моя натальная карта"),
        BotCommand("subscribe",   "Включить рассылку"),
        BotCommand("unsubscribe", "Отключить рассылку"),
        BotCommand("help",        "Справка"),
    ]
    await app.bot.set_my_commands(commands)
    logger.info("Бот запущен (polling)")

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
