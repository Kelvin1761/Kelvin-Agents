#!/bin/zsh
# 攞 Telegram chat id —— 你自己跑，個 token 由頭到尾唔會離開部機。
#
# 步驟：
#   1. Telegram 搵 @BotFather → /newbot → 跟指示 → 佢會畀你一個 token
#   2. 開 ~/.wongchoi_notify.env，入面寫：
#        export WC_NOTIFY_TELEGRAM_TOKEN=<個 token>
#   3. 喺 Telegram 搵返你隻新 bot，撳 Start，隨便講句嘢
#   4. 跑呢個 script，佢會印返 chat id，然後把 chat id 加埋落同一個檔
set -u
ENV_FILE="$HOME/.wongchoi_notify.env"
[ -f "$ENV_FILE" ] || { print -r -- "❌ 搵唔到 $ENV_FILE —— 先照上面第 2 步開個檔"; exit 1; }
source "$ENV_FILE"
[ -n "${WC_NOTIFY_TELEGRAM_TOKEN:-}" ] || { print -r -- "❌ $ENV_FILE 冇 WC_NOTIFY_TELEGRAM_TOKEN"; exit 1; }

print -r -- "問緊 Telegram…（記住要先同隻 bot 講過嘢，否則佢乜都收唔到）"
/usr/bin/python3 - "$WC_NOTIFY_TELEGRAM_TOKEN" <<'PY'
import json, sys, urllib.request
tok = sys.argv[1]
try:
    with urllib.request.urlopen(
            f"https://api.telegram.org/bot{tok}/getUpdates", timeout=20) as r:
        d = json.load(r)
except Exception as exc:
    print(f"❌ 問唔到 Telegram：{type(exc).__name__}: {exc}")
    raise SystemExit(1)
if not d.get("ok"):
    print("❌ Telegram 話個 token 唔啱：", str(d.get("description"))[:120])
    raise SystemExit(1)
chats = {}
for u in d.get("result", []):
    msg = u.get("message") or u.get("channel_post") or {}
    c = msg.get("chat") or {}
    if c.get("id"):
        chats[c["id"]] = c.get("title") or c.get("username") or c.get("first_name") or ""
if not chats:
    print("⚠️ 收唔到任何訊息 —— 去 Telegram 搵你隻 bot，撳 Start 講句嘢，再跑一次")
    raise SystemExit(1)
for cid, name in chats.items():
    print(f"✅ chat id: {cid}   ({name})")
print()
print("加落 ~/.wongchoi_notify.env：")
print(f"  export WC_NOTIFY_TELEGRAM_CHAT={next(iter(chats))}")
PY
