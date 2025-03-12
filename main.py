import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from alerts_in_ua import AsyncClient as AsyncAlertsClient
import pytz
import datetime

# Токен вашого Telegram бота
TELEGRAM_TOKEN = 'ТВОЙ ТЕЛЕГРАМ ТОКЕН'

# Логування для бота
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Список активних користувачів, які підписалися на сповіщення
subscribed_users = set()
last_alerts_regions = set()
ended_alerts = set()  # Список завершених тривог

# Ініціалізація асинхронного клієнта для отримання тривог
alerts_client = AsyncAlertsClient(token="0806e9f2a61d68b2cf84b10e06de4e3602bb9557ab2203")


# Отримання інформації про тривоги
async def get_alerts():
    try:
        # Отримуємо активні тривоги
        active_alerts = await alerts_client.get_active_alerts()

        if active_alerts:
            logger.info(f"Активні тривоги: {active_alerts}")
            return active_alerts
        else:
            return []
    except Exception as e:
        logger.error(f"Помилка при отриманні даних: {e}")
        return []


# Форматування часу в Київську зону
def format_kyiv_time(timestamp):
    if not timestamp:
        return "Неізвестно"
    try:
        dt = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        kyiv_tz = pytz.timezone('Europe/Kiev')
        local_time = dt.astimezone(kyiv_tz)
        return local_time.strftime("%d.%m.%Y %H:%M:%S")  # без временной зоны
    except Exception as e:
        logger.error(f"Помилка форматування часу: {e}")
        return timestamp



# Словник для відображення типів тривог
alert_types = {
    "air_raid": "✈️ Повітряна тривога",
    "artillery_shelling": "💥 Обстріл",
    "urban_fights": "⚔️ Вуличні бої"
}


# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.chat_id
    subscribed_users.add(user_id)
    await update.message.reply_text(
        'Привіт! Я бот для сповіщень про тривоги в Україні. Я автоматично надсилаю повідомлення при нових тривогах.')


# Команда /alerts для отримання інформації про тривоги
async def alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    alerts_data = await get_alerts()
    if alerts_data:
        alert_message = "⚠️ АКТИВНІ ТРИВОГИ: ⚠️\n\n"
        for alert in alerts_data:
            region_name = alert.location_title if hasattr(alert, 'location_title') else 'Невідома область'
            started_at = format_kyiv_time(alert.started_at) if hasattr(alert, 'started_at') else 'Неізвестно'
            alert_type = alert.alert_type if hasattr(alert, 'alert_type') else 'Неізвестий тип'

            # Отримуємо текст тривоги зі словника
            alert_text = alert_types.get(alert_type, "❗️ Невідомий тип тривоги")

            alert_message += f"Область: {region_name}\n"
            alert_message += f"Тип: {alert_text}\n"
            alert_message += f"Початок: {started_at}\n\n"

        await update.message.reply_text(alert_message)
    else:
        await update.message.reply_text("Немає активних тривог на даний момент.")


# Фоновий процес моніторингу тривог
async def monitor_alerts(application):
    global last_alerts_regions, ended_alerts  # Використовуємо глобальні змінні для останнього стану тривог
    while True:
        try:
            current_alerts = await get_alerts()
            current_alerts_regions = set()
            new_alerts = []
            ended_alerts_now = set()

            # Логуємо поточні тривоги для відладки
            logger.info(f"Поточні тривоги: {current_alerts}")

            # Обробляємо поточні тривоги
            for alert in current_alerts:
                region = alert.get('location_title', '')
                current_alerts_regions.add(region)

                # Перевіряємо, чи є ця тривога новою
                if region not in last_alerts_regions:
                    new_alerts.append(alert)

            # Логуємо нові тривоги для відладки
            logger.info(f"Нові тривоги: {new_alerts}")

            # Перевірка на завершені тривоги (тривоги, яких вже немає)
            for alert in last_alerts_regions:
                if alert not in current_alerts_regions:
                    ended_alerts_now.add(alert)

            # Логуємо завершені тривоги
            logger.info(f"Завершені тривоги: {ended_alerts_now}")

            # Надсилаємо сповіщення про нові тривоги
            if new_alerts and subscribed_users:
                alert_message = "⚠️ НОВА ТРИВОГА! ⚠️\n\n"

                for alert in new_alerts:
                    region = alert.get('location_title', 'Невідома область')
                    started_at = format_kyiv_time(alert.get('started_at'))
                    alert_type = alert.get('alert_type', 'Неізвестний тип')

                    # Отримуємо текст тривоги зі словника
                    alert_text = alert_types.get(alert_type, "❗️ Невідомий тип тривоги")

                    alert_message += f"Область: {region}\n"
                    alert_message += f"Тип: {alert_text}\n"
                    alert_message += f"Початок: {started_at}\n\n"

                for user_id in subscribed_users:
                    try:
                        await application.bot.send_message(chat_id=user_id, text=alert_message)
                    except Exception as e:
                        logger.error(f"Помилка при надсиланні повідомлення: {e}")

            # Надсилаємо сповіщення про відбій
            if ended_alerts_now and subscribed_users:
                ended_alert_message = "✅ ВІДБІЙ ТРИВОГИ! ✅\n\n"

                for alert in ended_alerts_now:
                    ended_alert_message += f"Область: {alert}\n"
                    ended_alert_message += "Тривога завершена.\n\n"

                for user_id in subscribed_users:
                    try:
                        await application.bot.send_message(chat_id=user_id, text=ended_alert_message)
                    except Exception as e:
                        logger.error(f"Помилка при надсиланні повідомлення: {e}")

            # Оновлюємо попередні тривоги
            last_alerts_regions = current_alerts_regions
            ended_alerts = ended_alerts_now
        except Exception as e:
            logger.error(f"Помилка в моніторингу: {e}")

        # Чекаємо 10 секунд перед наступною перевіркою
        await asyncio.sleep(10)


async def main():
    # Ініціалізація додатку
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Додаємо обробники команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("alerts", alerts))

    # Запускаємо фоновий моніторинг
    asyncio.create_task(monitor_alerts(application))

    # Запускаємо бота
    await application.run_polling()  # Не використовуємо asyncio.run() тут


if __name__ == '__main__':
    # Запускаємо main() з використанням async event loop
    import nest_asyncio
    nest_asyncio.apply()  # Патч для роботи з вже працюючим циклом
    asyncio.run(main())
