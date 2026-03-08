import os
import threading
import asyncio
from pyrogram import Client, filters, idle
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
    # Render jo port dega hum wo use karenge, taaki crash na ho
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# Auto-post variables
auto_post_active = False
auto_post_tags = []
HISTORY_FILE = "history.txt"

# History File Logic
def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r") as f:
        return f.read().splitlines()

def save_history(link):
    with open(HISTORY_FILE, "a") as f:
        f.write(link + "\n")

# ==========================================
# 2. TELEGRAM BOT SETUP
# ==========================================
app = Client("manga_bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    text = (
        "🤖 **Manga Bot Ready!**\n\n"
        "🛠 **Commands:**\n"
        "1. `/getmanga <limit> <tags>` - Manual download\n"
        "2. `/autoon <tags>` - Auto-post shuru karein\n"
        "3. `/autooff` - Auto-post band karein\n"
    )
    await message.reply_text(text)

# ==========================================
# 3. MANUAL DOWNLOAD LOGIC
# ==========================================
@app.on_message(filters.command("getmanga") & filters.private)
async def fetch_manga(client, message):
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
        pages = get_manga_pages(manga['link'])
        if not pages: continue
            
        await status_msg.edit_text(f"📥 **{manga['title']}**\nPDF ban rahi hai...")
        pdf_file = download_and_make_pdf(pages, manga['title'])
        
        if pdf_file and os.path.exists(pdf_file):
            await status_msg.edit_text(f"📤 Uploading **{manga['title']}**...")
            await client.send_document(
                chat_id=message.chat.id, 
                document=pdf_file, 
                caption=f"**{manga['title']}**\n🎯 **Tags:** {', '.join(tags)}\n🔗 **Link:** {manga['link']}"
            )
            os.remove(pdf_file)
            save_history(manga['link']) # Manual me bhi history save kar lo

    await status_msg.edit_text("✅ Manual Task Complete!")

# ==========================================
# 4. AUTO-POST LOGIC
# ==========================================
async def auto_post_task():
    global auto_post_active, auto_post_tags
    
    while True:
        if auto_post_active and auto_post_tags:
            print(f"🔄 Auto-Post Check chal raha hai for tags: {auto_post_tags}")
            
            manga_list = get_manga_list(auto_post_tags, limit=2)
            history = load_history()
            
            for manga in manga_list:
                if manga['link'] not in history:
                    print(f"🆕 Nayi Manga Mili: {manga['title']}")
                    
                    pages = get_manga_pages(manga['link'])
                    if pages:
                        pdf_file = download_and_make_pdf(pages, manga['title'])
                        if pdf_file and os.path.exists(pdf_file):
                            await app.send_document(
                                chat_id="me", # Khud ko bhejega, channel ke liye yahan ID dalna
                                document=pdf_file,
                                caption=f"🔥 **New Update**\n**{manga['title']}**\n🎯 **Tags:** {', '.join(auto_post_tags)}"
                            )
                            os.remove(pdf_file)
                            save_history(manga['link'])
                            print("✅ Uploaded & Saved to history.")
                            
                    await asyncio.sleep(10) 
        
        # Har 30 minutes (1800 seconds) me website check karega
        await asyncio.sleep(1800) 

@app.on_message(filters.command("autoon") & filters.private)
async def start_auto(client, message):
    global auto_post_active, auto_post_tags
    args = message.text.split()
    
    if len(args) < 2:
        await message.reply_text("❌ Tags batao. Format: `/autoon color english`")
        return
        
    auto_post_tags = args[1:]
    auto_post_active = True
    await message.reply_text(f"✅ Auto-Post ON ho gaya hai! Tags: {', '.join(auto_post_tags)}\nHar 30 minute me check karunga.")

@app.on_message(filters.command("autooff") & filters.private)
async def stop_auto(client, message):
    global auto_post_active
    auto_post_active = False
    await message.reply_text("🛑 Auto-Post band kar diya gaya hai.")

# ==========================================
# RUN EVERYTHING (Fix for 24/7 & Listening)
# ==========================================
async def start_bot():
    print("🚀 Telegram se connect kar raha hu...")
    await app.start()
    print("✅ Bot is ONLINE aur messages sun raha hai!")
    
    # Auto-post wale task ko background me chala do
    asyncio.create_task(auto_post_task())
    
    # Bot ko jagaye rakho taaki wo sun sake
    await idle()
    await app.stop()

if __name__ == "__main__":
    # Web server ko background thread me chalne do
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Bot ka main engine start karo
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_bot())
