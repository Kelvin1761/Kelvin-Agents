#!/usr/bin/env python3
"""把一個 run 嘅結果推去手機。

點解需要：成套嘢喺背景跑，Kelvin 唔喺電腦前就完全睇唔到發生緊乜。2026-08-07
發佈撞到 Cloudflare 25 MiB 上限失敗咗兩晚，dashboard 一直停留喺舊版本 ——
log 入面寫得清清楚楚，但冇人會去睇 log，所以兩日之後先由「點解冇今日賽事」
發現。一個推得到手機嘅訊息就係嗰兩日嘅分別。

支援兩個出口，兩個都係純 HTTPS POST，所以喺 launchd 底下一樣行得：

  WC_NOTIFY_TELEGRAM_TOKEN + WC_NOTIFY_TELEGRAM_CHAT
                         Telegram bot。最簡單嗰個：@BotFather 開個 bot 免費、即時、
                         唔使商業帳號、唔使中間商。
  WC_NOTIFY_NTFY_TOPIC   ntfy.sh 嘅 topic 名。連 bot 都唔使開，但 topic 名就係
                         唯一嘅保護 —— 改個估唔到嘅。
  WC_NOTIFY_WEBHOOK      任何收 JSON 嘅 URL。WhatsApp 要行呢條 —— Twilio /
                         Zapier / Make 嗰邊接住再轉去 WhatsApp（WhatsApp 官方
                         API 一定要有商業帳號，冇得直接 POST）。

⚠️ token 由 env 讀，**唔會寫入版本控制、亦唔應該貼入對話**。runner 會 source
`~/.wongchoi_notify.env`（gitignore 唔到嘅位置，喺 repo 外面），你自己開嗰個檔。

  WC_NOTIFY_ONLY_PROBLEMS=1  只喺 partial / failed 至出聲。

⚠️ 通知失敗**唔可以**令 run 失敗 —— run 已經做完晒嘢，通知只係報告。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

TIMEOUT = 20
ICON = {"ok": "✅", "partial": "⚠️", "failed": "❌", "running": "⏳"}


def summarise(run: dict) -> tuple[str, str]:
    """run JSON → (標題, 內文)。內文要喺手機通知一眼睇晒。"""
    status = run.get("status") or "?"
    mode = "晚更" if run.get("mode") == "evening" else "早更"
    icon = ICON.get(status, "•")
    day = run.get("review_day") or ""
    mins = round((run.get("duration_seconds") or 0) / 60)

    added = run.get("races_added") or []
    updated = run.get("races_updated") or []
    archived = run.get("races_archived") or []
    lines = []
    if added:
        lines.append(f"新分析 {len(added)} 個場次／"
                     f"{sum(len(r.get('races') or []) for r in added)} 場")
    if updated:
        lines.append(f"重評分 {len(updated)} 個場次")
    if archived:
        lines.append(f"歸檔 {len(archived)} 個場次")

    dep = run.get("cloudflare_deployment") or {}
    if dep.get("skipped"):
        lines.append("發佈：冇變動，唔使發")
    elif dep.get("ok"):
        v = (dep.get("verified") or {}).get("ok")
        lines.append("發佈：成功" + ("、已核實上線" if v else "、但核實唔到"))
    elif dep:
        lines.append(f"發佈：失敗 —— {str(dep.get('detail'))[:80]}")
    else:
        lines.append("發佈：冇行到")

    errs = run.get("errors") or []
    for e in errs[:3]:
        lines.append(f"❌ {e.get('step')}: {str(e.get('message'))[:100]}")
    pending = sorted({m.get("status") for m in run.get("meetings_processed") or []}
                     & {"pending_extraction", "pending_results", "partial_results",
                        "refresh_deferred"})
    if pending:
        lines.append("未完成：" + "、".join(pending) + "（下次排程接住做）")

    ver = run.get("code_version") or {}
    if ver.get("engine_dirty"):
        lines.append(f"⚠️ 引擎有 {len(ver['engine_dirty'])} 個未 commit 嘅檔")

    title = f"{icon} AU {mode} {status} · {day} · {mins} 分鐘"
    return title, "\n".join(lines) or "冇動作"


def post(url: str, data: bytes, headers: dict) -> str | None:
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return None if 200 <= r.status < 300 else f"HTTP {r.status}"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return f"{type(exc).__name__}: {exc}"


def push(text: str, title: str = "🏇 AU 覆盤") -> list[str]:
    """直接推一段自訂文字（覆盤用），行同一批出口。"""
    out = []
    tok, chat = (os.environ.get("WC_NOTIFY_TELEGRAM_TOKEN"),
                 os.environ.get("WC_NOTIFY_TELEGRAM_CHAT"))
    if tok and chat:
        err = post(f"https://api.telegram.org/bot{tok}/sendMessage",
                   json.dumps({"chat_id": chat, "text": text[:3900],
                               "disable_web_page_preview": True}).encode("utf-8"),
                   {"Content-Type": "application/json"})
        out.append(f"telegram: {'ok' if err is None else err}")
    topic = os.environ.get("WC_NOTIFY_NTFY_TOPIC")
    if topic:
        err = post(f"https://ntfy.sh/{topic}", text.encode("utf-8"), {})
        out.append(f"ntfy: {'ok' if err is None else err}")
    return out


def send(run: dict) -> list[str]:
    """回一串「邊個出口點樣」嘅描述。冇配置就回空。"""
    status = run.get("status") or "?"
    if os.environ.get("WC_NOTIFY_ONLY_PROBLEMS") and status == "ok":
        return ["skipped: 只報問題"]

    title, body = summarise(run)
    out = []
    tg_token = os.environ.get("WC_NOTIFY_TELEGRAM_TOKEN")
    tg_chat = os.environ.get("WC_NOTIFY_TELEGRAM_CHAT")
    if tg_token and tg_chat:
        # 純文字，唔用 Markdown —— 場次名同錯誤訊息入面嘅 `_`、`*`、`[` 會令
        # Telegram 嘅 Markdown parser 直接拒收成條訊息，變成靜靜咁冇通知。
        payload = json.dumps({"chat_id": tg_chat,
                              "text": f"{title}\n\n{body}",
                              "disable_web_page_preview": True}).encode("utf-8")
        err = post(f"https://api.telegram.org/bot{tg_token}/sendMessage",
                   payload, {"Content-Type": "application/json"})
        out.append(f"telegram: {'ok' if err is None else err}")
    elif tg_token or tg_chat:
        out.append("telegram: 只設咗一半（token 同 chat id 兩樣都要）")
    topic = os.environ.get("WC_NOTIFY_NTFY_TOPIC")
    if topic:
        err = post(f"https://ntfy.sh/{topic}", body.encode("utf-8"),
                   {"Title": title.encode("utf-8").decode("latin-1", "replace"),
                    "Priority": "high" if status == "failed" else "default",
                    "Tags": "horse"})
        out.append(f"ntfy: {'ok' if err is None else err}")
    hook = os.environ.get("WC_NOTIFY_WEBHOOK")
    if hook:
        payload = json.dumps({"title": title, "body": body, "status": status,
                              "mode": run.get("mode"),
                              "review_day": run.get("review_day")},
                             ensure_ascii=False).encode("utf-8")
        err = post(hook, payload, {"Content-Type": "application/json"})
        out.append(f"webhook: {'ok' if err is None else err}")
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print("用法：au_notify.py <run-json>  |  --test")
        return 2
    if sys.argv[1] == "--test":
        run = {"status": "partial", "mode": "evening", "review_day": "2026-08-09",
               "duration_seconds": 4200,
               "races_added": [{"races": [1, 2, 3]}, {"races": [1, 2]}],
               "races_archived": [{"meeting": "x"}],
               "cloudflare_deployment": {"ok": True, "verified": {"ok": True}},
               "errors": [], "meetings_processed": [{"status": "pending_extraction"}],
               "code_version": {"engine_dirty": None}}
    else:
        run = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    title, body = summarise(run)
    print(title); print(body); print()
    print("送出：", send(run) or "冇配置任何出口 —— 睇 au_notify_setup.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
