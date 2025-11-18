import logging
import os
import asyncio
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext
from telegram.error import BadRequest, NetworkError, TimedOut

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# دریافت چند ادمین به صورت لیست از ENV
ADMIN_USER_IDS = os.getenv("ADMIN_USER_IDS", "").split(",")
ADMIN_USER_IDS = [int(i.strip()) for i in ADMIN_USER_IDS if i.strip().isdigit()]

def is_admin(user_id: int) -> bool:
    """بررسی کند که آیا کاربر جزو مدیرهاست یا نه"""
    return user_id in ADMIN_USER_IDS


TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN در تنظیمات محیطی پیدا نشد!")

app = Application.builder().token(TOKEN).build()

CONFIG_FILE = "config.json"
MEDIA_MAP_FILE = "media_map.json"


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return default
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

config = load_json(CONFIG_FILE, {})
media_map = load_json(MEDIA_MAP_FILE, {})


async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    await update.message.reply_text(
        f"سلام {user.first_name}! 😄\n"
        f"من ربات آماده‌به‌کار هستم."
    )


async def add_channel(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        return await update.message.reply_text("⛔ شما مدیر نیستید!")

    if len(context.args) != 2:
        return await update.message.reply_text("❗ استفاده صحیح:\n/addchannel name @channelusername")

    name, channel = context.args

    config[name] = channel
    save_json(CONFIG_FILE, config)

    await update.message.reply_text(f"✔ کانال {channel} با نام {name} ذخیره شد.")


async def add_media(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        return await update.message.reply_text("⛔ شما مدیر نیستید!")

    if update.message.reply_to_message is None:
        return await update.message.reply_text("❗ باید روی یک پیام که عکس یا ویدیو دارد ریپلای کنید!")

    if len(context.args) != 1:
        return await update.message.reply_text("❗ استفاده:\n/addmedia name")

    name = context.args[0]
    msg = update.message.reply_to_message

    if msg.photo:
        file_id = msg.photo[-1].file_id
        media_type = "photo"
    elif msg.video:
        file_id = msg.video.file_id
        media_type = "video"
    else:
        return await update.message.reply_text("❗ فقط عکس یا ویدیو پشتیبانی می‌شود!")

    media_map[name] = {"type": media_type, "file_id": file_id}
    save_json(MEDIA_MAP_FILE, media_map)

    await update.message.reply_text(f"✔ مدیا ذخیره شد با نام {name}")


async def send_media(update: Update, context: CallbackContext):
    if len(context.args) != 2:
        return await update.message.reply_text("❗ استفاده:\n/send medianame channelname")

    medianame, channelname = context.args

    if channelname not in config:
        return await update.message.reply_text("❌ چنین کانالی ثبت نشده.")

    if medianame not in media_map:
        return await update.message.reply_text("❌ چنین مدیایی ثبت نشده.")

    channel_id = config[channelname]
    info = media_map[medianame]

    try:
        if info["type"] == "photo":
            await context.bot.send_photo(chat_id=channel_id, photo=info["file_id"])
        else:
            await context.bot.send_video(chat_id=channel_id, video=info["file_id"])

        await update.message.reply_text("✔ ارسال شد.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا: {e}")


app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("addchannel", add_channel))
app.add_handler(CommandHandler("addmedia", add_media))
app.add_handler(CommandHandler("send", send_media))


if __name__ == "__main__":
    print("🤖 Bot Started...")
    app.run_polling()
