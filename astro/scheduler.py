"""
Планировщик задач: ежедневная публикация в Telegram-канал и индивидуальная рассылка.
"""
import asyncio
import logging
from datetime import date, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _post_daily_channel(app) -> None:
    """Опубликовать сегодняшний гороскоп в Telegram-канал."""
    from database import get_posts_for_date, mark_post_sent, get_setting

    channel_id = get_setting("channel_id")
    if not channel_id:
        logger.warning("Автопостинг: channel_id не задан — пропуск")
        return

    today = date.today().isoformat()
    posts = get_posts_for_date(today)

    if not posts:
        logger.info("Нет постов на %s — пропуск", today)
        return

    bot = app.bot
    for post in posts:
        if post["posted"]:
            continue
        try:
            card_path = post.get("card_path")
            text = (
                f"<b>{post['sign']}</b>\n\n"
                f"<b>◆ Общее:</b> {post['general_text']}\n\n"
                f"<b>◆ Любовь:</b> {post['love_text']}\n\n"
                f"<b>◆ Финансы:</b> {post['finance_text']}\n\n"
                f"<b>◆ Здоровье:</b> {post['health_text']}"
            )

            if card_path and __import__("os").path.exists(card_path):
                with open(card_path, "rb") as f:
                    await bot.send_photo(
                        chat_id=channel_id,
                        photo=f,
                        caption=text,
                        parse_mode="HTML",
                    )
            else:
                await bot.send_message(
                    chat_id=channel_id,
                    text=text,
                    parse_mode="HTML",
                )

            mark_post_sent(today, post["sign"])
            logger.info("Пост отправлен в канал: %s %s", today, post["sign"])
        except Exception as e:
            logger.error("Ошибка отправки поста %s/%s: %s", today, post["sign"], e)


async def _send_individual(app) -> None:
    """Отправить персональный прогноз подписчикам."""
    from database import get_subscribed_users, get_post

    today = date.today().isoformat()
    users = get_subscribed_users()
    bot   = app.bot

    for user in users:
        sign = user.get("sun_sign")
        if not sign:
            continue
        post = get_post(today, sign)
        if not post:
            continue
        try:
            name = user.get("first_name") or "друг"
            text = (
                f"Привет, {name}! Твой прогноз на сегодня ✨\n\n"
                f"<b>{sign}</b>\n\n"
                f"<b>◆ Общее:</b> {post['general_text']}\n\n"
                f"<b>◆ Любовь:</b> {post['love_text']}\n\n"
                f"<b>◆ Финансы:</b> {post['finance_text']}\n\n"
                f"<b>◆ Здоровье:</b> {post['health_text']}"
            )
            card_path = post.get("card_path")
            if card_path and __import__("os").path.exists(card_path):
                with open(card_path, "rb") as f:
                    await bot.send_photo(
                        chat_id=user["telegram_id"],
                        photo=f,
                        caption=text,
                        parse_mode="HTML",
                    )
            else:
                await bot.send_message(
                    chat_id=user["telegram_id"],
                    text=text,
                    parse_mode="HTML",
                )
            logger.debug("Рассылка отправлена: %d (%s)", user["telegram_id"], sign)
        except Exception as e:
            logger.warning("Не удалось отправить рассылку %d: %s", user["telegram_id"], e)


async def _daily_job(app) -> None:
    """Общая ежедневная задача: сначала канал, потом подписчики."""
    logger.info("Запуск ежедневных задач...")
    await _post_daily_channel(app)
    await _send_individual(app)


def setup_scheduler(app, posting_time: str) -> AsyncIOScheduler:
    """
    Инициализировать и вернуть планировщик.

    posting_time: "ЧЧ:ММ"
    """
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)

    hour, minute = map(int, posting_time.split(":"))
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _daily_job,
        trigger="cron",
        hour=hour,
        minute=minute,
        args=[app],
        id="daily_post",
        replace_existing=True,
    )
    logger.info("Планировщик настроен на %s каждый день", posting_time)
    return _scheduler


def update_schedule(app, posting_time: str) -> None:
    """Обновить время публикации без перезапуска планировщика."""
    global _scheduler
    if _scheduler is None:
        setup_scheduler(app, posting_time)
        if not _scheduler.running:
            _scheduler.start()
        return

    hour, minute = map(int, posting_time.split(":"))
    _scheduler.reschedule_job(
        "daily_post",
        trigger="cron",
        hour=hour,
        minute=minute,
    )
    logger.info("Время публикации обновлено: %s", posting_time)
