import json
import os
import time
import random
import string
import requests
import urllib.parse

DB_FILE = "user_data.json"

# ==========================================
# ⚙️ URL SHORTENER API CONFIGURATION
# ==========================================
# FIX: Direct LinkShortify URL default kar diya hai taaki error na aaye
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
    # Generate 8-character random token
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
            # Token match ho gaya -> 24 Ghante (86400 sec) ka time dedo
            data[user_str]["expiry"] = time.time() + 86400
            data[user_str]["current_token"] = None # Token delete karo (One time use)
            pending_dl = data[user_str].get("pending_dl")
            data[user_str]["pending_dl"] = None
            save_data(data)
            return True, pending_dl
    return False, None

# Baaki upar ka code same rahega...

def get_short_link(long_url):
    if not SHORTENER_API_KEY or SHORTENER_API_KEY == "YOUR_API_KEY_HERE":
        print("⚠️ API Key missing! Returning direct Telegram link.")
        return long_url 
        
    try:
        encoded_url = urllib.parse.quote(long_url)
        # NAYA: &format=text add kiya taaki direct link mile, JSON error na aaye
        api_call = f"{SHORTENER_API_URL}?api={SHORTENER_API_KEY}&url={encoded_url}&format=text"
        
        response = requests.get(api_call)
        
        # Agar link direct text format me mila (http se shuru hone wala)
        if response.status_code == 200 and response.text.startswith("http"):
            print("✅ Ad Link Generated Successfully!")
            return response.text.strip()
            
        # Agar phir bhi JSON aaye toh fallback:
        try:
            data = response.json()
            if data.get("status") == "success":
                print("✅ Ad Link Generated Successfully!")
                return data.get("shortenedUrl")
        except:
            pass
            
        print(f"❌ LinkShortify API Error/HTML Response: {response.text}")
        return long_url
    except Exception as e:
        print(f"❌ API Request Failed: {e}")
        return long_url
