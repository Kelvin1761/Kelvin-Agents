#!/usr/bin/env python3
os.environ.setdefault('PYTHONUTF8', '1')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os
import sys

try:
    import requests
except ImportError:
    print("❌ python-requests not found. Please pip install requests.")
    sys.exit(1)

# Helper function to parse .env file
def load_env(filepath):
    if not os.path.exists(filepath):
        return
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, val = line.split('=', 1)
                os.environ[key.strip()] = val.strip()

# Load Antigravity workspace .env
workspace_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
env_path = os.path.join(workspace_dir, ".env")
load_env(env_path)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

if not BOT_TOKEN or not CHAT_ID or BOT_TOKEN == "YOUR_BOT_TOKEN":
    print("⚠️ Telegram BOT_TOKEN or CHAT_ID not correctly set in .env. Skipping Telegram push.")
    sys.exit(0)

if len(sys.argv) < 2:
    print("⚠️ Usage: send_telegram_doc.py <file_path>")
    sys.exit(1)

file_path = sys.argv[1]
if not os.path.exists(file_path):
    print(f"⚠️ File tells not exist: {file_path}")
    sys.exit(1)

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"

try:
    with open(file_path, 'rb') as f:
        filename = os.path.basename(file_path)
        caption = f"🏀 Wong Choi Auto-Analysis: {filename}"
        files = {'document': f}
        data = {'chat_id': CHAT_ID, 'caption': caption}
        response = requests.post(url, files=files, data=data)
        
        if response.status_code == 200:
            print(f"✅ Telegram Push Success: {filename}")
        else:
            print(f"❌ Telegram Push Failed: {response.status_code} - {response.text}")
except Exception as e:
    print(f"❌ Exception sending to Telegram: {e}")
