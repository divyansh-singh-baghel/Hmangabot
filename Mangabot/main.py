import os
import threading
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from flask import Flask

from scraper import get_manga_list, get_manga_pages, download_and_make_pdf
from config import API_ID, API_HASH, BOT_TOKEN

# ==========================================
# 1. DUMMY WEB SERVER & GLOBALS
# ==========================================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Premium Manga Bot is Online! 🚀"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

auto_post_active = False
auto_post_tags = []
DATABASE_CHANNEL = int(os.environ.get("DATABASE_CHANNEL", "0"))
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

# Dynamic Settings
FSUB_CHANNEL = os.environ.get("FSUB_CHANNEL", "") 
AUTO_POST_CHANNEL = "" 
START_IMAGE = "https://i.postimg.cc/mZh4Hpxb/ayaka.jpg" 

# Memory Arrays
scraped_history = set()
USERS = set()
ADMINS = set()
AWAITING_IMAGE = set() # Naya Tracker image receive karne ke liye

# ==========================================
# 2. UPGRADED TELEGRAM DATABASE LOGIC
# ==========================================
async def load_database():
    global START_IMAGE, FSUB_CHANNEL, AUTO_POST_CHANNEL
    print("📥 Loading Data from Database Channel...")
    if DATABASE_CHANNEL == 0:
        print("⚠️ WARNING: DATABASE_CHANNEL ID is missing!")
        return
    try:
        async for msg in app.get_chat_history(DATABASE_CHANNEL):
            if msg.text:
                text = msg.text.strip()
                if text.startswith("ADMIN:"):
                    ADMINS.add(int(text.split(":")[1]))
                elif text.startswith("DELADMIN:"):
                    aid = int(text.split(":")[1])
                    if aid in ADMINS: ADMINS.remove(aid)
                elif text.startswith("USER:"):
                    USERS.add(int(text.split(":")[1]))
                elif text.startswith("IMAGE:"):
                    START_IMAGE = text.split(":", 1)[1]
                    if START_IMAGE == "NONE": START_IMAGE = None
                elif text.startswith("FSUB:"):
                    FSUB_CHANNEL = text.split(":", 1)[1]
                    if FSUB_CHANNEL == "NONE": FSUB_CHANNEL = ""
                elif text.startswith("AUTOPOST:"):
                    AUTO_POST_CHANNEL = text.split(":", 1)[1]
                    if AUTO_POST_CHANNEL == "NONE": AUTO_POST_CHANNEL = ""
                else:
                    scraped_history.add(text) 
                    
        print(f"✅ DB Loaded: {len(scraped_history)} Manga | {len(USERS)} Users | {len(ADMINS)} Admins")
    except Exception as e:
        print(f"❌ Database load error: {e}")

async def save_to_db(data_string):
    if DATABASE_CHANNEL != 0:
        try:
            await app.send_message(DATABASE_CHANNEL, data_string)
        except Exception as e:
            print(f"DB Save Error: {e}")

# ==========================================
# 3. SECURITY: ADMIN & FSUB CHECKS
# ==========================================
app = Client("manga_bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def is_admin(user_id):
    return user_id == OWNER_ID or user_id in ADMINS

async def check_fsub_and_admin(client, message, strict_admin=True):
    user_id = message.from_user.id
    
    if user_id not in USERS:
        USERS.add(user_id)
        await save_to_db(f"USER:{user_id}")
        
    if strict_admin and not is_admin(user_id):
        await message.reply_text("⛔ **Access Denied:**\n\nThis is a private bot. Only authorized Admins can use it.")
        return False
        
    if not FSUB_CHANNEL: return True 
    try:
        await client.get_chat_member(FSUB_CHANNEL, user_id)
        return True 
    except UserNotParticipant:
        user_name = message.from_user.first_name
        fsub_text = (
            f"> 👤 **User:** {user_name}\n\n"
            "🔐 **Membership Required**\n\n"
            "Please join the listed channel to activate your access."
        )
        
        link = f"https://t.me/{FSUB_CHANNEL.replace('@', '')}" if not str(FSUB_CHANNEL).startswith("-100") else "https://t.me/telegram"
        join_btn = InlineKeyboardMarkup([[InlineKeyboardButton("📢 Join Channel", url=link)]])
        
        try:
            if START_IMAGE: await message.reply_photo(photo=START_IMAGE, caption=fsub_text, reply_markup=join_btn)
            else: await message.reply_text(text=fsub_text, reply_markup=join_btn)
        except:
            await message.reply_text(text=fsub_text, reply_markup=join_btn)
        return False
    except Exception:
        return True

# ==========================================
# 4. ADMIN CONTROL PANEL COMMANDS
# ==========================================
@app.on_message(filters.command("setfsub") & filters.private)
async def cmd_setfsub(client, message):
    global FSUB_CHANNEL
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    if len(args) < 2: return await message.reply_text("❌ **Format:** `/setfsub @YourChannel`\n*(To remove: `/setfsub none`)*")
    val = args[1]
    if val.lower() == "none":
        FSUB_CHANNEL = ""
        await save_to_db("FSUB:NONE")
        await message.reply_text("✅ Force Subscribe requirement has been **REMOVED**.")
    else:
        FSUB_CHANNEL = val
        await save_to_db(f"FSUB:{val}")
        await message.reply_text(f"✅ Force Subscribe channel has been set to: **{val}**")

@app.on_message(filters.command("setautopost") & filters.private)
async def cmd_setautopost(client, message):
    global AUTO_POST_CHANNEL
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    if len(args) < 2: return await message.reply_text("❌ **Format:** `/setautopost @YourChannel`\n*(To remove: `/setautopost none`)*")
    val = args[1]
    if val.lower() == "none":
        AUTO_POST_CHANNEL = ""
        await save_to_db("AUTOPOST:NONE")
        await message.reply_text("✅ Auto-Post channel removed. Downloads will now be sent directly to your DM.")
    else:
        AUTO_POST_CHANNEL = val
        await save_to_db(f"AUTOPOST:{val}")
        await message.reply_text(f"✅ All downloads and Auto-Posts will now be sent to: **{val}**")

# --- NEW SETIMAGE LOGIC (Direct Photo Upload) ---
@app.on_message(filters.command("setimage") & filters.private)
async def cmd_setimage(client, message):
    global START_IMAGE
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    
    if len(args) == 2 and args[1].lower() == "none":
        START_IMAGE = None
        await save_to_db("IMAGE:NONE")
        await message.reply_text("✅ Start Image removed. Bot will only send text now.")
    else:
        AWAITING_IMAGE.add(message.from_user.id)
        await message.reply_text("🖼️ **Send me the new Start Image now.**\n*(Just upload a photo directly in this chat)*")

@app.on_message(filters.photo & filters.private)
async def handle_photo(client, message):
    global START_IMAGE
    if message.from_user.id in AWAITING_IMAGE:
        # Telegram ka direct fast link (file_id) nikalna
        START_IMAGE = message.photo.file_id
        await save_to_db(f"IMAGE:{START_IMAGE}")
        AWAITING_IMAGE.remove(message.from_user.id)
        await message.reply_photo(photo=START_IMAGE, caption="✅ **Start Image Updated Successfully!**\n*(It will now load instantly)*")

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
    except: await message.reply_text("❌ **Format:** `/addadmin <User_ID>`")

@app.on_message(filters.command("deladmin") & filters.private)
async def cmd_deladmin(client, message):
    if message.from_user.id != OWNER_ID: return
    try:
        del_admin = int(message.text.split()[1])
        if del_admin in ADMINS:
            ADMINS.remove(del_admin)
            await save_to_db(f"DELADMIN:{del_admin}")
            await message.reply_text(f"🗑️ Admin `{del_admin}` removed.")
    except: await message.reply_text("❌ **Format:** `/deladmin <User_ID>`")

@app.on_message(filters.command("adminlist") & filters.private)
async def cmd_adminlist(client, message):
    if not is_admin(message.from_user.id): return
    text = f"👑 **Owner ID:** `{OWNER_ID}`\n\n🛡️ **Admins:**\n"
    for a in ADMINS: text += f"• `{a}`\n"
    if not ADMINS: text += "• No extra admins."
    await message.reply_text(text)

# ==========================================
# 5. CORE BOT COMMANDS
# ==========================================
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    if not await check_fsub_and_admin(client, message, strict_admin=False): return
    welcome_text = (
        f"🤖 **Welcome to the Premium Manga Bot, {message.from_user.first_name}!**\n\n"
        "I am an advanced, high-speed automated bot designed to search, compile, and deliver high-quality manga directly to you in PDF format.\n\n"
        "*(Note: This is a private bot. Only Admins can use core commands)*"
    )
    try:
        if START_IMAGE: await message.reply_photo(photo=START_IMAGE, caption=welcome_text)
        else: await message.reply_text(text=welcome_text)
    except Exception: await message.reply_text(text=welcome_text)

# --- NEW FORMATTED HELP COMMAND ---
@app.on_message(filters.command("help") & filters.private)
async def help_command(client, message):
    if not await check_fsub_and_admin(client, message): return
    help_text = (
        "🛠 **Manga Bot - Help Menu** 🛠\n\n"
        "**1. Manual Search & Download**\n"
        "Format: `/getmanga <limit> <tags>`\n"
        "• `<limit>`: The number of results you want (e.g., 1, 3, 5)\n"
        "• `<tags>`: The keywords or name of the manga.\n"
        "💡 *Example:* `/getmanga 2 naruto doujin` (Downloads 2 Naruto doujins)\n\n"
        "**2. Automated Posting (Admin Only)**\n"
        "Format: `/autoon <tags>`\n"
        "• Starts checking the site every 30 minutes for the given tags.\n"
        "💡 *Example:* `/autoon color english`\n\n"
        "**3. Stop Automated Posting**\n"
        "Format: `/autooff`\n"
        "• Stops the background scanning process completely.\n\n"
        "⚙️ **Admin Controls:**\n"
        "`/setimage` - Change start picture (Just send photo)\n"
        "`/setfsub @channel` - Force Subscribe setup\n"
        "`/setautopost @channel` - Redirect downloads to channel\n"
        "`/stats` - View users & bot data\n"
    )
    await message.reply_text(help_text)

@app.on_message(filters.command("getmanga") & filters.private)
async def fetch_manga(client, message):
    if not await check_fsub_and_admin(client, message): return
    args = message.text.split()
    if len(args) < 3: return await message.reply_text("❌ **Format Error:** `/getmanga <limit> <tags>`")
    try: limit = int(args[1]); tags = args[2:]
    except ValueError: return await message.reply_text("❌ Limit must be a number.")

    status_msg = await message.reply_text(f"🔍 Searching for **{limit}** manga...")
    manga_list = get_manga_list(tags, limit)
    
    if not manga_list: return await status_msg.edit_text("❌ No results found.")
    await status_msg.edit_text(f"✅ Found **{len(manga_list)}** manga. Processing...")

    for manga in manga_list:
        if " ai " in manga['title'].lower() or "[ai]" in manga['title'].lower(): continue
        pages = get_manga_pages(manga['link'])
        if not pages or len(pages) < 7: continue
            
        eta_seconds = int(len(pages) * 0.8)
        await status_msg.edit_text(f"📥 **{manga['title']}**\n📄 Pages: {len(pages)} | ⏳ ETA: ~{eta_seconds}s")
        
        pdf_files = download_and_make_pdf(pages, manga['title'])
        if pdf_files:
            btn_link = f"https://t.me/{FSUB_CHANNEL.replace('@', '')}" if FSUB_CHANNEL and not str(FSUB_CHANNEL).startswith("-100") else "https://t.me/telegram"
            post_buttons = InlineKeyboardMarkup([[InlineKeyboardButton("🔥 Join Our Channel", url=btn_link)]])
            
            target_chat = AUTO_POST_CHANNEL if AUTO_POST_CHANNEL else message.chat.id
            
            for pdf_file in pdf_files:
                if os.path.exists(pdf_file):
                    await client.send_document(chat_id=target_chat, document=pdf_file, caption=f"📚 **{manga['title']}**\n🎯 **Tags:** {', '.join(tags)}", reply_markup=post_buttons)
                    os.remove(pdf_file)
            scraped_history.add(manga['link'])
            await save_to_db(manga['link'])
    await status_msg.edit_text("✅ Task completed!")

# ==========================================
# 6. AUTO-POST LOGIC (Admin Locked)
# ==========================================
async def auto_post_task():
    global auto_post_active, auto_post_tags
    while True:
        if auto_post_active and auto_post_tags:
            manga_list = get_manga_list(auto_post_tags, limit=3)
            for manga in manga_list:
                if " ai " in manga['title'].lower() or "[ai]" in manga['title'].lower(): continue
                if manga['link'] not in scraped_history:
                    pages = get_manga_pages(manga['link'])
                    if not pages or len(pages) < 7:
                        scraped_history.add(manga['link'])
                        await save_to_db(manga['link'])
                        continue
                        
                    pdf_files = download_and_make_pdf(pages, manga['title'])
                    if pdf_files:
                        btn_link = f"https://t.me/{FSUB_CHANNEL.replace('@', '')}" if FSUB_CHANNEL and not str(FSUB_CHANNEL).startswith("-100") else "https://t.me/telegram"
                        post_buttons = InlineKeyboardMarkup([[InlineKeyboardButton("🔥 Join Our Channel", url=btn_link)]])
                        
                        target_chat = AUTO_POST_CHANNEL if AUTO_POST_CHANNEL else "me"
                        
                        for pdf_file in pdf_files:
                            if os.path.exists(pdf_file):
                                await app.send_document(chat_id=target_chat, document=pdf_file, caption=f"🔥 **New Update**\n**{manga['title']}**\n🎯 **Tags:** {', '.join(auto_post_tags)}", reply_markup=post_buttons)
                                os.remove(pdf_file)
                        scraped_history.add(manga['link'])
                        await save_to_db(manga['link'])
                    await asyncio.sleep(15) 
        await asyncio.sleep(1800) 

@app.on_message(filters.command("autoon") & filters.private)
async def start_auto(client, message):
    if not await check_fsub_and_admin(client, message): return
    global auto_post_active, auto_post_tags
    args = message.text.split()
    if len(args) < 2: return await message.reply_text("❌ **Format:** `/autoon <tags>`")
    auto_post_tags = args[1:]
    auto_post_active = True
    await message.reply_text(f"✅ **Auto-Post Enabled!**")

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
    await load_database()
    asyncio.create_task(auto_post_task())
    await idle()
    await app.stop()

if __name__ == "__main__":
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_bot())
