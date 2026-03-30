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
    return "Manga Bot is Alive and Running! 🚀"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# Auto-post & Database variables
auto_post_active = False
auto_post_tags = []
DATABASE_CHANNEL = int(os.environ.get("DATABASE_CHANNEL", "0"))
scraped_history = set()

# Premium FSub Variables
FSUB_CHANNEL = os.environ.get("FSUB_CHANNEL", "") 
START_IMAGE = "https://i.pinimg.com/originals/82/4c/75/824c75d5d8baddac1e3ab99a48b77f36.jpg"

# ==========================================
# 2. TELEGRAM DATABASE LOGIC
# ==========================================
async def load_database():
    print("📥 Telegram Channel se purani history load kar raha hu...")
    if DATABASE_CHANNEL == 0:
        print("⚠️ WARNING: DATABASE_CHANNEL ID set nahi hai!")
        return
    try:
        async for msg in app.get_chat_history(DATABASE_CHANNEL):
            if msg.text:
                scraped_history.add(msg.text.strip())
        print(f"✅ Database Loaded! Total {len(scraped_history)} manga saved hain.")
    except Exception as e:
        print(f"❌ Database load error: {e}")

async def save_to_database(link):
    scraped_history.add(link)
    if DATABASE_CHANNEL != 0:
        try:
            await app.send_message(DATABASE_CHANNEL, link)
        except Exception as e:
            pass

# ==========================================
# 3. PREMIUM FORCE SUB & START LOGIC
# ==========================================
app = Client("manga_bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def check_fsub(client, message):
    if not FSUB_CHANNEL:
        return True 
        
    try:
        await client.get_chat_member(FSUB_CHANNEL, message.from_user.id)
        return True 
    except UserNotParticipant:
        user_name = message.from_user.first_name
        fsub_text = (
            f"> 👤 **User:** {user_name}\n\n"
            "🔐 **Membership Required**\n\n"
            "Access to this bot is limited to subscribed members only.\n\n"
            "Please join the listed channel to activate your access."
        )
        # Button banana
        channel_link = f"https://t.me/{FSUB_CHANNEL.replace('@', '')}"
        join_btn = InlineKeyboardMarkup([[InlineKeyboardButton("📢 Join Channel To Use Bot", url=channel_link)]])
        
        await message.reply_photo(photo=START_IMAGE, caption=fsub_text, reply_markup=join_btn)
        return False
    except Exception as e:
        print(f"FSub Error (Bot admin nahi hoga): {e}")
        return True

@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    if not await check_fsub(client, message): return

    welcome_text = (
        f"🤖 **Welcome {message.from_user.first_name}!**\n\n"
        "Tumhara Premium Access verified hai. ✅\n\n"
        "Manga mangwane ke liye command use karo:\n"
        "`/getmanga <limit> <tags>`\n"
        "**Example:** `/getmanga 1 color`\n\n"
        "Baaki details ke liye `/help` type karo."
    )
    await message.reply_photo(photo=START_IMAGE, caption=welcome_text)

@app.on_message(filters.command("help") & filters.private)
async def help_command(client, message):
    if not await check_fsub(client, message): return
    
    help_text = (
        "🛠 **Manga Bot - Help Menu** 🛠\n\n"
        "🔍 **1. Search & Download:**\n"
        "`/getmanga <limit> <tags>`\n"
        "*(Yeh command tags ke hisaab se PDF bhej dega)*\n\n"
        "🤖 **2. Auto-Post System:**\n"
        "`/autoon <tags>`\n"
        "*(Bot har 30 min me check karega)*\n\n"
        "🛑 **3. Stop Auto-Post:**\n"
        "`/autooff`\n"
    )
    await message.reply_text(help_text)

# ==========================================
# 4. MANUAL DOWNLOAD LOGIC (With Buttons)
# ==========================================
@app.on_message(filters.command("getmanga") & filters.private)
async def fetch_manga(client, message):
    if not await check_fsub(client, message): return

    args = message.text.split()
    if len(args) < 3:
        await message.reply_text("❌ Format: `/getmanga 1 color english`")
        return
    
    try:
        limit = int(args[1])
        tags = args[2:]
    except ValueError:
        await message.reply_text("❌ Limit number hona chahiye.")
        return

    status_msg = await message.reply_text(f"🔍 Searching {limit} manga...")
    manga_list = get_manga_list(tags, limit)
    
    if not manga_list:
        await status_msg.edit_text("❌ Kuch nahi mila.")
        return

    await status_msg.edit_text(f"✅ {len(manga_list)} manga mili. Processing...")

    for manga in manga_list:
        title_lower = manga['title'].lower()
        if " ai " in f" {title_lower} " or "[ai]" in title_lower or "(ai)" in title_lower or "ai generated" in title_lower:
            await message.reply_text(f"🤖 Skipped AI Manga: {manga['title']}")
            continue

        pages = get_manga_pages(manga['link'])
        
        if not pages or len(pages) < 7:
            await message.reply_text(f"📉 Skipped (Kam pages hain): {manga['title']}")
            continue
            
        await status_msg.edit_text(f"📥 **{manga['title']}**\nPDF ban rahi hai...")
        pdf_files = download_and_make_pdf(pages, manga['title'])
        
        if pdf_files:
            await status_msg.edit_text(f"📤 Uploading **{manga['title']}**...")
            
            # Premium Channel Button
            channel_link = f"https://t.me/{FSUB_CHANNEL.replace('@', '')}" if FSUB_CHANNEL else "https://t.me/telegram"
            post_buttons = InlineKeyboardMarkup([[InlineKeyboardButton("🔥 Join Our Channel", url=channel_link)]])

            for pdf_file in pdf_files:
                if os.path.exists(pdf_file):
                    await client.send_document(
                        chat_id=message.chat.id, 
                        document=pdf_file, 
                        caption=f"📚 **{manga['title']}**\n\n🎯 **Tags:** {', '.join(tags)}",
                        reply_markup=post_buttons
                    )
                    os.remove(pdf_file)
                    
            await save_to_database(manga['link'])

    await status_msg.edit_text("✅ Task Complete!")

# ==========================================
# 5. AUTO-POST LOGIC (Shortened for display, but fully functional)
# ==========================================
async def auto_post_task():
    global auto_post_active, auto_post_tags
    while True:
        if auto_post_active and auto_post_tags:
            manga_list = get_manga_list(auto_post_tags, limit=3)
            for manga in manga_list:
                title_lower = manga['title'].lower()
                if " ai " in f" {title_lower} " or "[ai]" in title_lower or "(ai)" in title_lower: continue

                if manga['link'] not in scraped_history:
                    pages = get_manga_pages(manga['link'])
                    if not pages or len(pages) < 7:
                        await save_to_database(manga['link'])
                        continue
                        
                    pdf_files = download_and_make_pdf(pages, manga['title'])
                    if pdf_files:
                        channel_link = f"https://t.me/{FSUB_CHANNEL.replace('@', '')}" if FSUB_CHANNEL else "https://t.me/telegram"
                        post_buttons = InlineKeyboardMarkup([[InlineKeyboardButton("🔥 Join Our Channel", url=channel_link)]])
                        
                        for pdf_file in pdf_files:
                            if os.path.exists(pdf_file):
                                await app.send_document(
                                    chat_id=FSUB_CHANNEL if FSUB_CHANNEL else "me", 
                                    document=pdf_file,
                                    caption=f"🔥 **New Update**\n**{manga['title']}**\n🎯 **Tags:** {', '.join(auto_post_tags)}",
                                    reply_markup=post_buttons
                                )
                                os.remove(pdf_file)
                        await save_to_database(manga['link'])
                    await asyncio.sleep(15) 
        await asyncio.sleep(1800) 

@app.on_message(filters.command("autoon") & filters.private)
async def start_auto(client, message):
    if not await check_fsub(client, message): return
    global auto_post_active, auto_post_tags
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("❌ Format: `/autoon color english`")
        return
    auto_post_tags = args[1:]
    auto_post_active = True
    await message.reply_text(f"✅ Auto-Post ON! Tags: {', '.join(auto_post_tags)}")

@app.on_message(filters.command("autooff") & filters.private)
async def stop_auto(client, message):
    if not await check_fsub(client, message): return
    global auto_post_active
    auto_post_active = False
    await message.reply_text("🛑 Auto-Post band!")

# ==========================================
# RUN EVERYTHING
# ==========================================
async def start_bot():
    print("🚀 Telegram se connect kar raha hu...")
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
