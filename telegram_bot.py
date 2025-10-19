import os
import asyncio
import signal
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv
from hyperliquid_client import HyperliquidClient

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.getenv("TELEGRAM_ALLOWED_USERS", "0"))

client = None
monitoring_task = None

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("❌ У вас нет доступа к этому боту")
        return
    
    welcome_text = """
🤖 Ekubo-Hyperliquid Trading Bot

Команды:
/set_deviation <число> - Установить отклонение (в ETH до 3 знаков после запятой)
/set_timeout <секунды> - Установить интервал проверки (в секундах)
/start_monitoring - Запустить софт
/stop_monitoring - Остановить софт
/status - Текущие настройки
    """
    await update.message.reply_text(welcome_text)


async def set_deviation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("❌ Нет доступа")
        return
    
    global client
    
    if not context.args:
        await update.message.reply_text("❌ Укажите значение: /set_deviation 0.002")
        return
    
    try:
        deviation = float(context.args[0])
        if deviation <= 0:
            await update.message.reply_text("❌ Отклонение должно быть > 0")
            return
        
        if client is None:
            await update.message.reply_text("⏳ Инициализация клиента, подождите...")
            client = HyperliquidClient()
        
        client.set_deviation(deviation)
        await update.message.reply_text(f"✅ Deviation установлен: {deviation}")
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат числа")


async def set_timeout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("❌ Нет доступа")
        return
    
    global client
    
    if not context.args:
        await update.message.reply_text("❌ Укажите значение: /set_timeout 60")
        return
    
    try:
        timeout = int(context.args[0])
        if timeout < 10:
            await update.message.reply_text("❌ Таймаут должен быть >= 10 секунд")
            return
        
        if client is None:
            await update.message.reply_text("⏳ Инициализация клиента, подождите...")
            client = HyperliquidClient()
        
        client.set_timeout(timeout)
        await update.message.reply_text(f"✅ Timeout установлен: {timeout} сек")
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат числа")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("❌ Нет доступа")
        return
    
    global client, monitoring_task
    
    if client is None:
        await update.message.reply_text("⚠️ Клиент не инициализирован")
        return
    
    is_running = monitoring_task is not None and not monitoring_task.done()
    
    ekubo_success, ekubo_data = client.get_ekubo_positions()
    fees_success, fees_data = client.get_ekubo_fees()
    
    if ekubo_success:
        eth_in_pool = ekubo_data[0]
        usdc_in_pool = ekubo_data[1]
        ekubo_status = f"ETH: {eth_in_pool}, USDC: {usdc_in_pool}"
    else:
        ekubo_status = f"❌ Ошибка: {ekubo_data}"
    
    if fees_success:
        fee_eth_in_pool = fees_data[0]
        fee_usdc_in_pool = fees_data[1]
        fees_status = f"ETH: {fee_eth_in_pool:.6f}, USDC: {fee_usdc_in_pool:.6f}"
    else:
        fees_status = f"❌ Ошибка: {fees_data}"

    try:
        hl_position = client.get_hl_positions()
        if hl_position:
            short_size = float(hl_position['szi'])
            short_entry = float(hl_position['entryPx'])
            hl_status = f"SHORT {short_size:.6f} ETH @ ${short_entry:.2f}"
        else:
            hl_status = "Нет позиций"
    except:
        hl_status = "Нет позиций"
    
    status_text = f"""
📊 Статус бота:

🔄 Мониторинг: {'🟢 Запущен' if is_running else '🔴 Остановлен'}

⚙️ Параметры:
  Deviation: {client.get_deviation()}
  Timeout: {client.get_timeout()} сек
  
💰 Цена ETH: ${client.get_eth_price():.2f}

🏊 Ekubo пул: {ekubo_status}
🏦 Hyperliquid: {hl_status}
💰 Ekubo fees: {fees_status}
    """
    
    await update.message.reply_text(status_text)

async def start_monitoring_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start_monitoring"""
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("❌ Нет доступа")
        return
    
    global client, monitoring_task
    
    if monitoring_task is not None and not monitoring_task.done():
        await update.message.reply_text("⚠️ Мониторинг уже запущен")
        return
    
    if client is None:
        await update.message.reply_text("⏳ Инициализация клиента, подождите...")
        client = HyperliquidClient()
    
    client.start_control_loop()
    
    client.telegram_chat_id = update.effective_chat.id
    client.telegram_bot = context.bot
    
    await update.message.reply_text("🚀 Запуск мониторинга очка Егора...")
    
    monitoring_task = asyncio.create_task(run_monitoring_loop(client))
    
    await update.message.reply_text("✅ Мониторинг очка Егора запущен!")


async def stop_monitoring_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("❌ Нет доступа")
        return
    
    global client, monitoring_task
    
    if monitoring_task is None or monitoring_task.done():
        await update.message.reply_text("⚠️ Мониторинг не запущен")
        return
    
    client.stop_control_loop()
    await update.message.reply_text("🛑 Остановка мониторинга очка Егора...")
    
    await monitoring_task
    monitoring_task = None
    
    await update.message.reply_text("✅ Мониторинг очка Егора остановлен")


async def run_monitoring_loop(client: HyperliquidClient):
    try:
        while client.control_loop_flag:
            try:
                success, action = client.check_to_change_position()
                
                message = f"⏰ {asyncio.get_event_loop().time()}\n"
                
                if success:
                    message += f"🔄 Действие: {action}\n"
                    
                    if action == "place_min_short":
                        result_success, result = client.place_min_short()
                        message += f"   place_min_short: {'✅' if result_success else '❌'}\n"
                    elif action == "place_max_short":
                        result_success, result = client.place_max_short()
                        message += f"   place_max_short: {'✅' if result_success else '❌'}\n"
                    elif action == "decrease":
                        result_success, result = client.decrease_short()
                        message += f"   Уменьшен шорт: {'✅' if result_success else '❌'}\n"
                    elif action == "increase":
                        result_success, result = client.increase_short()
                        message += f"   Увеличен шорт: {'✅' if result_success else '❌'}\n"
                    
                    if result_success and isinstance(result, dict):
                        filled = result.get('response', {}).get('data', {}).get('statuses', [{}])[0].get('filled')
                        if filled:
                            message += f"   Исполнено: {filled.get('totalSz')} ETH @ ${filled.get('avgPx')}"
                else:
                    message += f"✅ {action}"
                
                if hasattr(client, 'telegram_bot') and client.telegram_bot:
                    await client.telegram_bot.send_message(
                        chat_id=client.telegram_chat_id,
                        text=message
                    )
                
            except Exception as e:
                error_msg = f"❌ Ошибка в цикле: {e}"
                if hasattr(client, 'telegram_bot') and client.telegram_bot:
                    await client.telegram_bot.send_message(
                        chat_id=client.telegram_chat_id,
                        text=error_msg
                    )
            
            await asyncio.sleep(client.get_timeout())
    except asyncio.CancelledError:
        print("   Задача мониторинга отменена")
        raise


def signal_handler(sig, frame):
    """Обработчик сигнала завершения (Ctrl+C)"""
    global client, monitoring_task
    
    print("\n\n🛑 Получен сигнал завершения, останавливаем бот...")
    
    if client:
        client.stop_control_loop()
    
    if monitoring_task and not monitoring_task.done():
        monitoring_task.cancel()
    
    print("✅ Бот остановлен")
    sys.exit(0)


def main():
    global client
    
    if not BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN не установлен в .env")
        print("\nДобавьте в .env:")
        print("TELEGRAM_BOT_TOKEN=ваш_токен_от_BotFather")
        print("TELEGRAM_USER_ID=ваш_telegram_id")
        return
    
    if not ALLOWED_USER_ID:
        print("❌ TELEGRAM_USER_ID не установлен в .env")
        return
    
    # Регистрируем обработчик сигнала Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("🤖 Запуск Telegram бота...")
    print(f"   Разрешенный пользователь ID: {ALLOWED_USER_ID}")
    
    # Инициализация клиента при старте (займет время один раз)
    print("⏳ Инициализация Hyperliquid клиента...")
    try:
        client = HyperliquidClient()
        print("✅ Клиент инициализирован")
    except Exception as e:
        print(f"⚠️  Не удалось инициализировать клиент: {e}")
        print("   Клиент будет создан при первом использовании")
        client = None
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("set_deviation", set_deviation_command))
    application.add_handler(CommandHandler("set_timeout", set_timeout_command))
    application.add_handler(CommandHandler("start_monitoring", start_monitoring_command))
    application.add_handler(CommandHandler("stop_monitoring", stop_monitoring_command))
    application.add_handler(CommandHandler("status", status_command))
    
    print("✅ Telegram бот запущен!")
    print("   Нажмите Ctrl+C для остановки\n")
    
    try:
        application.run_polling()
    except KeyboardInterrupt:
        print("\n🛑 Остановка бота...")
    finally:
        if client:
            client.stop_control_loop()
        print("✅ Бот остановлен")

if __name__ == "__main__":
    main()

