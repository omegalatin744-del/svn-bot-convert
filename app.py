import os
import threading
import subprocess
import random
from datetime import datetime, timedelta
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

TOKEN = os.environ.get("TELEGRAM_TOKEN")
SCRIPT_PATH = "image_to_svn.py"

ADMIN_ID = 6667068532
LOG_CHAT_ID = -1003919249553

KYIV_TZ = timedelta(hours=3)

BANNED_IDS = set()

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

def kyiv_now():
    return datetime.utcnow() + KYIV_TZ

def log_event(text):
    ts = kyiv_now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[LOG {ts}] {text}", flush=True)

async def send_log(context, text):
    try:
        await context.bot.send_message(chat_id=LOG_CHAT_ID, text=text)
    except Exception as e:
        log_event(f"Не удалось отправить в группу логов: {e}")

# ── Команды ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in BANNED_IDS:
        await update.message.reply_text("Вы заблокированы и не можете пользоваться ботом.")
        await send_log(context, f"Забаненный {uid} попытался использовать /start")
        return
    keyboard = [[InlineKeyboardButton("Создать .svn из GIF/видео", callback_data="start_convert")]]
    await update.message.reply_text(
        "Нажми кнопку, затем отправь GIF или видео.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Использование: /ban <user_id>")
        return
    try:
        target = int(context.args[0])
        BANNED_IDS.add(target)
        log_event(f"BAN: {target}")
        await update.message.reply_text(f"Пользователь {target} добавлен в чёрный список.")
        await send_log(context, f"Забанен пользователь: {target}")
    except ValueError:
        await update.message.reply_text("user_id должен быть числом.")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Использование: /unban <user_id>")
        return
    try:
        target = int(context.args[0])
        BANNED_IDS.discard(target)
        log_event(f"UNBAN: {target}")
        await update.message.reply_text(f"Пользователь {target} разблокирован.")
        await send_log(context, f"Разбанен пользователь: {target}")
    except ValueError:
        await update.message.reply_text("user_id должен быть числом.")

async def list_banned(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not BANNED_IDS:
        await update.message.reply_text("Чёрный список пуст.")
    else:
        ids = "\n".join(str(i) for i in BANNED_IDS)
        await update.message.reply_text(f"Забаненные user_id:\n{ids}")

# ── Обработка медиа ──────────────────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    if uid in BANNED_IDS:
        await query.edit_message_text("Вы заблокированы.")
        return
    if query.data == "start_convert":
        await query.edit_message_text("Отлично, Теперь отправьте GIF или видеофайл.")
        context.user_data["waiting"] = True

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    username = user.username or "(без username)"
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "—"

    if uid in BANNED_IDS:
        await update.message.reply_text("Вы заблокированы и не можете пользоваться ботом.")
        await send_log(context, f"Забаненный {uid} @{username} пытался отправить файл")
        return

    if not context.user_data.get("waiting"):
        await update.message.reply_text("Сначала нажмите /start и выбери действие.")
        return

    message = update.message
    file_obj = None
    original_name = "input"
    file_size = 0

    if message.video:
        file_obj = await message.video.get_file()
        original_name = message.video.file_name or "video.mp4"
        file_size = message.video.file_size
    elif message.animation:
        file_obj = await message.animation.get_file()
        original_name = message.animation.file_name or "animation.gif"
        file_size = message.animation.file_size
    elif message.document:
        file_obj = await message.document.get_file()
        original_name = message.document.file_name or "file"
        file_size = message.document.file_size
    else:
        await message.reply_text("Пожалуйста, отправьте GIF, видео или файл-GIF.")
        return

    size_kb = file_size // 1024 if file_size else 0
    now = kyiv_now().strftime("%d.%m.%Y %H:%M:%S")

    log_event(f"MEDIA: {uid} @{username} '{original_name}' {size_kb} KB")

    await send_log(
        context,
        f"Новый файл\n"
        f"@{username} (ID: {uid})\n"
        f"Имя: {full_name}\n"
        f"Файл: {original_name}\n"
        f"Размер: {size_kb} KB\n"
        f"{now} "
    )

    os.makedirs("./tmp", exist_ok=True)
    input_path = f"./tmp/{original_name}"
    await file_obj.download_to_drive(input_path)

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
            await send_log(context, f"Ошибка ffmpeg у {uid}: {e.stderr.decode()[:100]}")
            return

    output_path = f"./tmp/{os.path.splitext(os.path.basename(input_path))[0]}.svn"

    try:
        subprocess.run(
            ["python", SCRIPT_PATH, input_path, output_path],
            capture_output=True, text=True, check=True
        )
        new_name = f"map{random.randint(100000, 999999)}.svn"
        await message.reply_document(document=open(output_path, "rb"), filename=new_name)
        log_event(f"SUCCESS: {uid} @{username} -> {new_name}")
        await send_log(
            context,
            f"Сконвертировано\n"
            f"@{username} (ID: {uid})\n"
            f"Отдано: {new_name}\n"
            f"{kyiv_now().strftime('%d.%m.%Y %H:%M:%S')} Kyiv"
        )
        context.user_data["waiting"] = False
    except subprocess.CalledProcessError as e:
        await message.reply_text(f"Ошибка конвертации: {e.stderr[:300]}")
        await send_log(context, f"Ошибка конвертации у {uid}: {e.stderr[:150]}")
    except Exception as e:
        await message.reply_text(f"Ошибка: {str(e)[:300]}")
        await send_log(context, f"Ошибка у {uid}: {str(e)[:150]}")
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
    application.add_handler(CommandHandler("ban", ban))
    application.add_handler(CommandHandler("unban", unban))
    application.add_handler(CommandHandler("list_banned", list_banned))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.VIDEO | filters.ANIMATION | filters.Document.ALL, handle_media))
    application.run_polling()

main()
