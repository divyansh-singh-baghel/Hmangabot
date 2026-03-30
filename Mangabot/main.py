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

auto_post_active = False
auto_post_tags = []
DATABASE_CHANNEL = int(os.environ.get("DATABASE_CHANNEL", "0"))
scraped_history = set()

# Premium FSub Variables
FSUB_CHANNEL = os.environ.get("FSUB_CHANNEL", "") 
# YAHAN APNI IMAGE KA LINK DAAL DENA
START_IMAGE = "https://i.postimg.cc/mZh4Hpxb/ayaka.jpg" 

# ==========================================
# 2. TELEGRAM DATABASE LOGIC
# ==========================================
async def load_database():
    print("📥 Loading history from Telegram Database Channel...")
    if DATABASE_CHANNEL == 0:
        print("⚠️ WARNING: DATABASE_CHANNEL ID is not set!")
        return
    try:
        async for msg in app.get_chat_history(DATABASE_CHANNEL):
            if msg.text:
                scraped_history.add(msg.text.strip())
        print(f"✅ Database Loaded! Total {len(scraped_history)} items saved.")
    except Exception as e:
        print(f"❌ Database load error: {e}")

async def save_to_database(link):
    scraped_history.add(link)
    if DATABASE_CHANNEL != 0:
        try:
            await app.send_message(DATABASE_CHANNEL, link)
        except Exception:
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
        channel_link = f"https://t.me/{FSUB_CHANNEL.replace('@', '')}"
        join_btn = InlineKeyboardMarkup([[InlineKeyboardButton("📢 Join Channel To Use Bot", url=channel_link)]])
        
        await message.reply_photo(photo=START_IMAGE, caption=fsub_text, reply_markup=join_btn)
        return False
    except Exception as e:
        print(f"FSub Error: {e}")
        return True

@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    if not await check_fsub(client, message): return

    welcome_text = (
        f"🤖 **Welcome {message.from_user.first_name}!**\n\n"
        "Your Premium Access is verified. ✅\n\n"
        "To download a manga, use the following command structure:\n"
        "`/getmanga <limit> <tags>`\n"
        "**Example:** `/getmanga 1 color`\n\n"
        "Type `/help` for a detailed guide on how to use all commands."
    )
    await message.reply_photo(photo=START_IMAGE, caption=welcome_text)

@app.on_message(filters.command("help") & filters.private)
async def help_command(client, message):
    if not await check_fsub(client, message): return
    
    help_text = (
        "🛠 **Manga Bot - Premium Help Menu** 🛠\n\n"
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
        "• Stops the background scanning process completely."
    )
    await message.reply_text(help_text)

# ==========================================
# 4. MANUAL DOWNLOAD LOGIC (With ETA)
# ==========================================
@app.on_message(filters.command("getmanga") & filters.private)
async def fetch_manga(client, message):
    if not await check_fsub(client, message): return

    args = message.text.split()
    if len(args) < 3:
        await message.reply_text("❌ **Invalid Format!**\nPlease use: `/getmanga <limit> <tags>`\n*Example:* `/getmanga 1 color english`")
        return
    
    try:
        limit = int(args[1])
        tags = args[2:]
    except ValueError:
        await message.reply_text("❌ The `<limit>` must be a valid number (e.g., 1, 2, 5).")
        return

    status_msg = await message.reply_text(f"🔍 Searching for **{limit}** manga with tags: `{', '.join(tags)}`...")
    manga_list = get_manga_list(tags, limit)
    
    if not manga_list:
        await status_msg.edit_text("❌ No results found for the given tags. Try different keywords.")
        return

    await status_msg.edit_text(f"✅ Found **{len(manga_list)}** manga. Initiating processing sequence...")

    for manga in manga_list:
        title_lower = manga['title'].lower()
        if " ai " in f" {title_lower} " or "[ai]" in title_lower or "(ai)" in title_lower or "ai generated" in title_lower:
            await message.reply_text(f"🤖 **Skipped AI Manga:** {manga['title']}")
            continue

        pages = get_manga_pages(manga['link'])
        
        if not pages or len(pages) < 7:
            await message.reply_text(f"📉 **Skipped:** {manga['title']} (Contains less than 7 pages)")
            continue
            
        # Calculation for Estimated Time (Assuming ~0.8 seconds per page download)
        eta_seconds = int(len(pages) * 0.8)
        
        await status_msg.edit_text(
            f"📥 **{manga['title']}**\n\n"
            f"📄 **Total Pages:** {len(pages)}\n"
            f"⏳ **Estimated Time:** ~{eta_seconds} seconds\n\n"
            f"*(Downloading images and generating PDF. Please wait...)*"
        )
        
        pdf_files = download_and_make_pdf(pages, manga['title'])
        
        if pdf_files:
            await status_msg.edit_text(f"📤 **{manga['title']}** processed. Uploading to Telegram...")
            
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

    await status_msg.edit_text("✅ Download task completed successfully!")

# ==========================================
# 5. AUTO-POST LOGIC
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
        await message.reply_text("❌ **Format Error:** `/autoon <tags>`")
        return
    auto_post_tags = args[1:]
    auto_post_active = True
    await message.reply_text(f"✅ **Auto-Post Enabled!**\nScanning for tags: `{', '.join(auto_post_tags)}`")

@app.on_message(filters.command("autooff") & filters.private)
async def stop_auto(client, message):
    if not await check_fsub(client, message): return
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
