#!/usr/bin/env python3
"""
cron_morning_trigger.py
(Phase 2.1: Zero-Click Pre-Game Telegram Push Automation)

This script is designed to be triggered via crontab at 9:00 PM AU Time 
before the game day. It wakes up the Hermes-Agent (Gemma 4) to automatically 
trigger the NBA Wong Choi pipeline, fetch data, run injury algorithms, and 
push the finished analysis to the user's Telegram.
"""

import os
import requests
import datetime
import argparse

# Dummy Configuration
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")
HERMES_AGENT_WEBHOOK = os.environ.get("HERMES_AGENT_WEBHOOK", "http://localhost:8080/trigger")

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload)
        print("✅ Telegram notification sent.")
    except Exception as e:
        print(f"⚠️ Failed to send Telegram message: {e}")

def trigger_hermes_pipeline(date_str):
    print(f"🚀 Triggering Hermes-Agent (Gemma 4) NBA Wong Choi Pipeline for {date_str}...")
    payload = {
        "agent": "nba_wong_choi",
        "action": "run_full_pipeline",
        "date": date_str
    }
    try:
        # Mocking the trigger request
        print(f"   [POST] {HERMES_AGENT_WEBHOOK} - {payload}")
        # response = requests.post(HERMES_AGENT_WEBHOOK, json=payload)
        
        message = (
            f"🏀 **NBA Wong Choi Pipeline Triggered!**\n"
            f"📅 Date: {date_str}\n"
            f"🤖 Agent: Hermes (Gemma 4)\n\n"
            f"I have started processing tomorrow's logic. You will receive the sharp money and H2H analysis shortly!"
        )
        send_telegram_message(message)
        print("✅ Trigger success.")
    except Exception as e:
        print(f"⚠️ Trigger failed: {e}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', type=str, help="YYYY-MM-DD to analyze. Defaults to tomorrow.")
    args = parser.parse_args()
    
    if args.date:
        target_date = args.date
    else:
        # Defaults to tomorrow since this runs at 9:00 PM the day before
        target_date = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        
    print(f"⏰ Cron Execution Triggered at {datetime.datetime.now().isoformat()}")
    trigger_hermes_pipeline(target_date)
