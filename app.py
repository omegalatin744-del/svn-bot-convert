import os
import threading
import subprocess
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# Конфигурация
TOKEN = os.environ.get("TELEGRAM_TOKEN")
SCRIPT_PATH = "image_to_svn.py"

# Flask для health-check (чтобы Render не ругался на "No open ports")
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"

@app.route("/health")
def health():
    return "OK"

# --- Логика бота ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Создать .svn из GIF/видео", callback_data="start_convert")]]
    await update.message.reply_text(
        "Нажми кнопку, затем отправь гифку или видео.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "start_convert":
        await query.edit_message_text("Отлично! Теперь отправь мне GIF или видеофайл.")
        context.user_data["waiting"] = True

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting"):
        await update.message.reply_text("Сначала нажми /start и выбери действие.")
        return

    message = update.message
    file_obj = None
    original_name = "input"

    if message.video:
        file_obj = await message.video.get_file()
        original_name = message.video.file_name or "video.mp4"
    elif message.animation:
        file_obj = await message.animation.get_file()
        original_name = message.animation.file_name or "animation.gif"
    else:
        await message.reply_text("Пожалуйста, отправь именно GIF или видео.")
        return

    # Скачиваем
    os.makedirs("./tmp", exist_ok=True)
    input_path = f"./tmp/{original_name}"
    await file_obj.download_to_drive(input_path)

    output_path = f"./tmp/{os.path.splitext(original_name)[0]}.svn"

    try:
        # Запускаем ваш скрипт
        result = subprocess.run(
            ["python", SCRIPT_PATH, input_path, output_path],
            capture_output=True, text=True, check=True
        )
        await message.reply_document(document=open(output_path, "rb"), filename="map.svn")
        context.user_data["waiting"] = False
    except subprocess.CalledProcessError as e:
        await message.reply_text(f"Ошибка конвертации: {e.stderr[:200]}")
    except Exception as e:
        await message.reply_text(f"Ошибка: {str(e)[:200]}")
    finally:
        for p in [input_path, output_path]:
            if os.path.exists(p):
                os.remove(p)

def run_bot():
    """Запуск Telegram-бота в отдельном потоке."""
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.VIDEO | filters.ANIMATION, handle_media))
    application.run_polling()

if __name__ == "__main__":
    # Запускаем бота в фоне
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Flask слушает порт, который даёт Render
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)