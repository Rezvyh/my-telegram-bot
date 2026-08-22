from astro.main import app, bot, scheduler
import threading

if __name__ == "__main__":
    # Запускаем Flask-приложение в отдельном потоке
    threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=8000), daemon=True
    ).start()

    # Запускаем бота и планировщик
    bot.polling()
