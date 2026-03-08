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
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# Auto-post & Database variables
auto_post_active = False
auto_post_tags = []
DATABASE_CHANNEL = int(os.environ.get("DATABASE_CHANNEL", "0"))
scraped_history = set() # Bot ki memory

# ==========================================
# 2. TELEGRAM DATABASE LOGIC (Option 1 Hack)
# ==========================================
async def load_database():
    print("📥 Telegram Channel se purani history load kar raha hu...")
    if DATABASE_CHANNEL == 0:
        print("⚠️ WARNING: DATABASE_CHANNEL ID set nahi hai Render mein!")
        return
        
    try:
        # Channel ke saare purane messages (links) padh kar memory me daal lo
        async for msg in app.get_chat_history(DATABASE_CHANNEL):
            if msg.text:
                scraped_history.add(msg.text.strip())
        print(f"✅ Database Loaded! Total {len(scraped_history)} manga pehle se saved hain.")
    except Exception as e:
        print(f"❌ Database load karne me error: {e}. Kya bot channel me admin hai?")

async def save_to_database(link):
    scraped_history.add(link) # Memory me save karo
    if DATABASE_CHANNEL != 0:
        try:
            await app.send_message(DATABASE_CHANNEL, link) # Channel me backup bhej do
        except Exception as e:
            print(f"❌ Database channel me link save nahi ho paya: {e}")

# ==========================================
# 3. TELEGRAM BOT SETUP
# ==========================================
app = Client("manga_bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    text = (
        "🤖 **Premium Manga Bot Ready!**\n\n"
        "🛠 **Commands:**\n"
        "1. `/getmanga <limit> <tags>` - Manual download\n"
        "2. `/autoon <tags>` - Auto-post shuru karein\n"
        "3. `/autooff` - Auto-post band karein\n"
    )
    await message.reply_text(text)

# ==========================================
# 4. MANUAL DOWNLOAD LOGIC
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
        # --- SMART FILTER 1: AI GENERATED CHECK ---
        title_lower = manga['title'].lower()
        if " ai " in f" {title_lower} " or "[ai]" in title_lower or "(ai)" in title_lower or "ai generated" in title_lower:
            await message.reply_text(f"🤖 Skipped AI Manga: {manga['title']}")
            continue

        pages = get_manga_pages(manga['link'])
        
        # --- SMART FILTER 2: PAGE COUNT CHECK ---
        if not pages or len(pages) < 7:
            await message.reply_text(f"📉 Skipped (Kam pages hain): {manga['title']}")
            continue
            
        await status_msg.edit_text(f"📥 **{manga['title']}**\nPDF ban rahi hai...")
        
        # Splitter logic support (ab yeh list aayegi)
        pdf_files = download_and_make_pdf(pages, manga['title'])
        
        if pdf_files:
            await status_msg.edit_text(f"📤 Uploading **{manga['title']}**...")
            for pdf_file in pdf_files:
                if os.path.exists(pdf_file):
                    await client.send_document(
                        chat_id=message.chat.id, 
                        document=pdf_file, 
                        caption=f"🔥 **{manga['title']}**\n🎯 **Tags:** {', '.join(tags)}"
                    )
                    os.remove(pdf_file) # Upload hote hi delete
                    
            await save_to_database(manga['link'])

    await status_msg.edit_text("✅ Manual Task Complete!")

# ==========================================
# 5. AUTO-POST LOGIC
# ==========================================
async def auto_post_task():
    global auto_post_active, auto_post_tags
    
    while True:
        if auto_post_active and auto_post_tags:
            print(f"🔄 Auto-Post Check chal raha hai for tags: {auto_post_tags}")
            manga_list = get_manga_list(auto_post_tags, limit=3)
            
            for manga in manga_list:
                # --- SMART FILTER 1: AI GENERATED CHECK ---
                title_lower = manga['title'].lower()
                if " ai " in f" {title_lower} " or "[ai]" in title_lower or "(ai)" in title_lower or "ai generated" in title_lower:
                    print(f"🤖 AI Manga Skipped: {manga['title']}")
                    continue

                # --- DATABASE CHECK ---
                if manga['link'] not in scraped_history:
                    pages = get_manga_pages(manga['link'])
                    
                    # --- SMART FILTER 2: PAGE COUNT CHECK ---
                    if not pages or len(pages) < 7:
                        print(f"📉 Skipped (Kam pages hain): {manga['title']}")
                        # Kachra manga ko bhi database me daal do taaki baar baar check na kare
                        await save_to_database(manga['link'])
                        continue
                        
                    print(f"🆕 Nayi Manga Mili: {manga['title']}")
                    pdf_files = download_and_make_pdf(pages, manga['title'])
                    
                    if pdf_files:
                        for pdf_file in pdf_files:
                            if os.path.exists(pdf_file):
                                await app.send_document(
                                    chat_id="me", # TODO: Jab main channel banega, yahan us channel ka ID aayega
                                    document=pdf_file,
                                    caption=f"🔥 **New Update**\n**{manga['title']}**\n🎯 **Tags:** {', '.join(auto_post_tags)}"
                                )
                                os.remove(pdf_file)
                                
                        await save_to_database(manga['link'])
                        print("✅ Uploaded & Saved to Telegram Database.")
                            
                    await asyncio.sleep(15) 
        
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
# RUN EVERYTHING
# ==========================================
async def start_bot():
    print("🚀 Telegram se connect kar raha hu...")
    await app.start()
    print("✅ Bot is ONLINE!")
    
    # Bot start hote hi sabse pehle database load karega
    await load_database()
    
    asyncio.create_task(auto_post_task())
    await idle()
    await app.stop()

if __name__ == "__main__":
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_bot())
