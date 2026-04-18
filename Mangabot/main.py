import os
import threading
import asyncio
import json
import time
import random
import string
import requests
import urllib.parse
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserNotParticipant
from flask import Flask

# ==========================================
# ⚙️ TOKEN MANAGER LOGIC (Integrated)
# ==========================================
DB_FILE = "user_data.json"
SHORTENER_API_URL = os.environ.get("SHORTENER_API_URL", "https://linkshortify.com/api").strip()
SHORTENER_API_KEY = os.environ.get("SHORTENER_API_KEY", "").strip()

def load_data():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

def has_valid_pass(user_id):
    data = load_data()
    user_str = str(user_id)
    if user_str in data:
        expiry = data[user_str].get("expiry", 0)
        if time.time() < expiry:
            return True
    return False

def generate_token(user_id, pending_dl=None):
    data = load_data()
    user_str = str(user_id)
    token = "tok_" + "".join(random.choices(string.ascii_letters + string.digits, k=8))
    
    if user_str not in data:
        data[user_str] = {}
        
    data[user_str]["current_token"] = token
    if pending_dl:
        data[user_str]["pending_dl"] = pending_dl
        
    save_data(data)
    return token

def verify_token(user_id, token):
    data = load_data()
    user_str = str(user_id)
    if user_str in data:
        if data[user_str].get("current_token") == token:
            data[user_str]["expiry"] = time.time() + 86400
            data[user_str]["current_token"] = None 
            pending_dl = data[user_str].get("pending_dl")
            data[user_str]["pending_dl"] = None
            save_data(data)
            return True, pending_dl
    return False, None

# NAYA: Bulletproof API Logic (Crash fix)
def get_short_link(long_url):
    if not SHORTENER_API_KEY or SHORTENER_API_KEY == "YOUR_API_KEY_HERE":
        print("⚠️ API Key missing! Returning direct Telegram link.")
        return long_url 
        
    try:
        encoded_url = urllib.parse.quote(long_url)
        api_call = f"{SHORTENER_API_URL}?api={SHORTENER_API_KEY}&url={encoded_url}"
        response = requests.get(api_call)
        
        try:
            data = response.json()
            if data.get("status") == "success":
                print("✅ Ad Link Generated Successfully!")
                return data.get("shortenedUrl")
        except Exception:
            pass # Ignore JSON error and try text
            
        if response.status_code == 200 and response.text.startswith("http"):
            print("✅ Ad Link Generated Successfully!")
            return response.text.strip()
            
        print(f"❌ API Error: Invalid Response -> {response.text[:50]}")
        return long_url
    except Exception as e:
        print(f"❌ API Request Failed: {e}")
        return long_url


# ==========================================
# 1. DUMMY WEB SERVER & GLOBALS
# ==========================================
from scraper import get_manga_list, get_manga_pages, download_and_make_pdf
from config import API_ID, API_HASH, BOT_TOKEN

web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Premium Manga Bot is Online! 🚀"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

auto_post_active = False
auto_post_tags = []

# Queue System Lock
download_lock = asyncio.Lock()

db_env = os.environ.get("DATABASE_CHANNEL", "0").strip().replace(" ", "")
if db_env.startswith("https://t.me/"):
    db_env = "@" + db_env.split("/")[-1]
elif not db_env.lstrip("-").isdigit() and not db_env.startswith("@") and db_env != "0":
    db_env = "@" + db_env

try:
    DATABASE_CHANNEL = int(db_env)
except ValueError:
    DATABASE_CHANNEL = db_env

OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

FSUB_CHANNEL = os.environ.get("FSUB_CHANNEL", "") 
AUTO_POST_CHANNEL = "" 
START_IMAGE = "https://i.postimg.cc/mZh4Hpxb/ayaka.jpg" 

BOT_USERNAME = ""
FSUB_LINK = "https://t.me/telegram"

scraped_history = set()
USERS = set()
ADMINS = set()
AWAITING_IMAGE = set()

app = Client("manga_bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ==========================================
# 2. UPGRADED DATABASE & LINKS CACHE
# ==========================================
async def update_dynamic_links():
    global BOT_USERNAME, FSUB_LINK
    me = await app.get_me()
    BOT_USERNAME = me.username
    if FSUB_CHANNEL:
        try:
            chat = await app.get_chat(FSUB_CHANNEL)
            if chat.invite_link:
                FSUB_LINK = chat.invite_link
            else:
                FSUB_LINK = await app.export_chat_invite_link(FSUB_CHANNEL)
        except Exception as e:
            print(f"⚠️ Invite Link Error: {e}")
            if str(FSUB_CHANNEL).startswith("-100"):
                FSUB_LINK = "https://t.me/telegram"
            else:
                FSUB_LINK = f"https://t.me/{str(FSUB_CHANNEL).replace('@', '')}"

async def load_database():
    global START_IMAGE, FSUB_CHANNEL, AUTO_POST_CHANNEL
    print("📥 Loading Data from Database Channel...")
    if DATABASE_CHANNEL == 0 or DATABASE_CHANNEL == "0":
        print("⚠️ WARNING: DATABASE_CHANNEL ID is missing!")
        return

    try:
        wake_msg = await app.send_message(DATABASE_CHANNEL, "🔄 Database Syncing...")
        await asyncio.sleep(1)
        await wake_msg.delete()
    except Exception as e:
        print(f"⚠️ Could not wake DB Channel (Make sure bot is admin): {e}")

    try:
        async for msg in app.get_chat_history(DATABASE_CHANNEL):
            text = msg.text or msg.caption
            if text:
                text = text.strip()
                if text.startswith("ADMIN:"): ADMINS.add(int(text.split(":")[1]))
                elif text.startswith("DELADMIN:"):
                    aid = int(text.split(":")[1])
                    if aid in ADMINS: ADMINS.remove(aid)
                elif text.startswith("USER:"): USERS.add(int(text.split(":")[1]))
                elif text.startswith("IMAGE:"):
                    START_IMAGE = text.split(":", 1)[1]
                    if START_IMAGE == "NONE": START_IMAGE = None
                elif text.startswith("FSUB:"):
                    FSUB_CHANNEL = text.split(":", 1)[1]
                    if FSUB_CHANNEL == "NONE": FSUB_CHANNEL = ""
                elif text.startswith("AUTOPOST:"):
                    AUTO_POST_CHANNEL = text.split(":", 1)[1]
                    if AUTO_POST_CHANNEL == "NONE": AUTO_POST_CHANNEL = ""
                elif text.startswith("LINK:"): 
                    scraped_history.add(text.split(":", 1)[1].strip())
                elif text.startswith("http"): 
                    scraped_history.add(text.strip())
                    
        print(f"✅ DB Loaded: {len(scraped_history)} Manga | {len(USERS)} Users")
    except Exception as e:
        print(f"⚠️ Peer ID Invalid or DB Error: {e}")

async def save_to_db(data_string):
    if DATABASE_CHANNEL != 0 and DATABASE_CHANNEL != "0":
        try: await app.send_message(DATABASE_CHANNEL, data_string)
        except Exception: pass

# ==========================================
# 3. SECURITY: ADMIN & FSUB CHECKS
# ==========================================
MAIN_HELP_TEXT = (
    "🛠 **Manga Bot - Help Menu** 🛠\n\n"
    "**1. Manual Search & Download**\n"
    "Format: `/getmanga [limit] [tags]`\n"
    "• `[limit]`: Number of results (e.g., 1, 3)\n"
    "• `[tags]`: Keywords of the manga.\n"
    "💡 *Example:* `/getmanga 2 naruto doujin`\n\n"
    "**2. Automated Posting (Admin Only)**\n"
    "Format: `/autoon [tags]`\n"
    "• Starts checking the site every 30 mins.\n"
    "💡 *Example:* `/autoon color english`\n\n"
    "**3. Stop Automated Posting**\n"
    "Format: `/autooff`\n"
    "• Stops the background scanning process completely.\n\n"
    "⚙️ **Admin Controls:**\n"
    "`/setimage` - Change start picture (Send photo)\n"
    "`/setfsub @channel` - Force Subscribe setup (Type 'none' to remove)\n"
    "`/setautopost @channel` - Redirect downloads (Type 'none' for DM)\n"
    "`/stats` - View total users, manga & bot data\n"
    "`/addadmin [User_ID]` - Make someone an Admin (Owner only)\n"
    "`/deladmin [User_ID]` - Remove an Admin (Owner only)\n"
    "`/adminlist` - View all current Admins\n"
)

def is_admin(user_id):
    return user_id == OWNER_ID or user_id in ADMINS

async def check_fsub_and_admin(client, message, strict_admin=True):
    user_id = message.from_user.id
    
    if user_id not in USERS:
        USERS.add(user_id)
        await save_to_db(f"USER:{user_id}")
        
    if strict_admin and not is_admin(user_id):
        await message.reply_text("⛔ **Access Denied:** Private Bot.")
        return False
        
    if not FSUB_CHANNEL: return True 
    try:
        await client.get_chat_member(FSUB_CHANNEL, user_id)
        return True 
    except UserNotParticipant:
        fsub_text = (
            f"👤 **Hello {message.from_user.first_name}**\n\n"
            "🔐 **Join Channel to Use Bot**\n\n"
            "You must join our channel to use this bot and access premium manga."
        )
        fsub_buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Join Now", url=FSUB_LINK)],
            [InlineKeyboardButton("♻️ Try Again", callback_data="check_start")]
        ])
        try:
            if START_IMAGE: await message.reply_photo(photo=START_IMAGE, caption=fsub_text, reply_markup=fsub_buttons)
            else: await message.reply_text(text=fsub_text, reply_markup=fsub_buttons)
        except:
            await message.reply_text(text=fsub_text, reply_markup=fsub_buttons)
        return False
    except Exception: return True

# ==========================================
# 4. ADMIN & CALLBACK HANDLERS
# ==========================================
@app.on_message(filters.command("setfsub") & filters.private)
async def cmd_setfsub(client, message):
    global FSUB_CHANNEL
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    if len(args) < 2: return await message.reply_text("❌ **Format Error:** Use `/setfsub @YourChannel` or `/setfsub none`")
    val = args[1]
    FSUB_CHANNEL = "" if val.lower() == "none" else val
    await save_to_db(f"FSUB:{'NONE' if val.lower() == 'none' else val}")
    await update_dynamic_links()
    await message.reply_text(f"✅ FSub updated.")

@app.on_message(filters.command("setautopost") & filters.private)
async def cmd_setautopost(client, message):
    global AUTO_POST_CHANNEL
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    if len(args) < 2: return await message.reply_text("❌ **Format Error:** Use `/setautopost @YourChannel` or `/setautopost none`")
    val = args[1]
    AUTO_POST_CHANNEL = "" if val.lower() == "none" else val
    await save_to_db(f"AUTOPOST:{'NONE' if val.lower() == 'none' else val}")
    await message.reply_text(f"✅ Auto-post target updated.")

@app.on_message(filters.command("setimage") & filters.private)
async def cmd_setimage(client, message):
    global START_IMAGE
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    if len(args) == 2 and args[1].lower() == "none":
        START_IMAGE = None
        await save_to_db("IMAGE:NONE")
        await message.reply_text("✅ Start Image removed.")
    elif len(args) == 1:
        AWAITING_IMAGE.add(message.from_user.id)
        await message.reply_text("🖼️ **Send me the new Start Image photo now.**")
    else:
        await message.reply_text("❌ **Format Error:** Send `/setimage` to upload a photo or `/setimage none` to remove it.")

@app.on_message(filters.photo & filters.private)
async def handle_photo(client, message):
    global START_IMAGE
    if message.from_user.id in AWAITING_IMAGE:
        START_IMAGE = message.photo.file_id
        await save_to_db(f"IMAGE:{START_IMAGE}")
        AWAITING_IMAGE.remove(message.from_user.id)
        await message.reply_photo(photo=START_IMAGE, caption="✅ **Start Image Updated!**")

@app.on_message(filters.command("stats") & filters.private)
async def cmd_stats(client, message):
    if not is_admin(message.from_user.id): return
    stats_text = (
        "📊 **Bot Statistics** 📊\n\n"
        f"👥 **Unique Users:** `{len(USERS)}`\n"
        f"📚 **Manga Processed:** `{len(scraped_history)}`\n"
        f"👑 **Admins:** `{len(ADMINS)} (+Owner)`\n\n"
        f"🔐 **FSub Channel:** `{FSUB_CHANNEL if FSUB_CHANNEL else 'Not Set'}`\n"
        f"📢 **Post Channel:** `{AUTO_POST_CHANNEL if AUTO_POST_CHANNEL else 'DM Only'}`"
    )
    await message.reply_text(stats_text)

@app.on_message(filters.command("addadmin") & filters.private)
async def cmd_addadmin(client, message):
    if message.from_user.id != OWNER_ID: return
    try:
        new_admin = int(message.text.split()[1])
        if new_admin in ADMINS: return await message.reply_text("⚠️ Already an admin.")
        ADMINS.add(new_admin)
        await save_to_db(f"ADMIN:{new_admin}")
        await message.reply_text(f"✅ User `{new_admin}` is now an Admin!")
    except Exception: await message.reply_text("❌ **Format Error:** `/addadmin [User_ID]`\n*(Use Number ID, not username)*")

@app.on_message(filters.command("deladmin") & filters.private)
async def cmd_deladmin(client, message):
    if message.from_user.id != OWNER_ID: return
    try:
        del_admin = int(message.text.split()[1])
        if del_admin in ADMINS:
            ADMINS.remove(del_admin)
            await save_to_db(f"DELADMIN:{del_admin}")
            await message.reply_text(f"🗑️ Admin `{del_admin}` removed.")
    except Exception: await message.reply_text("❌ **Format Error:** `/deladmin [User_ID]`")

@app.on_message(filters.command("adminlist") & filters.private)
async def cmd_adminlist(client, message):
    if not is_admin(message.from_user.id): return
    text = f"👑 **Owner ID:** `{OWNER_ID}`\n\n🛡️ **Admins:**\n"
    for a in ADMINS: text += f"• `{a}`\n"
    if not ADMINS: text += "• No extra admins."
    await message.reply_text(text)

@app.on_callback_query()
async def handle_callback(client, message: CallbackQuery):
    if message.data == "show_help":
        await message.message.reply_text(MAIN_HELP_TEXT)
        await message.answer("✅ Help Menu Opened")
    elif message.data == "check_start":
        try:
            await client.get_chat_member(FSUB_CHANNEL, message.from_user.id)
            await message.message.delete()
            from pyrogram.types import Message
            fake_msg = Message(chat=message.message.chat, from_user=message.from_user, text="/start", client=client)
            await start_command(client, fake_msg)
            await message.answer("✅ Access verified!")
        except UserNotParticipant:
            await message.answer("❌ Join the channel first!", show_alert=True)
        except Exception:
            await message.answer("❌ Error.")

# ==========================================
# 5. START & 24H AD VERIFICATION HANDLER
# ==========================================
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    if not await check_fsub_and_admin(client, message, strict_admin=False): return
    
    user_id = message.from_user.id
    
    if len(message.command) > 1:
        arg = message.command[1]
        
        if arg.startswith("tok_"):
            is_valid, pending_dl = verify_token(user_id, arg)
            if is_valid:
                await message.reply_text("🎉 **24-Hour Premium Pass Activated!**\nYou can now download unlimited manga without ads for the next 24 hours.")
                if pending_dl:
                    arg = pending_dl 
                else:
                    return
            else:
                await message.reply_text("❌ **Invalid or Expired Token.** Please generate a new link.")
                return

        if arg.startswith("dl_"):
            if not has_valid_pass(user_id) and not is_admin(user_id):
                token = generate_token(user_id, pending_dl=arg)
                verify_link = f"https://t.me/{BOT_USERNAME}?start={token}"
                short_link = get_short_link(verify_link)
                
                locked_text = (
                    "⛔ **VIP Pass Expired**\n\n"
                    "To keep the bot alive, please verify your access. "
                    "Click the button below to get your **24-Hour VIP Pass** and unlock unlimited ad-free downloads!"
                )
                
                TUTORIAL_LINK = "https://t.me/telegram" 
                locked_buttons = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔓 Verify & Unlock 24H Pass", url=short_link)],
                    [InlineKeyboardButton("❓ How to Open / Tutorial", url=TUTORIAL_LINK)]
                ])
                locked_image = "https://i.postimg.cc/mZh4Hpxb/ayaka.jpg" 
                
                try:
                    await message.reply_photo(photo=locked_image, caption=locked_text, reply_markup=locked_buttons)
                except:
                    await message.reply_text(locked_text, reply_markup=locked_buttons)
                return

            db_ids = arg.replace("dl_", "").split("-")
            status_msg = await message.reply_text("📥 **Fetching your Manga securely... Please wait.**")
            for db_msg_id in db_ids:
                try:
                    await app.copy_message(
                        chat_id=message.chat.id, 
                        from_chat_id=DATABASE_CHANNEL, 
                        message_id=int(db_msg_id)
                    )
                except Exception as e:
                    print(f"Deep link fetch error: {e}")
            await status_msg.delete()
            return 
            
    welcome_text = (
        f"🤖 **Welcome to the Premium Manga Bot, {message.from_user.first_name}!**\n\n"
        "I am an advanced, high-speed automated bot designed to search, compile, and deliver high-quality manga directly to you in PDF format.\n\n"
        "*(Note: This is a private bot. Only Admins can use core commands)*\n\n"
        "📞 **Creator:** @DSB_07"
    )
    start_buttons = InlineKeyboardMarkup([[InlineKeyboardButton("🔍 Know More", callback_data="show_help")]])
    try:
        if START_IMAGE: await message.reply_photo(photo=START_IMAGE, caption=welcome_text, reply_markup=start_buttons)
        else: await message.reply_text(text=welcome_text, reply_markup=start_buttons)
    except Exception: await message.reply_text(text=welcome_text, reply_markup=start_buttons)

@app.on_message(filters.command("help") & filters.private)
async def help_command(client, message):
    if not await check_fsub_and_admin(client, message): return
    await message.reply_text(MAIN_HELP_TEXT)

# ==========================================
# 6. DOWNLOAD & POST BUILDER LOGIC
# ==========================================
async def build_and_send_premium_post(title, tags, pages_count, cover_url, pdf_files, dm_chat_id=None, is_autopost=False):
    db_msg_ids = []
    for pdf_file in pdf_files:
        if os.path.exists(pdf_file):
            try:
                db_msg = await app.send_document(
                    chat_id=DATABASE_CHANNEL,
                    document=pdf_file,
                    caption=f"📚 **{title}**"
                )
                db_msg_ids.append(str(db_msg.id))
            except Exception as e:
                print(f"⚠️ DB Upload Failed: {e}")
                
    if not db_msg_ids:
        if dm_chat_id:
            await app.send_message(dm_chat_id, "❌ **Error:** Could not upload to Database. Please verify the Bot is Admin in the Database Channel.")
        for pdf_file in pdf_files:
            if os.path.exists(pdf_file): os.remove(pdf_file)
        return

    dl_param = "dl_" + "-".join(db_msg_ids)
    download_link = f"https://t.me/{BOT_USERNAME}?start={dl_param}"
    
    post_buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Download Manga (PDF)", url=download_link)],
        [InlineKeyboardButton("🔥 Join Our Channel", url=FSUB_LINK)]
    ])
    
    post_caption = (
        f"📖 **Name:** `{title}`\n\n"
        f"🏷 **Tags:** `{', '.join(tags)}`\n"
        f"📄 **Pages:** `{pages_count}`"
    )

    async def send_to_target(target_chat):
        try:
            await app.send_photo(
                chat_id=target_chat,
                photo=cover_url if cover_url else START_IMAGE,
                caption=post_caption,
                reply_markup=post_buttons,
                has_spoiler=True  
            )
        except Exception as e:
            print(f"Post error in {target_chat}: {e}")

    if not is_autopost:
        if dm_chat_id: await send_to_target(dm_chat_id)
        if AUTO_POST_CHANNEL: await send_to_target(AUTO_POST_CHANNEL)
    else:
        target = AUTO_POST_CHANNEL if AUTO_POST_CHANNEL else OWNER_ID
        await send_to_target(target)

    for pdf_file in pdf_files:
        if os.path.exists(pdf_file):
            try: os.remove(pdf_file)
            except: pass

@app.on_message(filters.command("getmanga") & filters.private)
async def fetch_manga(client, message):
    if not await check_fsub_and_admin(client, message): return
    args = message.text.split()
    if len(args) < 3: 
        return await message.reply_text("❌ **Format Error:** Please use `/getmanga [limit] [tags]`\n💡 *Example:* `/getmanga 1 naruto`")
    try: 
        limit = int(args[1])
        tags = args[2:]
    except ValueError: 
        return await message.reply_text("❌ **Format Error:** Limit must be a number.\n💡 *Example:* `/getmanga 1 naruto`")

    status_msg = await message.reply_text(f"🔍 Searching for **{limit}** manga...")
    manga_list = get_manga_list(tags, limit)
    
    if not manga_list: return await status_msg.edit_text("❌ No results found.")
    await status_msg.edit_text(f"✅ Found **{len(manga_list)}** manga. Processing...")

    for manga in manga_list:
        try:
            if " ai " in manga['title'].lower() or "[ai]" in manga['title'].lower(): continue
            
            if manga['link'] in scraped_history:
                await message.reply_text(f"⚠️ **Skipped:** `{manga['title']}` is already in the database.")
                continue

            pages, cover_url = get_manga_pages(manga['link'])
            if not pages or len(pages) < 7: continue
                
            eta_seconds = int(len(pages) * 0.8)
            await status_msg.edit_text(f"📥 **{manga['title']}**\n📄 Pages: {len(pages)} | ⏳ ETA: ~{eta_seconds}s")
            
            async with download_lock:
                pdf_files = download_and_make_pdf(pages, manga['title'])
                
            if pdf_files:
                await build_and_send_premium_post(manga['title'], tags, len(pages), cover_url, pdf_files, dm_chat_id=message.chat.id, is_autopost=False)
                
                scraped_history.add(manga['link'])
                await save_to_db(f"LINK:{manga['link']}") 
        except Exception as e:
            print(f"Crash Guard Protected Bot: {e}")
            continue
            
    await status_msg.edit_text("✅ Task completed!")

# ==========================================
# 7. AUTO-POST LOGIC
# ==========================================
async def auto_post_task():
    global auto_post_active, auto_post_tags
    while True:
        if auto_post_active and auto_post_tags:
            manga_list = get_manga_list(auto_post_tags, limit=3)
            for manga in manga_list:
                try:
                    if " ai " in manga['title'].lower() or "[ai]" in manga['title'].lower(): continue
                    if manga['link'] not in scraped_history:
                        pages, cover_url = get_manga_pages(manga['link'])
                        if not pages or len(pages) < 7:
                            scraped_history.add(manga['link'])
                            await save_to_db(f"LINK:{manga['link']}")
                            continue
                        
                        async with download_lock:
                            pdf_files = download_and_make_pdf(pages, manga['title'])
                            
                        if pdf_files:
                            await build_and_send_premium_post(manga['title'], auto_post_tags, len(pages), cover_url, pdf_files, is_autopost=True)
                            
                            scraped_history.add(manga['link'])
                            await save_to_db(f"LINK:{manga['link']}")
                except Exception as e:
                    print(f"Auto-post error skipped: {e}")
                    continue
                await asyncio.sleep(15) 
        await asyncio.sleep(1800) 

@app.on_message(filters.command("autoon") & filters.private)
async def start_auto(client, message):
    if not await check_fsub_and_admin(client, message): return
    global auto_post_active, auto_post_tags
    args = message.text.split()
    if len(args) < 2: 
        return await message.reply_text("❌ **Format Error:** Please specify tags.\n💡 *Example:* `/autoon color english`")
    auto_post_tags = args[1:]
    auto_post_active = True
    await message.reply_text(f"✅ **Auto-Post Enabled!** for tags: `{', '.join(auto_post_tags)}`")

@app.on_message(filters.command("autooff") & filters.private)
async def stop_auto(client, message):
    if not await check_fsub_and_admin(client, message): return
    global auto_post_active
    auto_post_active = False
    await message.reply_text("🛑 **Auto-Post Terminated.**")

# ==========================================
# RUN EVERYTHING
# ==========================================
async def start_bot():
    print("🚀 Connecting to Telegram Servers...")
    await app.start()
    print("✅ Bot is ONLINE!")
    await update_dynamic_links() 
    await load_database()
    asyncio.create_task(auto_post_task())
    await idle()
    await app.stop()

if __name__ == "__main__":
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_bot())
