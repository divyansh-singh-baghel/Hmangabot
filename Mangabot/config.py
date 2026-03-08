import os

# os.environ.get() ka matlab hai ki ye values PC se nahi, Render ke dashboard se aayengi
API_ID = int(os.environ.get("API_ID", "0")) 
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")