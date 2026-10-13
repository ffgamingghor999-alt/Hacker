import asyncio
import json
import logging
import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from config import BOT_TOKEN, OWNER_ID, PHOTO_DIRS, VIDEO_DIRS, FILE_DIRS, MAX_FILE_MB, MAX_FILES_PER_REQUEST

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"
LOG_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

logging.basicConfig(filename=LOG_DIR / "bot.log", level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("personal_device_bot")

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm"}
FILE_EXTS = {".pdf", ".txt", ".zip", ".docx", ".xlsx", ".csv", ".json"}
MAX_BYTES = MAX_FILE_MB * 1024 * 1024
USERS_DB = DATA_DIR / "users.json"
ACTIVITY_DB = DATA_DIR / "activity.json"


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        logger.exception("Could not read %s", path)
        return default


def save_json(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def record_user(update: Update, action="message"):
    user = update.effective_user
    if not user:
        return
    now = datetime.now(timezone.utc).isoformat()
    users = load_json(USERS_DB, {})
    uid = str(user.id)
    item = users.get(uid, {"id": user.id, "name": user.full_name, "username": user.username,
                           "first_seen": now, "last_seen": now, "actions": 0})
    item.update({"name": user.full_name, "username": user.username, "last_seen": now,
                 "actions": int(item.get("actions", 0)) + 1})
    users[uid] = item
    save_json(USERS_DB, users)
    activity = load_json(ACTIVITY_DB, [])
    activity.append({"time": now, "user_id": user.id, "name": user.full_name,
                     "username": user.username, "action": action})
    save_json(ACTIVITY_DB, activity[-1000:])


def owner_only(update: Update):
    return bool(update.effective_user and update.effective_user.id == OWNER_ID)


async def deny(update):
    if update.callback_query:
        await update.callback_query.answer("Access denied.", show_alert=True)
        if update.callback_query.message:
            await update.callback_query.message.reply_text("❌ Access denied.")
    elif update.effective_message:
        await update.effective_message.reply_text("❌ Access denied.")


def menu():
    return ReplyKeyboardMarkup([["📸 Photos", "🎥 Videos"], ["📱 Device Info", "🔋 Battery"],
                                ["🌐 Network", "📦 Apps"], ["📁 Files", "📋 File List"],
                                ["ℹ️ Help"]], resize_keyboard=True, is_persistent=True)


def back():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu")]])


def existing_dirs(items):
    return [Path(os.path.expanduser(x)) for x in items if Path(os.path.expanduser(x)).is_dir()]


def find_files(directories, extensions):
    found, seen = [], set()
    for directory in existing_dirs(directories):
        try:
            for p in directory.rglob("*"):
                if p.is_file() and p.suffix.lower() in extensions:
                    try: key = str(p.resolve())
                    except OSError: key = str(p)
                    if key not in seen:
                        seen.add(key); found.append(p)
        except (OSError, PermissionError):
            logger.exception("Could not scan %s", directory)
    return sorted(found, key=lambda p: str(p).lower())


def human_size(n):
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB": return f"{size:.2f} {unit}"
        size /= 1024


def file_summary():
    groups = [("📸 Photos", find_files(PHOTO_DIRS, PHOTO_EXTS)),
              ("🎥 Videos", find_files(VIDEO_DIRS, VIDEO_EXTS)),
              ("📁 Files", find_files(FILE_DIRS, FILE_EXTS))]
    lines = ["📋 File List", ""]
    for title, arr in groups:
        lines.append(f"{title}: {len(arr)} files")
    for title, arr in groups:
        if arr:
            lines += ["", title]
            lines += [f"• {p.name}" for p in arr[:100]]
            if len(arr) > 100: lines.append(f"… and {len(arr)-100} more")
    return "\n".join(lines)


async def start(update, context):
    if not owner_only(update): return await deny(update)
    record_user(update, "/start")
    await update.effective_message.reply_text("👋 Personal Device Utility v3\n\nChoose an option:", reply_markup=menu())


async def help_cmd(update, context):
    if not owner_only(update): return await deny(update)
    record_user(update, "/help")
    await update.effective_message.reply_text(
        "ℹ️ Help\n\n📸 Photos / 🎥 Videos / 📁 Files — configured shared folders only\n"
        "📱 Device Info — runtime/storage information\n🔋 Battery — Termux:API when available\n"
        "🌐 Network — basic Wi-Fi info when available\n📦 Apps — packages visible to Termux\n"
        "📋 File List — counts and filenames\n\n🔐 Owner-only access. No private chat extraction, credential theft, or permission bypass.\n"
        "Storage permission: termux-setup-storage", reply_markup=menu())


async def device_info(update, context):
    if not owner_only(update): return await deny(update)
    record_user(update, "/info")
    total, used, free = shutil.disk_usage(BASE_DIR)
    await update.effective_message.reply_text(
        "📱 Device Info\n\nArchitecture: %s\nOS: %s %s\nPython: %s\nTime: %s\nStorage total: %s\nStorage used: %s\nStorage free: %s" %
        (platform.machine(), platform.system(), platform.release(), platform.python_version(),
         datetime.now().astimezone().isoformat(timespec="seconds"), human_size(total), human_size(used), human_size(free)),
        reply_markup=back())


def termux(command):
    try:
        p = subprocess.run(command, capture_output=True, text=True, timeout=10)
        return p.returncode, p.stdout.strip()
    except Exception as e:
        return 1, str(e)


async def battery(update, context):
    if not owner_only(update): return await deny(update)
    record_user(update, "/battery")
    code, out = await asyncio.to_thread(termux, ["termux-battery-status"])
    if code != 0 or not out: text = "🔋 Termux:API is unavailable."
    else:
        try:
            d = json.loads(out)
            text = "🔋 Battery\n\nPercentage: %s%%\nStatus: %s\nHealth: %s\nTemperature: %s °C" % (d.get("percentage", "N/A"), d.get("status", "N/A"), d.get("health", "N/A"), d.get("temperature", "N/A"))
        except Exception: text = "🔋 Battery data could not be parsed."
    await update.effective_message.reply_text(text, reply_markup=back())


async def network(update, context):
    if not owner_only(update): return await deny(update)
    record_user(update, "/network")
    code, out = await asyncio.to_thread(termux, ["termux-wifi-connectioninfo"])
    if code != 0 or not out: text = "🌐 Wi-Fi information is unavailable."
    else:
        try:
            d = json.loads(out)
            text = "🌐 Network\n\nSSID: %s\nIP: %s\nLink speed: %s" % (d.get("ssid", "N/A"), d.get("ip", "N/A"), d.get("link_speed_mbps", d.get("link_speed", "N/A")))
        except Exception: text = "🌐 Network data could not be parsed."
    await update.effective_message.reply_text(text, reply_markup=back())


async def apps(update, context):
    if not owner_only(update): return await deny(update)
    record_user(update, "/apps")
    code, out = await asyncio.to_thread(termux, ["pm", "list", "packages"])
    if code != 0 or not out: text = "📦 Apps\n\nPackage information is unavailable."
    else:
        packages = sorted({line.split("package:",1)[1].strip() for line in out.splitlines() if line.startswith("package:")})
        text = "📦 Apps\n\n" + ("\n".join("• "+p for p in packages[:150]) or "No visible packages.")
        if len(packages) > 150: text += f"\n\n… and {len(packages)-150} more."
    await update.effective_message.reply_text(text, reply_markup=back())


async def send_group(update, dirs, exts, title, mode):
    if not owner_only(update): return await deny(update)
    record_user(update, title)
    msg = update.effective_message
    items = find_files(dirs, exts)
    eligible = []
    skipped_large = 0
    for p in items:
        try:
            if p.stat().st_size <= MAX_BYTES: eligible.append(p)
            else: skipped_large += 1
        except OSError: pass
    eligible = eligible[:MAX_FILES_PER_REQUEST]
    if not eligible:
        await msg.reply_text(f"{title}\n\nNo permitted files under the configured size limit ({MAX_FILE_MB} MB).", reply_markup=back())
        return
    await msg.reply_text(f"{title}\n\nSending {len(eligible)} file(s)…")
    sent = failed = 0
    for p in eligible:
        try:
            await msg.chat.send_action(ChatAction.UPLOAD_DOCUMENT)
            with p.open("rb") as f:
                caption = p.name[:1024]
                if mode == "photo":
                    try: await msg.chat.send_photo(f, caption=caption)
                    except TelegramError:
                        f.seek(0); await msg.chat.send_document(f, caption=caption)
                elif mode == "video":
                    try: await msg.chat.send_video(f, caption=caption, supports_streaming=True)
                    except TelegramError:
                        f.seek(0); await msg.chat.send_document(f, caption=caption)
                else: await msg.chat.send_document(f, caption=caption)
            sent += 1
        except (OSError, TelegramError):
            failed += 1; logger.exception("Send failed: %s", p)
    extra = f"\nSkipped over {MAX_FILE_MB} MB: {skipped_large}" if skipped_large else ""
    await msg.reply_text(f"✅ Completed\n\nSuccessfully sent: {sent}\nFailed: {failed}{extra}", reply_markup=back())


async def photos(update, context): return await send_group(update, PHOTO_DIRS, PHOTO_EXTS, "📸 Photos", "photo")
async def videos(update, context): return await send_group(update, VIDEO_DIRS, VIDEO_EXTS, "🎥 Videos", "video")
async def files(update, context): return await send_group(update, FILE_DIRS, FILE_EXTS, "📁 Files", "file")


async def file_list(update, context):
    if not owner_only(update): return await deny(update)
    record_user(update, "/list")
    await update.effective_message.reply_text(file_summary(), reply_markup=back())


async def status(update, context):
    if not owner_only(update): return await deny(update)
    record_user(update, "/status")
    await update.effective_message.reply_text("🟢 Bot Status\n\nRunning normally.\nPython: %s\nTime: %s" % (platform.python_version(), datetime.now().astimezone().isoformat(timespec="seconds")), reply_markup=menu())


async def ping(update, context):
    if not owner_only(update): return await deny(update)
    record_user(update, "/ping")
    await update.effective_message.reply_text("🏓 Pong — bot is online.", reply_markup=menu())


async def callback_menu(update, context):
    if not owner_only(update): return await deny(update)
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("🏠 Main Menu", reply_markup=menu())


async def text_router(update, context):
    if not owner_only(update): return await deny(update)
    routes = {"📸 Photos": photos, "🎥 Videos": videos, "📱 Device Info": device_info, "🔋 Battery": battery,
              "🌐 Network": network, "📦 Apps": apps, "📁 Files": files, "📋 File List": file_list, "ℹ️ Help": help_cmd}
    fn = routes.get((update.effective_message.text or "").strip())
    if fn: await fn(update, context)


async def post_init(app):
    await app.bot.set_my_commands([BotCommand("start","Open main menu"), BotCommand("menu","Open main menu"), BotCommand("help","Help and privacy"),
        BotCommand("info","Device information"), BotCommand("battery","Battery status"), BotCommand("network","Basic network info"),
        BotCommand("apps","Visible package list"), BotCommand("photos","Send permitted photos"), BotCommand("videos","Send permitted videos"),
        BotCommand("files","Send permitted files"), BotCommand("list","List files"), BotCommand("status","Bot status"), BotCommand("ping","Check bot")])


def validate():
    if not BOT_TOKEN or BOT_TOKEN in {"PASTE_NEW_BOT_TOKEN_HERE", ""}: raise RuntimeError("Set BOT_TOKEN environment variable")
    if not isinstance(OWNER_ID, int) or OWNER_ID <= 0: raise RuntimeError("Set OWNER_ID environment variable")
    if MAX_FILE_MB <= 0 or MAX_FILES_PER_REQUEST <= 0: raise RuntimeError("File limits must be positive")


def build():
    validate()
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    for command, fn in [("start",start),("menu",start),("help",help_cmd),("info",device_info),("battery",battery),("network",network),("apps",apps),("photos",photos),("videos",videos),("files",files),("list",file_list),("status",status),("ping",ping)]:
        app.add_handler(CommandHandler(command, fn))
    app.add_handler(CallbackQueryHandler(callback_menu, pattern="^menu$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    return app


if __name__ == "__main__":
    print("Starting Telegram Personal Device Utility v3…")
    build().run_polling(drop_pending_updates=True)
