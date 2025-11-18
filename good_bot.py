import logging
import os
import asyncio
import json
import base64
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext
from telegram.error import BadRequest, NetworkError, TimedOut
# برای Render (جلوگیری از timeout)
import threading
import http.server
import socketserver
import time
import requests

def keep_alive():
    PORT = int(os.environ.get('PORT', 10000))
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()

def auto_ping():
    url = "https://good-bot-v5lz.onrender.com"  # آدرس Render خودت
    while True:
        try:
            requests.get(url)
            print("🔁 Ping sent successfully.")
        except Exception as e:
            print("Ping failed:", e)
        time.sleep(180)  # هر 3 دقیقه یکبار پینگ

threading.Thread(target=keep_alive, daemon=True).start()
threading.Thread(target=auto_ping, daemon=True).start()

# فعال‌سازی لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TOKEN")
# تغییر: پشتیبانی از چندین مدیر
ADMIN_USER_IDS = [int(id) for id in os.getenv("ADMIN_USER_IDS", "0").split(",")]
# برای سازگاری با کد قبلی
ADMIN_USER_ID = ADMIN_USER_IDS[0] if ADMIN_USER_IDS else 0
# تغییر: تعریف ابر مدیر (فقط شما می‌توانید مدیران را حذف کنید)
SUPER_ADMIN_ID = 6196578711

# GitHub settings (set these environment variables)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # باید با دسترسی repo:contents ساخته شود
GITHUB_OWNER = os.getenv("GITHUB_OWNER", "ame1387112-cloud")
GITHUB_REPO = os.getenv("GITHUB_REPO", "ame")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")

# نام فایل‌های پیکربندی 
CONFIG_FILE = 'config.json'
MEDIA_MAP_FILE = 'media_map.json'

# --- GitHub helper functions ---
def github_update_file(path: str, content_str: str, commit_message: str) -> bool:
    """
    آپدیت یا ایجاد فایل در مخزن گیت‌هاب. برمی‌گرداند True در صورت موفقیت.
    این تابع هم‌زمان (synchronous) است و در یک thread جدا اجرا می‌شود تا هندلرهای async را مسدود نکند.
    """
    if not GITHUB_TOKEN:
        logger.warning("GITHUB_TOKEN not set; skipping GitHub update for %s", path)
        return False
    api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    # get current file sha (اگر وجود داشته باشد)
    try:
        r = requests.get(api_url, params={"ref": GITHUB_BRANCH}, headers=headers, timeout=15)
    except Exception as e:
        logger.error("Failed to GET %s from GitHub: %s", api_url, e)
        return False

    if r.status_code == 200:
        sha = r.json().get("sha")
    elif r.status_code == 404:
        sha = None
    else:
        logger.error("Unexpected status getting %s: %s %s", api_url, r.status_code, r.text)
        return False

    payload = {
        "message": commit_message,
        "content": base64.b64encode(content_str.encode('utf-8')).decode('utf-8'),
        "branch": GITHUB_BRANCH
    }
    if sha:
        payload["sha"] = sha

    try:
        put = requests.put(api_url, json=payload, headers=headers, timeout=20)
    except Exception as e:
        logger.error("Failed to PUT %s to GitHub: %s", api_url, e)
        return False

    if put.status_code in (200, 201):
        logger.info("✅ Updated %s on GitHub (%s).", path, put.status_code)
        return True
    else:
        logger.error("❌ Failed to update %s on GitHub: %s %s", path, put.status_code, put.text)
        return False

def github_update_file_background(path: str, content_str: str, commit_message: str) -> bool:
    """
    انتشارات به گیت‌هاب در یک ترد جدا تا بلوک نشود.
    این نسخه بهبود یافته یک مقدار بازگشتی دارد که نشان می‌دهد آیا عملیات موفقیت‌آمیز بوده است یا خیر.
    """
    result = threading.Event()
    result_container = {'success': False}
    
    def update_task():
        result_container['success'] = github_update_file(path, content_str, commit_message)
        result.set()
    
    threading.Thread(target=update_task, daemon=True).start()
    result.wait(timeout=30)  # منتظر می‌مانیم تا حداکثر ۳۰ ثانیه عملیات تمام شود
    return result_container['success']

# بارگذاری تنظیمات از فایل
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    # اگر فایل وجود نداشت، یک تنظیمات پیش‌فرض می‌سازیم
    default_config = {
        "required_channels": [
            {"id": "@aeah1am", "name": "کانال اول"},
            {"id": "@VelvetWhisper_AY", "name": "کانال دوم"}
        ],
        "payment_contact_id": "@uhftgrt",
        "source_channel_id": -1003251983791,
        # تغییر: اضافه کردن لیست مدیران به کانفیگ
        "admin_ids": [SUPER_ADMIN_ID, 8068113172]  # شما و مدیر جدید
    }
    save_config(default_config)
    return default_config

# ذخیره تنظیمات در فایل
def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)
    # ارسال به گیت‌هاب در پس‌زمینه
    try:
        json_text = json.dumps(config, ensure_ascii=False, indent=4)
        success = github_update_file_background(CONFIG_FILE, json_text, "Update config.json via bot")
        if success:
            logger.info("✅ Configuration successfully synced to GitHub")
        else:
            logger.warning("⚠️ Failed to sync configuration to GitHub")
        return success
    except Exception as e:
        logger.warning("Could not push config to GitHub in background: %s", e)
        return False

# بارگذاری نقشه رسانه‌ها از فایل
def load_media_map():
    if os.path.exists(MEDIA_MAP_FILE):
        with open(MEDIA_MAP_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    default_map = {
        "1": [33, 34, 35, 36, 37, 38, 39, 40, 41, 42],
        "2": [43, 44, 45, 46, 47, 48, 49],
        "3": [50, 51, 52, 53, 54, 55],
        "4": [56],
        "5": [58],
        "6": [59],
        "7": [61, 62, 63],
    }
    save_media_map(default_map)
    return default_map

# ذخیره نقشه رسانه‌ها در فایل
def save_media_map(media_map):
    with open(MEDIA_MAP_FILE, 'w', encoding='utf-8') as f:
        json.dump(media_map, f, ensure_ascii=False, indent=4)
    # ارسال به گیت‌هاب در پس‌زمینه
    try:
        json_text = json.dumps(media_map, ensure_ascii=False, indent=4)
        success = github_update_file_background(MEDIA_MAP_FILE, json_text, "Update media_map.json via bot")
        if success:
            logger.info("✅ Media map successfully synced to GitHub")
        else:
            logger.warning("⚠️ Failed to sync media map to GitHub")
        return success
    except Exception as e:
        logger.warning("Could not push media_map to GitHub in background: %s", e)
        return False

# بارگذاری اولیه تنظیمات و رسانه‌ها
CONFIG = load_config()
MEDIA_MAP = load_media_map()

# تغییر: تابع بررسی دسترسی مدیر
def is_admin(user_id):
    # اگر در کانفیگ مدیران تعریف شده باشند، از آن استفاده کن
    if 'admin_ids' in CONFIG:
        return user_id in CONFIG['admin_ids']
    # در غیر این صورت از متغیر محیطی استفاده کن
    return user_id in ADMIN_USER_IDS

# تغییر: تابع بررسی دسترسی ابر مدیر (فقط برای حذف مدیر)
def is_super_admin(user_id):
    return user_id == SUPER_ADMIN_ID

# --- شروع بخش جدید: دستورات مدیریتی برای کانال‌ها ---
async def add_channel_command(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("این دستور فقط برای مدیر مجاز است.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("مثال: /addchannel @newchannel نام_کانال_جدید")
        return

    channel_id = context.args[0]
    channel_name = " ".join(context.args[1:])

    # جلوگیری از تکرار
    if any(ch['id'] == channel_id for ch in CONFIG['required_channels']):
        await update.message.reply_text("این کانال از قبل در لیست وجود دارد.")
        return

    CONFIG['required_channels'].append({"id": channel_id, "name": channel_name})
    
    # ذخیره محلی و ارسال به گیت‌هاب
    saved_locally = True  # همیشه ذخیره محلی موفق است
    github_success = save_config(CONFIG)
    
    if saved_locally and github_success:
        await update.message.reply_text(f"✅ کانال '{channel_name}' با موفقیت اضافه شد و در گیت‌هاب ذخیره گردید.")
    elif saved_locally:
        await update.message.reply_text(f"✅ کانال '{channel_name}' با موفقیت اضافه شد اما در گیت‌هاب ذخیره نشد. لطفاً تنظیمات گیت‌هاب را بررسی کنید.")
    else:
        await update.message.reply_text(f"❌ خطا در ذخیره کانال '{channel_name}'.")
    
    logger.info(f"Admin added channel: {channel_id} ({channel_name})")

async def list_channels_command(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("این دستور فقط برای مدیر مجاز است.")
        return

    if not CONFIG['required_channels']:
        await update.message.reply_text("هیچ کانال اجباری تعریف نشده است.")
        return

    response_text = "📋 لیست کانال‌های اجباری:\n\n"
    for ch in CONFIG['required_channels']:
        response_text += f"• **{ch['name']}** (`{ch['id']}`)\n"

    await update.message.reply_text(response_text, parse_mode='Markdown')

async def remove_channel_command(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("این دستور فقط برای مدیر مجاز است.")
        return
    if not context.args:
        await update.message.reply_text("مثال: /removechannel @newchannel")
        return

    channel_id_to_remove = context.args[0]
    original_length = len(CONFIG['required_channels'])
    CONFIG['required_channels'] = [ch for ch in CONFIG['required_channels'] if ch['id'] != channel_id_to_remove]

    if len(CONFIG['required_channels']) < original_length:
        # ذخیره محلی و ارسال به گیت‌هاب
        saved_locally = True  # همیشه ذخیره محلی موفق است
        github_success = save_config(CONFIG)
        
        if saved_locally and github_success:
            await update.message.reply_text(f"✅ کانال '{channel_id_to_remove}' با موفقیت حذف شد و در گیت‌هاب ذخیره گردید.")
        elif saved_locally:
            await update.message.reply_text(f"✅ کانال '{channel_id_to_remove}' با موفقیت حذف شد اما در گیت‌هاب ذخیره نشد. لطفاً تنظیمات گیت‌هاب را بررسی کنید.")
        else:
            await update.message.reply_text(f"❌ خطا در حذف کانال '{channel_id_to_remove}'.")
            
        logger.info(f"Admin removed channel: {channel_id_to_remove}")
    else:
        await update.message.reply_text(f"کانال '{channel_id_to_remove}' در لیست یافت نشد.")
# --- پایان بخش جدید ---


# --- شروع بخش جدید: دستورات مدیریتی برای رسانه ---
async def add_media_command(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("این دستور فقط برای مدیر مجاز است.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("مثال: /addmedia مجموعه_جدید 25 26 27")
        return
    keyword = context.args[0]
    try:
        message_ids = list(map(int, context.args[1:]))
        MEDIA_MAP[keyword] = message_ids
        
        # ذخیره محلی و ارسال به گیت‌هاب
        saved_locally = True  # همیشه ذخیره محلی موفق است
        github_success = save_media_map(MEDIA_MAP)
        
        if saved_locally and github_success:
            await update.message.reply_text(f"✅ کلمه کلیدی '{keyword}' با {len(message_ids)} آیدی با موفقیت آپدیت شد و در گیت‌هاب ذخیره گردید.")
        elif saved_locally:
            await update.message.reply_text(f"✅ کلمه کلیدی '{keyword}' با {len(message_ids)} آیدی با موفقیت آپدیت شد اما در گیت‌هاب ذخیره نشد. لطفاً تنظیمات گیت‌هاب را بررسی کنید.")
        else:
            await update.message.reply_text(f"❌ خطا در آپدیت کلمه کلیدی '{keyword}'.")
            
        logger.info(f"Admin updated keyword '{keyword}' with IDs: {message_ids}")
    except ValueError:
        await update.message.reply_text("خطا: تمام آیدی‌ها باید عدد باشند. مثال: /addmedia مجموعه_جدید 25 26 27")

async def list_media_command(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("این دستور فقط برای مدیر مجاز است.")
        return
    if not MEDIA_MAP:
        await update.message.reply_text("هیچ رسانه‌ای تعریف نشده است.")
        return
    response_text = "📋 لیست رسانه‌های فعلی:\n\n"
    for keyword, ids in MEDIA_MAP.items():
        response_text += f"• `{keyword}`: {len(ids)} آیدی\n"
    await update.message.reply_text(response_text, parse_mode='Markdown')

async def delete_media_command(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("این دستور فقط برای مدیر مجاز است.")
        return
    if not context.args:
        await update.message.reply_text("مثال: /deletemedia مجموعه")
        return
    keyword = context.args[0]
    if keyword in MEDIA_MAP:
        del MEDIA_MAP[keyword]
        
        # ذخیره محلی و ارسال به گیت‌هاب
        saved_locally = True  # همیشه ذخیره محلی موفق است
        github_success = save_media_map(MEDIA_MAP)
        
        if saved_locally and github_success:
            await update.message.reply_text(f"✅ کلمه کلیدی '{keyword}' با موفقیت حذف شد و در گیت‌هاب ذخیره گردید.")
        elif saved_locally:
            await update.message.reply_text(f"✅ کلمه کلیدی '{keyword}' با موفقیت حذف شد اما در گیت‌هاب ذخیره نشد. لطفاً تنظیمات گیت‌هاب را بررسی کنید.")
        else:
            await update.message.reply_text(f"❌ خطا در حذف کلمه کلیدی '{keyword}'.")
            
        logger.info(f"Admin deleted keyword '{keyword}'.")
    else:
        await update.message.reply_text(f"کلمه کلیدی '{keyword}' یافت نشد.")
# --- پایان بخش جدید ---

# دستور جدید برای بررسی وضعیت همگام‌سازی با گیت‌هاب
async def sync_status_command(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("این دستور فقط برای مدیر مجاز است.")
        return
    
    if not GITHUB_TOKEN:
        await update.message.reply_text("⚠️ توکن گیت‌هاب تنظیم نشده است. همگام‌سازی با گیت‌هاب غیرفعال است.")
        return
    
    await update.message.reply_text("🔄 در حال بررسی وضعیت همگام‌سازی با گیت‌هاب...")
    
    # بررسی وضعیت فایل کانفیگ
    config_api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{CONFIG_FILE}"
    media_api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{MEDIA_MAP_FILE}"
    
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        # بررسی فایل کانفیگ
        config_response = requests.get(config_api_url, params={"ref": GITHUB_BRANCH}, headers=headers, timeout=15)
        media_response = requests.get(media_api_url, params={"ref": GITHUB_BRANCH}, headers=headers, timeout=15)
        
        status_text = "📊 وضعیت همگام‌سازی با گیت‌هاب:\n\n"
        
        if config_response.status_code == 200:
            config_data = json.loads(base64.b64decode(config_response.json()['content']).decode('utf-8'))
            if json.dumps(config_data, sort_keys=True) == json.dumps(CONFIG, sort_keys=True):
                status_text += "✅ فایل config.json همگام است.\n"
            else:
                status_text += "⚠️ فایل config.json با نسخه محلی متفاوت است.\n"
        else:
            status_text += "❌ فایل config.json در گیت‌هاب یافت نشد.\n"
        
        if media_response.status_code == 200:
            media_data = json.loads(base64.b64decode(media_response.json()['content']).decode('utf-8'))
            if json.dumps(media_data, sort_keys=True) == json.dumps(MEDIA_MAP, sort_keys=True):
                status_text += "✅ فایل media_map.json همگام است.\n"
            else:
                status_text += "⚠️ فایل media_map.json با نسخه محلی متفاوت است.\n"
        else:
            status_text += "❌ فایل media_map.json در گیت‌هاب یافت نشد.\n"
        
        # اضافه کردن اطلاعات مدیران
        if 'admin_ids' in CONFIG:
            status_text += f"\n👥 تعداد مدیران: {len(CONFIG['admin_ids'])} نفر"
        
        await update.message.reply_text(status_text)
        
    except Exception as e:
        logger.error(f"Error checking sync status: {e}")
        await update.message.reply_text(f"❌ خطا در بررسی وضعیت همگام‌سازی: {str(e)}")

# تغییر: دستور جدید برای مدیریت مدیران
async def add_admin_command(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("این دستور فقط برای مدیر مجاز است.")
        return
    if not context.args:
        await update.message.reply_text("مثال: /addadmin 123456789")
        return
    
    try:
        new_admin_id = int(context.args[0])
        if 'admin_ids' not in CONFIG:
            CONFIG['admin_ids'] = ADMIN_USER_IDS
        
        if new_admin_id in CONFIG['admin_ids']:
            await update.message.reply_text("این کاربر از قبل مدیر است.")
            return
        
        CONFIG['admin_ids'].append(new_admin_id)
        saved_locally = True
        github_success = save_config(CONFIG)
        
        if saved_locally and github_success:
            await update.message.reply_text(
                f"✅ کاربر با آیدی {new_admin_id} با موفقیت به لیست مدیران اضافه شد.\n"
                f"📁 این تغییر در گیت‌هاب نیز ذخیره گردید."
            )
        elif saved_locally:
            await update.message.reply_text(
                f"✅ کاربر با آیدی {new_admin_id} با موفقیت به لیست مدیران اضافه شد.\n"
                f"⚠️ اما در گیت‌هاب ذخیره نشد. لطفاً تنظیمات گیت‌هاب را بررسی کنید."
            )
        else:
            await update.message.reply_text(f"❌ خطا در افزودن مدیر جدید.")
            
        logger.info(f"Admin added new admin: {new_admin_id}")
    except ValueError:
        await update.message.reply_text("خطا: آیدی باید عدد باشد. مثال: /addadmin 123456789")

async def remove_admin_command(update: Update, context: CallbackContext) -> None:
    # تغییر: فقط ابر مدیر می‌تواند مدیران را حذف کند
    if not is_super_admin(update.effective_user.id):
        await update.message.reply_text("⚠️ فقط مدیر اصلی می‌تواند مدیران را حذف کند.")
        return
    if not context.args:
        await update.message.reply_text("مثال: /removeadmin 123456789")
        return
    
    try:
        admin_id_to_remove = int(context.args[0])
        if 'admin_ids' not in CONFIG:
            await update.message.reply_text("هیچ لیست مدیرانی در تنظیمات یافت نشد.")
            return
        
        if admin_id_to_remove not in CONFIG['admin_ids']:
            await update.message.reply_text("این کاربر در لیست مدیران یافت نشد.")
            return
        
        # جلوگیری از حذف آخرین مدیر
        if len(CONFIG['admin_ids']) <= 1:
            await update.message.reply_text("خطا: نمی‌توان آخرین مدیر را حذف کرد.")
            return
        
        CONFIG['admin_ids'].remove(admin_id_to_remove)
        saved_locally = True
        github_success = save_config(CONFIG)
        
        if saved_locally and github_success:
            await update.message.reply_text(
                f"✅ کاربر با آیدی {admin_id_to_remove} با موفقیت از لیست مدیران حذف شد.\n"
                f"📁 این تغییر در گیت‌هاب نیز ذخیره گردید."
            )
        elif saved_locally:
            await update.message.reply_text(
                f"✅ کاربر با آیدی {admin_id_to_remove} با موفقیت از لیست مدیران حذف شد.\n"
                f"⚠️ اما در گیت‌هاب ذخیره نشد. لطفاً تنظیمات گیت‌هاب را بررسی کنید."
            )
        else:
            await update.message.reply_text(f"❌ خطا در حذف مدیر.")
            
        logger.info(f"Super admin removed admin: {admin_id_to_remove}")
    except ValueError:
        await update.message.reply_text("خطا: آیدی باید عدد باشد. مثال: /removeadmin 123456789")

async def list_admins_command(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("این دستور فقط برای مدیر مجاز است.")
        return
    
    if 'admin_ids' not in CONFIG:
        await update.message.reply_text("هیچ لیست مدیرانی در تنظیمات یافت نشد.")
        return
    
    response_text = "📋 لیست مدیران ربات:\n\n"
    for admin_id in CONFIG['admin_ids']:
        if admin_id == SUPER_ADMIN_ID:
            response_text += f"• `{admin_id}` 👑 (مدیر اصلی)\n"
        else:
            response_text += f"• `{admin_id}`\n"
    
    response_text += "\n💡 نکته: لیست مدیران در گیت‌هاب ذخیره می‌شود و پس از ری‌استارت ربات باقی می‌ماند."
    
    await update.message.reply_text(response_text, parse_mode='Markdown')

# این تابع عضویت کاربر را در کانال‌های اجباری بررسی می‌کند
async def check_membership(context: CallbackContext, user_id: int) -> (bool, list):
    unchecked_channels = []
    is_member_of_checkable_channels = True
    # استفاده از لیست کانال‌ها از فایل کانفیگ
    for channel in CONFIG['required_channels']:
        channel_id = channel['id']
        channel_name = channel['name']
        channel_link = f"https://t.me/{channel_id.lstrip('@')}"
        try:
            logger.info(f"در حال بررسی عضویت کاربر {user_id} در {channel_name} ({channel_id})...")
            await context.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            logger.info(f"✅ کاربر {user_id} در {channel_name} عضو است.")
        except BadRequest as e:
            logger.warning(f"⚠️ نمی‌توان عضویت را در {channel_name} بررسی کرد. دلیل: {e.message}. (ربات احتمالاً مدیر نیست)")
            unchecked_channels.append((channel_name, channel_link))
        except (NetworkError, TimedOut) as e:
            logger.error(f"🔌 خطای شبکه در حین بررسی {channel_name}: {e}")
            is_member_of_checkable_channels = False
            return (False, [])
        except Exception as e:
            logger.error(f"⚠️ خطای پیش‌بینی نشده در بررسی {channel_name}: {e}")
            is_member_of_checkable_channels = False
            return (False, [])
    return (is_member_of_checkable_channels, unchecked_channels)


# این تابع پیام‌ها را پس از 60 ثانیه حذف کرده و یک پیام متنی جدید ارسال می‌کند
async def schedule_self_destruct(context: CallbackContext, chat_id: int, message_ids: list[int]):
    await asyncio.sleep(60)
    try:
        for message_id in message_ids:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        await context.bot.send_message(chat_id=chat_id, text="⏳ این محتوا پس از یک دقیقه خودکارسازی شد.")
        logger.info(f"Messages {message_ids} in chat {chat_id} were self-destructed.")
    except Exception as e:
        logger.warning(f"Could not self-destruct messages {message_ids} in chat {chat_id}: {e}")


# این تابع رسانه(ها) را ارسال کرده و سپس پیام تبلیغاتی VIP را می‌فرستد
async def send_media_by_keyword(update: Update, context: CallbackContext, keyword: str):
    message_ids = MEDIA_MAP.get(keyword)
    if not message_ids:
        await update.message.reply_text("رسانه‌ای برای این لینک پیدا نشد.")
        return
    logger.info(f"در حال کپی کردن {len(message_ids)} پیام از کانال ذخیره‌سازی برای کلمه کلیدی '{keyword}'")
    sent_message_ids = []
    try:
        for msg_id in message_ids:
            try:
                copied_message = await context.bot.copy_message(
                    chat_id=update.effective_chat.id,
                    from_chat_id=CONFIG['source_channel_id'],
                    message_id=msg_id
                )
                sent_message_ids.append(copied_message.message_id)
                logger.info(f"پیام با آیدی {msg_id} با موفقیت کپی شد. آیدی جدید: {copied_message.message_id}")
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Could not copy message {msg_id}: {e}")
        if sent_message_ids:
            asyncio.create_task(schedule_self_destruct(context, update.effective_chat.id, sent_message_ids))
            logger.info(f"زمان‌بندی خودکارسازی برای {len(sent_message_ids)} پیام فعال شد")
            await asyncio.sleep(2)
            await update.message.reply_text(
                "🔥 برای دسترسی به هزاران محتوای بیشتر و بدون محدودیت، عضو کانال VIP ما شوید!\n\n"
                "💰 هزینه اشتراک:یک بار برای همیشه\n\n"
                "👤 برای عضویت و اطلاعات بیشتر، به آیدی زیر پیام دهید:\n"
                f"**{CONFIG['payment_contact_id']}**",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("هیچ فایلی برای ارسال پیدا نشد.")
    except Exception as e:
        logger.error(f"Error sending media for keyword '{keyword}': {e}")
        await update.message.reply_text("متاسفانه در ارسال محتوا مشکلی پیش آمد.")


async def start(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    try:
        is_member, unchecked = await check_membership(context, user_id)
        if not is_member:
            await update.message.reply_text(
                "⚠️ برای استفاده از ربات، باید عضو کانال زیر باشید:\n\n"
                f"[{CONFIG['required_channels'][0]['name']}](https://t.me/{CONFIG['required_channels'][0]['id'].lstrip('@')})\n\n"
                "پس از عضویت، لطفاً دوباره تلاش کنید.",
                disable_web_page_preview=True,
                parse_mode='Markdown'
            )
            return
        if unchecked:
            keyboard = [[InlineKeyboardButton(f"➡️ عضویت در {name}", url=link)] for name, link in unchecked]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "✅ دسترسی شما تایید شد.\n\n"
                "⚠️ توجه: برای اطمینان از دریافت محتوای کامل، لطفاً روی دکمه(های) زیر کلیک کرده و در کانال(های) مربوطه عضو شوید.",
                reply_markup=reply_markup
            )
            await asyncio.sleep(1)
        if context.args:
            keyword = context.args[0]
            await send_media_by_keyword(update, context, keyword)
        else:
            await update.message.reply_text(
                "سلام! 👋\n\n"
                "این ربات فقط از طریق لینک‌های اختصاصی کار می‌کند.\n"
                "لطفاً از لینک معتبری برای مشاهده محتوا استفاده کنید.\n\n"
                "توجه: محتوا پس از یک دقیقه خودکارسازی می‌شود."
            )
    except (NetworkError, TimedOut):
        await update.message.reply_text("خطا در اتصال به سرور تلگرام. لطفاً چند لحظه دیگر دوباره تلاش کنید.")
        return
    except Exception as e:
        logger.error(f"Error in start handler: {e}")
        await update.message.reply_text("خطایی رخ داد. لطفاً بعداً تلاش کنید.")
        return


def main() -> None:
    if ADMIN_USER_ID == 0:
        print("⚠️ لطفاً ابتدا ADMIN_USER_ID را در متغیرهای محیطی تنظیم کنید.")
        return
    print("ربات با قابلیت مدیریت کامل از راه دور راه‌اندازی شد.")
    application = Application.builder().token(TOKEN).connect_timeout(20.0).read_timeout(90.0).write_timeout(90.0).pool_timeout(10.0).build()
    # اضافه کردن تمام هندلرهای مدیریتی
    application.add_handler(CommandHandler("addchannel", add_channel_command))
    application.add_handler(CommandHandler("listchannels", list_channels_command))
    application.add_handler(CommandHandler("removechannel", remove_channel_command))
    application.add_handler(CommandHandler("addmedia", add_media_command))
    application.add_handler(CommandHandler("listmedia", list_media_command))
    application.add_handler(CommandHandler("deletemedia", delete_media_command))
    application.add_handler(CommandHandler("syncstatus", sync_status_command))  # دستور جدید برای بررسی وضعیت همگام‌سازی
    # تغییر: اضافه کردن دستورات مدیریت مدیران
    application.add_handler(CommandHandler("addadmin", add_admin_command))
    application.add_handler(CommandHandler("removeadmin", remove_admin_command))
    application.add_handler(CommandHandler("listadmins", list_admins_command))
    # هندلرهای اصلی
    application.add_error_handler(error_handler)
    application.add_handler(CommandHandler("start", start))
    application.run_polling()
    logger.info("ربات با قابلیت مدیریت کامل از راه دور با موفقیت شروع به کار کرد!")

async def error_handler(update: object, context: CallbackContext) -> None:
    logger.error('Exception while handling an update: %s', context.error)
    try:
        if isinstance(context.error, NetworkError): 
            if update and hasattr(update, 'message'):
                await update.message.reply_text("خطای شبکه! لطفاً بعداً تلاش کنید.")
        elif isinstance(context.error, TimedOut): 
            if update and hasattr(update, 'message'):
                await update.message.reply_text("زمان اتصال به سرور تمام شد! لطفاً بعداً تلاش کنید.")
        else: 
            if update and hasattr(update, 'message'):
                await update.message.reply_text("خطایی رخ داد. لطفاً بعداً تلاش کنید.")
    except Exception: 
        pass

if __name__ == '__main__':
    main()
