import os
import threading
import subprocess
import random
from datetime import datetime, timedelta
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

TOKEN = os.environ.get("TELEGRAM_TOKEN")
SCRIPT_VIDEO = "image_to_svn.py"
SCRIPT_PHOTO = "image_to_svn_photo.py"

ADMIN_ID = 6667068532
LOG_CHAT_ID = -1003919249553

KYIV_TZ = timedelta(hours=3)

MOD_URL = "https://github.com/omegalatin744-del/svn-bot-convert/releases/download/1.0/HP0.4NoOpti.apk"

BANNED_IDS = set()

USAGE_LOG = {}
LIMIT_PER_DAY = 3
DAY_SECONDS = 24 * 60 * 60

INFO_TEXT = (
    "Информация\n\n"
    "1. Путь к загруженному сохранению:\n\n"
    "Android: /storage/emulated/0/Download/Telegram/\n"
    "iOS: зависит от выбранной вами папки\n"
    "Windows: C:\\Users\\<имя>\\Downloads\\Telegram Desktop\\\n"
    "Linux: /home/<имя>/Downloads/Telegram Desktop/\n\n"
    "2. Путь к сохранениям Hypper Sandbox:\n\n"
    "Android: Android/data/com.Hypper/files/saves\n"
    "iOS: /var/mobile/Containers/Data/Application/<UUID>/Documents/saves\n"
    "Windows: C:\\Users\\<имя>\\AppData\\Local\\Hypper\\saves\n"
    "Linux: /home/<имя_пользователя>/.local/share/Hypper/saves\n\n"
    "Форматы файлов, которые принимаются ботом: GIF, MP4, PNG, JPG, JPEG, WEBP, BMP.\n\n"
    "Мод на Hypper Sandbox:\n"
    "HP0.4NoOpti — убирает оптимизацию мониторов на расстоянии "
    "(текст и цветной фон на мониторах перестаёт быть невидным при дальних расстояниях). "
    "Версия мода устарела.\n\n"
    "Лимиты и тонкости:\n"
    "• Формат MP4 имеет ограничение >20 МБ.\n"
    "• GIF лучше отправлять файлом.\n"
    "• Лимит конвертирований: 3 сохранения на 24 часа."
)

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

def check_limit(user_id):
    now_ts = datetime.utcnow().timestamp()
    times = USAGE_LOG.get(user_id, [])
    times = [t for t in times if now_ts - t < DAY_SECONDS]
    USAGE_LOG[user_id] = times
    remaining = LIMIT_PER_DAY - len(times)
    return remaining > 0, max(remaining, 0)

def add_usage(user_id):
    now_ts = datetime.utcnow().timestamp()
    times = USAGE_LOG.get(user_id, [])
    times = [t for t in times if now_ts - t < DAY_SECONDS]
    times.append(now_ts)
    USAGE_LOG[user_id] = times

# ── Команды ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in BANNED_IDS:
        await update.message.reply_text("Вы заблокированы и не можете пользоваться ботом.")
        await send_log(context, f"Забаненный {uid} попытался использовать /start")
        return

    keyboard = [
        [InlineKeyboardButton("Создать видео-карту", callback_data="start_video")],
        [InlineKeyboardButton("Создать фото-карту", callback_data="start_photo")],
        [InlineKeyboardButton("Дополнительно", callback_data="more_menu")],
    ]
    await update.message.reply_text(
        "Выбери тип карты, затем отправь GIF или видео.",
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

# ── Кнопки ───────────────────────────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if uid in BANNED_IDS:
        await query.edit_message_text("Вы заблокированы.")
        return

    if query.data == "start_video":
        await query.edit_message_text("Отлично. Отправьте GIF или видео для видео-карты.")
        context.user_data["waiting"] = True
        context.user_data["mode"] = "video"

    elif query.data == "start_photo":
        await query.edit_message_text("Отлично. Отправьте GIF, PNG или JPG для фото-карты.")
        context.user_data["waiting"] = True
        context.user_data["mode"] = "photo"

    elif query.data == "more_menu":
        keyboard = [
            [InlineKeyboardButton("Информация", callback_data="show_info")],
            [InlineKeyboardButton("HP0.4NoOpti", url=MOD_URL)],
            [InlineKeyboardButton("Назад", callback_data="back_main")],
        ]
        await query.edit_message_text("Дополнительно:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "show_info":
        keyboard = [[InlineKeyboardButton("Назад", callback_data="more_menu")]]
        await query.edit_message_text(INFO_TEXT, reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "back_main":
        keyboard = [
            [InlineKeyboardButton("Создать видео-карту", callback_data="start_video")],
            [InlineKeyboardButton("Создать фото-карту", callback_data="start_photo")],
            [InlineKeyboardButton("Дополнительно", callback_data="more_menu")],
        ]
        await query.edit_message_text("Главное меню:", reply_markup=InlineKeyboardMarkup(keyboard))

# ── Обработка медиа ──────────────────────────────────────────────────────────

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
        await update.message.reply_text("Сначала нажми /start и выбери действие.")
        return

    mode = context.user_data.get("mode", "video")

    can_use, remaining = check_limit(uid)
    if not can_use:
        await update.message.reply_text(
            "Лимит исчерпан.\n"
            "Вы использовали 3 сохранения за последние 24 часа.\n"
            "Попробуйте позже."
        )
        await send_log(
            context,
            f"Лимит исчерпан\n"
            f"@{username} (ID: {uid})\n"
            f"Имя: {full_name}\n"
            f"Попытка отправить файл сверх лимита"
        )
        return

    message = update.message
    file_obj = None
    original_name = "input"
    file_size = 0
    file_id = None

    if message.video:
        file_obj = await message.video.get_file()
        original_name = message.video.file_name or "video.mp4"
        file_size = message.video.file_size
        file_id = message.video.file_id
    elif message.animation:
        file_obj = await message.animation.get_file()
        original_name = message.animation.file_name or "animation.gif"
        file_size = message.animation.file_size
        file_id = message.animation.file_id
    elif message.document:
        file_obj = await message.document.get_file()
        original_name = message.document.file_name or "file"
        file_size = message.document.file_size
        file_id = message.document.file_id
    else:
        await message.reply_text("Пожалуйста, отправь GIF, видео или файл-гифку.")
        return

    size_kb = file_size // 1024 if file_size else 0
    now = kyiv_now().strftime("%d.%m.%Y %H:%M:%S")
    mode_label = "ФОТО" if mode == "photo" else "ВИДЕО"

    log_event(f"MEDIA ({mode_label}): {uid} @{username} '{original_name}' {size_kb} KB")

    try:
        if file_size <= 50 * 1024 * 1024:
            await context.bot.send_document(
                chat_id=LOG_CHAT_ID,
                document=file_id,
                filename=original_name
            )
    except Exception as e:
        log_event(f"Не удалось переслать файл в группу: {e}")

    await send_log(
        context,
        f"Новый файл ({mode_label})\n"
        f"@{username} (ID: {uid})\n"
        f"Имя: {full_name}\n"
        f"Файл: {original_name}\n"
        f"Размер: {size_kb} KB\n"
        f"Осталось попыток: {remaining - 1}\n"
        f"{now}"
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

    script = SCRIPT_PHOTO if mode == "photo" else SCRIPT_VIDEO
    prefix = "photo" if mode == "photo" else "map"

    try:
        subprocess.run(
            ["python", script, input_path, output_path],
            capture_output=True, text=True, check=True
        )
        new_name = f"{prefix}{random.randint(100000, 999999)}.svn"
        await message.reply_document(document=open(output_path, "rb"), filename=new_name)

        add_usage(uid)
        _, remaining_after = check_limit(uid)

        log_event(f"SUCCESS ({mode_label}): {uid} @{username} -> {new_name}")

        await send_log(
            context,
            f"Сконвертировано ({mode_label})\n"
            f"@{username} (ID: {uid})\n"
            f"Отдано: {new_name}\n"
            f"Осталось попыток: {remaining_after}\n"
            f"{kyiv_now().strftime('%d.%m.%Y %H:%M:%S')}"
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
