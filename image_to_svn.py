import os
import threading
import subprocess
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

TOKEN = os.environ.get("TELEGRAM_TOKEN")
SCRIPT_PATH = "image_to_svn.py"

flask_app = Flask("bot")

@flask_app.route("/")
def home():
    return "Bot is running"

@flask_app.route("/health")
def health():
    return "OK"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port, use_reloader=False)

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
    elif message.document:
        file_obj = await message.document.get_file()
        original_name = message.document.file_name or "file"
    else:
        await message.reply_text("Пожалуйста, отправь GIF, видео или файл-гифку.")
        return

    os.makedirs("./tmp", exist_ok=True)
    input_path = f"./tmp/{original_name}"
    await file_obj.download_to_drive(input_path)

    # Если mp4 — конвертируем в gif через ffmpeg
    if input_path.lower().endswith(".mp4"):
        gif_path = os.path.splitext(input_path)[0] + ".gif"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", input_path, "-vf", "fps=10,scale=42:-1:flags=neighbor", gif_path],
                capture_output=True, check=True
            )
            os.remove(input_path)
            input_path = gif_path
        except subprocess.CalledProcessError as e:
            await message.reply_text(f"Ошибка ffmpeg: {e.stderr.decode()[:200]}")
            return

    output_path = f"./tmp/{os.path.splitext(os.path.basename(input_path))[0]}.svn"

    try:
        result = subprocess.run(
            ["python", SCRIPT_PATH, input_path, output_path],
            capture_output=True, text=True, check=True
        )
        await message.reply_document(document=open(output_path, "rb"), filename="map.svn")
        context.user_data["waiting"] = False
    except subprocess.CalledProcessError as e:
        await message.reply_text(f"Ошибка конвертации: {e.stderr[:300]}")
    except Exception as e:
        await message.reply_text(f"Ошибка: {str(e)[:300]}")
    finally:
        for p in [input_path, output_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except:
                    pass

def main():
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.VIDEO | filters.ANIMATION | filters.Document.ALL, handle_media))
    application.run_polling()

main()
