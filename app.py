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
SCRIPT_MINI  = "image_to_svn_mini.py"
SCRIPT_OPTI  = "opti_save.py"

ADMIN_ID = 6667068532
LOG_CHAT_ID = -1003919249553

KYIV_TZ = timedelta(hours=3)

MOD_URL = "https://github.com/omegalatin744-del/svn-bot-convert/releases/download/1.0/HP0.4NoOpti.apk"

BANNED_IDS = set()

USAGE_LOG = {}
LIMIT_PER_DAY = 3

OPTI_LOG = {}
OPTI_LIMIT_PER_DAY = 10

DAY_SECONDS = 24 * 60 * 60

UNLIMITED = {}


def parse_duration(s):
    s = (s or "").strip().lower()
    if s in ("", "forever", "inf", "infinity"):
        return None
    try:
        if s.endswith("h"):
            return datetime.utcnow().timestamp() + int(s[:-1]) * 3600
        if s.endswith("d"):
            return datetime.utcnow().timestamp() + int(s[:-1]) * 86400
        if s.endswith("m"):
            return datetime.utcnow().timestamp() + int(s[:-1]) * 60
    except ValueError:
        return None
    return None


def duration_label(expire_ts):
    if expire_ts is None:
        return "forever"
    left = int(expire_ts - datetime.utcnow().timestamp())
    if left <= 0:
        return "expired"
    if left < 3600:
        return f"{left // 60}m"
    if left < 86400:
        return f"{left // 3600}h"
    return f"{left // 86400}d"


def has_unlimited(user_id, kind):
    entry = UNLIMITED.get(user_id)
    if not entry:
        return False
    ts = entry.get(kind)
    if kind == "all":
        ts_all = entry.get("all")
        if ts_all is None and "all" in entry:
            return True
        if ts_all is not None:
            if ts_all > datetime.utcnow().timestamp():
                return True
            else:
                entry.pop("all", None)
    if ts is None and kind in entry:
        return True
    if ts is not None:
        if ts > datetime.utcnow().timestamp():
            return True
        else:
            entry.pop(kind, None)
    return False


def grant_unlimited(user_id, kinds, expire_ts):
    entry = UNLIMITED.setdefault(user_id, {})
    for k in kinds:
        entry[k] = expire_ts


def revoke_unlimited(user_id):
    UNLIMITED.pop(user_id, None)


INFO_TEXT = (
    "Информация\n\n"
    "1. Путь к загруженному сохранению:\n\n"
    "Android: /storage/emulated/0/Download/Telegram/\n"
    "iOS: зависит от выбранной вами папки\n"
    "Windows: C:\\Users\\<имя>\\Downloads\\Telegram Desktop\\\n"
    "Linux: /home/<имя>/Downloads/Telegram Desktop\n\n"
    "2. Путь к сохранениям Hypper Sandbox:\n\n"
    "Android: Android/data/com.Hypper/files/saves\n"
    "iOS: /var/mobile/Containers/Data/Application/<UUID>/Documents/saves\n"
    "Windows: C:\\Users\\<имя>\\AppData\\Local\\Hypper\\saves\n"
    "Linux: /home/<имя_пользователя>/.local/share/Hypper/saves\n\n"
    "Форматы файлов, которые принимаются ботом: GIF, MP4, PNG, JPG, JPEG, WEBP, BMP.\n\n"
    "Мод на Hypper Sandbox:\n"
    "NP0.4NoOpti — убирает оптимизацию мониторов на расстоянии. "
    "(Текст и цветной фон на мониторах не перестаёт быть невидным при дальних расстояниях). "
    "Версия мода устарела.\n\n"
    "Opti-save — это система оптимизирования веса сохранения путём сжатия. "
    "В отличии от некоторых систем, файл можно оптимизировать, а также деоптимизировать до первоначального состояния.\n"
    "Система проверялась на сохранениях, и она полностью рабочая, "
    "но шанс повредить файл никогда не равен нулю.\n\n"
    "ITS mini — упрощённая модель image to svn, адаптированная к использованию результата "
    "в режиме мультиплеера. В отличии от обычных видео-карт, которые идут от ± 3000 объектов, "
    "эта функция выдаёт сохранение с жёстким ограничением: до 909 пропов, до 8 кадров.\n\n"
    "Лимиты и тонкости:\n\n"
    "Формат MP4 имеет ограничение >20 МБ.\n"
    "GIF лучше отправлять файлом.\n\n"
    "Лимит конвертирований:\n"
    "3 конвертирования видео/фото или же ITS mini карт на 24 часа.\n"
    "10 оптимизаций/деоптимизаций на 24 часа"
)

RULES_TEXT = (
    "Правила\n\n"
    "1. Запрещено отправлять порнографию, материалы 18+ и любой NSFW-контент.\n\n"
    "2. Запрещён спам, флуд и массовая рассылка одинаковых файлов.\n\n"
    "3. Запрещено оскорбление других пользователей, угрозы и травля.\n\n"
    "4. Запрещено отправлять файлы, содержащие вирусы или вредоносный код.\n\n"
    "5. Запрещено выдавать себя за администрацию бота.\n\n"
    "6. Запрещено использовать бота для незаконных действий.\n\n"
    "7. Администрация оставляет за собой право забанить пользователя "
    "без предупреждения при нарушении правил.\n\n"
    "8. Незнание правил не освобождает от ответственности."
)

OPTI_TEXT = (
    "Opti-save\n\n"
    "Оптимизировать — сжимает .svn в формат .svnz (короткие ключи + таблица имён). "
    "Файл становится в 2-3 раза меньше, но полностью восстанавливаемым.\n\n"
    "Деоптимизировать — разворачивает .svnz обратно в стандартный .svn.\n\n"
    "Лимит: 10 операций в сутки (общий на обе кнопки)."
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

def check_limit(user_id, log_dict, limit):
    now_ts = datetime.utcnow().timestamp()
    times = log_dict.get(user_id, [])
    times = [t for t in times if now_ts - t < DAY_SECONDS]
    log_dict[user_id] = times
    remaining = limit - len(times)
    return remaining > 0, max(remaining, 0)

def add_usage(user_id, log_dict):
    now_ts = datetime.utcnow().timestamp()
    times = log_dict.get(user_id, [])
    times = [t for t in times if now_ts - t < DAY_SECONDS]
    times.append(now_ts)
    log_dict[user_id] = times

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
        [InlineKeyboardButton("Opti-save", callback_data="opti_menu")],
        [InlineKeyboardButton("ITM mini", callback_data="start_mini")],
        [InlineKeyboardButton("Дополнительно", callback_data="more_menu")],
    ]
    await update.message.reply_text(
        "Выбери действие, затем отправь файл.",
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

async def unlimited_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Использование:\n"
            "/unlimited <id> <kind> [time]\n\n"
            "kind: video | photo | mini | opti | all\n"
            "time: 24h | 7d | 30d | forever (по умолчанию forever)\n\n"
            "Примеры:\n"
            "/unlimited 123456789 video 24h\n"
            "/unlimited 123456789 all\n"
            "/unlimited 123456789 opti 7d"
        )
        return
    try:
        target = int(args[0])
    except ValueError:
        await update.message.reply_text("user_id должен быть числом.")
        return

    kind = args[1].lower()
    valid_kinds = ("video", "photo", "mini", "opti", "all")
    if kind not in valid_kinds:
        await update.message.reply_text(f"kind должен быть одним из: {', '.join(valid_kinds)}")
        return

    duration = args[2] if len(args) > 2 else "forever"
    expire_ts = parse_duration(duration)

    grant_unlimited(target, [kind], expire_ts)
    label = duration_label(expire_ts)

    await update.message.reply_text(f"Безлимит выдан: {target} / {kind} / {label}")
    await send_log(context, f"Безлимит выдан\nID: {target}\nТип: {kind}\nСрок: {label}")


async def limited_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Использование: /limited <user_id>")
        return
    try:
        target = int(context.args[0])
        revoke_unlimited(target)
        await update.message.reply_text(f"Безлимит снят с {target}.")
        await send_log(context, f"Безлимит снят\nID: {target}")
    except ValueError:
        await update.message.reply_text("user_id должен быть числом.")


async def list_unlimited(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not UNLIMITED:
        await update.message.reply_text("Список безлимита пуст.")
        return
    lines = []
    for uid, entry in UNLIMITED.items():
        parts = []
        for k in ("video", "photo", "mini", "opti", "all"):
            if k in entry:
                parts.append(f"{k}:{duration_label(entry[k])}")
        lines.append(f"{uid}: {', '.join(parts)}")
    await update.message.reply_text("Безлимит:\n" + "\n".join(lines))


# ── Кнопки ───────────────────────────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if uid in BANNED_IDS:
        await query.edit_message_text("Вы заблокированы.")
        return

    if query.data == "start_video":
        await query.edit_message_text("Отлично! Отправь GIF или видео для видео-карты.")
        context.user_data["waiting"] = True
        context.user_data["mode"] = "video"

    elif query.data == "start_photo":
        await query.edit_message_text("Отлично! Отправь GIF, PNG или JPG для фото-карты.")
        context.user_data["waiting"] = True
        context.user_data["mode"] = "photo"

    elif query.data == "start_mini":
        await query.edit_message_text("Отлично! Отправь GIF или видео для ITM mini.")
        context.user_data["waiting"] = True
        context.user_data["mode"] = "mini"

    elif query.data == "opti_menu":
        keyboard = [
            [InlineKeyboardButton("Оптимизировать", callback_data="opti_optimize")],
            [InlineKeyboardButton("Деоптимизировать", callback_data="opti_deoptimize")],
            [InlineKeyboardButton("Назад", callback_data="back_main")],
        ]
        await query.edit_message_text(OPTI_TEXT, reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "opti_optimize":
        await query.edit_message_text("Отправь .svn-файл для оптимизации.")
        context.user_data["waiting"] = True
        context.user_data["mode"] = "opti_optimize"

    elif query.data == "opti_deoptimize":
        await query.edit_message_text("Отправь .svnz-файл для деоптимизации.")
        context.user_data["waiting"] = True
        context.user_data["mode"] = "opti_deoptimize"

    elif query.data == "more_menu":
        keyboard = [
            [InlineKeyboardButton("Информация", callback_data="show_info")],
            [InlineKeyboardButton("Правила", callback_data="show_rules")],
            [InlineKeyboardButton("HP0.4NoOpti", url=MOD_URL)],
            [InlineKeyboardButton("Назад", callback_data="back_main")],
        ]
        await query.edit_message_text("Дополнительно:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "show_info":
        keyboard = [[InlineKeyboardButton("Назад", callback_data="more_menu")]]
        await query.edit_message_text(INFO_TEXT, reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "show_rules":
        keyboard = [[InlineKeyboardButton("Назад", callback_data="more_menu")]]
        await query.edit_message_text(RULES_TEXT, reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "back_main":
        keyboard = [
            [InlineKeyboardButton("Создать видео-карту", callback_data="start_video")],
            [InlineKeyboardButton("Создать фото-карту", callback_data="start_photo")],
            [InlineKeyboardButton("Opti-save", callback_data="opti_menu")],
            [InlineKeyboardButton("ITM mini", callback_data="start_mini")],
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

    if mode in ("opti_optimize", "opti_deoptimize"):
        kind = "opti"
        log_dict = OPTI_LOG
        limit = OPTI_LIMIT_PER_DAY
    elif mode == "photo":
        kind = "photo"
        log_dict = USAGE_LOG
        limit = LIMIT_PER_DAY
    elif mode == "mini":
        kind = "mini"
        log_dict = USAGE_LOG
        limit = LIMIT_PER_DAY
    else:
        kind = "video"
        log_dict = USAGE_LOG
        limit = LIMIT_PER_DAY

    unlimited = has_unlimited(uid, kind)

    if not unlimited:
        can_use, remaining = check_limit(uid, log_dict, limit)
        if not can_use:
            if kind == "opti":
                await update.message.reply_text(
                    "Лимит Opti-save исчерпан (10 операций за 24 часа)."
                )
            else:
                await update.message.reply_text(
                    "Лимит исчерпан.\nВы использовали 3 сохранения за последние 24 часа."
                )
            await send_log(
                context,
                f"Лимит исчерпан\n@{username} (ID: {uid})\nИмя: {full_name}"
            )
            return
    else:
        remaining = None

    message = update.message
    file_obj = None
    original_name = "input"
    file_size = 0
    file_id = None

    if message.document:
        file_obj = await message.document.get_file()
        original_name = message.document.file_name or "file"
        file_size = message.document.file_size
        file_id = message.document.file_id
    elif message.video:
        file_obj = await message.video.get_file()
        original_name = message.video.file_name or "video.mp4"
        file_size = message.video.file_size
        file_id = message.video.file_id
    elif message.animation:
        file_obj = await message.animation.get_file()
        original_name = message.animation.file_name or "animation.gif"
        file_size = message.animation.file_size
        file_id = message.animation.file_id
    else:
        await message.reply_text("Пожалуйста, отправь файл.")
        return

    if mode == "opti_optimize":
        if original_name.lower().endswith(".svnz"):
            await message.reply_text("Этот файл уже сжат (.svnz). Деоптимизируйте его сначала.")
            return
        if not original_name.lower().endswith(".svn"):
            await message.reply_text("Для оптимизации нужен .svn-файл.")
            return
    elif mode == "opti_deoptimize":
        if not original_name.lower().endswith(".svnz"):
            await message.reply_text("Для деоптимизации нужен .svnz-файл.")
            return

    size_kb = file_size // 1024 if file_size else 0
    now = kyiv_now().strftime("%d.%m.%Y %H:%M:%S")

    if mode == "video":
        mode_label = "ВИДЕО"
    elif mode == "photo":
        mode_label = "ФОТО"
    elif mode == "mini":
        mode_label = "MINI"
    elif mode == "opti_optimize":
        mode_label = "OPTI"
    else:
        mode_label = "DEOPTI"

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

    if unlimited:
        remaining_line = "Безлимит"
    else:
        remaining_line = f"Осталось попыток: {remaining - 1}"

    await send_log(
        context,
        f"Новый файл ({mode_label})\n"
        f"@{username} (ID: {uid})\n"
        f"Имя: {full_name}\n"
        f"Файл: {original_name}\n"
        f"Размер: {size_kb} KB\n"
        f"{remaining_line}\n"
        f"{now}"
    )

    os.makedirs("./tmp", exist_ok=True)
    input_path = f"./tmp/{original_name}"
    await file_obj.download_to_drive(input_path)

    if mode in ("opti_optimize", "opti_deoptimize"):
        action = "compress" if mode == "opti_optimize" else "decompress"
        if action == "compress":
            output_path = f"./tmp/opti_{os.path.splitext(os.path.basename(input_path))[0]}.svnz"
        else:
            output_path = f"./tmp/opti_{os.path.splitext(os.path.basename(input_path))[0]}.svn"

        try:
            subprocess.run(
                ["python", SCRIPT_OPTI, action, input_path, output_path],
                capture_output=True, text=True, check=True
            )
            if action == "compress":
                new_name = f"{os.path.splitext(original_name)[0]}.svnz"
            else:
                new_name = f"{os.path.splitext(original_name)[0]}.svn"

            await message.reply_document(document=open(output_path, "rb"), filename=new_name)

            if not unlimited:
                add_usage(uid, OPTI_LOG)
                _, remaining_after = check_limit(uid, OPTI_LOG, OPTI_LIMIT_PER_DAY)
            else:
                remaining_after = None

            log_event(f"SUCCESS ({mode_label}): {uid} @{username} -> {new_name}")
            after_line = "Безлимит" if remaining_after is None else f"Осталось попыток: {remaining_after}"

            await send_log(
                context,
                f"Готово ({mode_label})\n"
                f"@{username} (ID: {uid})\n"
                f"Отдано: {new_name}\n"
                f"{after_line}\n"
                f"{kyiv_now().strftime('%d.%m.%Y %H:%M:%S')}"
            )
            context.user_data["waiting"] = False
        except subprocess.CalledProcessError as e:
            await message.reply_text(f"Ошибка Opti-save: {e.stderr[:300]}")
            await send_log(context, f"Ошибка Opti-save у {uid}: {e.stderr[:150]}")
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
        return

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

    if mode == "photo":
        script = SCRIPT_PHOTO
        prefix = "photo"
    elif mode == "mini":
        script = SCRIPT_MINI
        prefix = "mini"
    else:
        script = SCRIPT_VIDEO
        prefix = "map"

    try:
        subprocess.run(
            ["python", script, input_path, output_path],
            capture_output=True, text=True, check=True
        )
        new_name = f"{prefix}{random.randint(100000, 999999)}.svn"
        await message.reply_document(document=open(output_path, "rb"), filename=new_name)

        if not unlimited:
            add_usage(uid, USAGE_LOG)
            _, remaining_after = check_limit(uid, USAGE_LOG, LIMIT_PER_DAY)
        else:
            remaining_after = None

        log_event(f"SUCCESS ({mode_label}): {uid} @{username} -> {new_name}")
        after_line = "Безлимит" if remaining_after is None else f"Осталось попыток: {remaining_after}"

        await send_log(
            context,
            f"Сконвертировано ({mode_label})\n"
            f"@{username} (ID: {uid})\n"
            f"Отдано: {new_name}\n"
            f"{after_line}\n"
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
    application.add_handler(CommandHandler("unlimited", unlimited_cmd))
    application.add_handler(CommandHandler("limited", limited_cmd))
    application.add_handler(CommandHandler("list_unlimited", list_unlimited))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.VIDEO | filters.ANIMATION | filters.Document.ALL, handle_media))
    application.run_polling()

main()
