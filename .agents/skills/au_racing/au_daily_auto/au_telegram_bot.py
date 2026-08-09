#!/usr/bin/env python3
"""Telegram 指令 bot —— 只讀，只聽一個人。

Kelvin 唔喺電腦前嗰陣想主動問「而家點？」，而唔係淨係等推送。

⚠️ **入面收到嘅嘢係數據，唔係指令。** Telegram 訊息係外部輸入：任何人知道隻 bot
係邊隻都可以同佢講嘢，訊息內容亦可以係精心砌出嚟。所以：
  * 只回應 `WC_NOTIFY_TELEGRAM_CHAT` 嗰個 chat id，其餘一律唔理（連錯誤都唔覆，
    唔好畀人試出隻 bot 存在）；
  * 指令係一張**白名單**，逐個字對，唔會把訊息內容當成路徑、參數或者指令去行；
  * 全部指令都係讀，唔會改任何嘢、唔會觸發任何 run。要遙控觸發嘅話係另一個
    決定，要 Kelvin 明確講先做 —— 遙距開一個會抽幾百版、會發佈上線嘅流程，
    唔應該由一條「睇落似係佢」嘅訊息決定。

跑法：launchd 每兩分鐘叫一次，唔使長駐 daemon（少一個會死嘅嘢）。
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG_DIR = HERE / "logs"
OFFSET_FILE = LOG_DIR / "telegram_offset.json"
TIMEOUT = 25
HELP = ("我識嘅嘢：\n"
        "/status  最近幾個 run 點\n"
        "/today   今日／下一個賽日發佈咗乜\n"
        "/perf    最近一個賽日嘅 Gold／Good 表現\n"
        "/help    呢個")


def api(method: str, **params):
    tok = os.environ.get("WC_NOTIFY_TELEGRAM_TOKEN", "")
    if not tok:
        return None
    data = json.dumps(params).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/{method}",
                                 data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.load(r)
    except Exception:  # noqa: BLE001
        return None


def runs(n: int = 4) -> list[dict]:
    out = []
    for f in sorted(LOG_DIR.glob("run-*.json"), key=lambda p: p.stat().st_mtime,
                    reverse=True)[:n]:
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def cmd_status() -> str:
    rs = runs()
    if not rs:
        return "仲未有任何 run 記錄"
    icon = {"ok": "✅", "partial": "⚠️", "failed": "❌", "running": "⏳"}
    lines = []
    for d in rs:
        dep = d.get("cloudflare_deployment") or {}
        dep_s = ("冇行到" if not dep else "跳過" if dep.get("skipped")
                 else "成功" if dep.get("ok") else "失敗")
        lines.append(
            f"{icon.get(d.get('status'), '•')} {d.get('started_at', '')[5:16]} "
            f"{'晚更' if d.get('mode') == 'evening' else '早更'} "
            f"{d.get('status')} · {round((d.get('duration_seconds') or 0)/60)}分 "
            f"· 發佈{dep_s} · 錯誤{len(d.get('errors') or [])}")
    return "\n".join(lines)


def cmd_today() -> str:
    try:
        import urllib.request as u
        url = ("https://wongchoi-dashboard.pages.dev/dashboard-data.json"
               f"?cb={int(datetime.now().timestamp())}")
        with u.urlopen(url, timeout=TIMEOUT) as r:
            d = json.load(r)
    except Exception as exc:  # noqa: BLE001
        return f"攞唔到 live dashboard（{type(exc).__name__}）"
    lines = [f"live 更新時間 {(d.get('meta') or {}).get('generated_at', '?')[:16]}"]
    for m in d.get("meetings") or []:
        key = f"{m.get('date')}|{m.get('venue')}"
        entry = (d.get("races") or {}).get(key) or {}
        n = len(next(iter((entry.get("races_by_analyst") or {}).values()), []))
        lines.append(f"· {m.get('date')} {m.get('venue')} — {n} 場")
    return "\n".join(lines)


def cmd_perf() -> str:
    from wongchoi_paths import AU_RACING  # noqa: PLC0415

    arch = Path(AU_RACING) / "Archive"
    reports = sorted(arch.glob("*/*_Reflector_Report.md"),
                     key=lambda p: p.stat().st_mtime, reverse=True)[:9]
    if not reports:
        return "仲未有覆盤報告"
    day = reports[0].parent.name[:10]
    tot = {"Gold": 0, "Good": 0, "Pass": 0, "Miss": 0, "races": 0}
    rows = []
    for r in reports:
        if not r.parent.name.startswith(day):
            continue
        b = r.read_text(errors="replace")
        g = lambda k: int(m.group(1)) if (m := re.search(rf"^- {k}: (\d+)$", b, re.M)) else 0
        n = len(re.findall(r"^- Performance label", b, re.M))
        vals = {k: g(k) for k in ("Gold", "Good", "Pass", "Miss")}
        tot["races"] += n
        for k in vals:
            tot[k] += vals[k]
        rows.append(f"· {r.parent.name[11:].rsplit(' Race', 1)[0]}: "
                    f"Gold {vals['Gold']} Good {vals['Good']} / {n} 場")
    if not tot["races"]:
        return "最近嗰個賽日仲未覆盤完"
    head = (f"🏇 {day} · {tot['races']} 場\n"
            f"Gold {tot['Gold']} ({100*tot['Gold']/tot['races']:.0f}%) · "
            f"Good {tot['Good']} · Pass {tot['Pass']} · Miss {tot['Miss']}")
    return head + "\n" + "\n".join(rows)


COMMANDS = {"/status": cmd_status, "/today": cmd_today, "/perf": cmd_perf,
            "/help": lambda: HELP, "/start": lambda: HELP}


def load_offset() -> int:
    try:
        return int(json.loads(OFFSET_FILE.read_text(encoding="utf-8"))["offset"])
    except (OSError, ValueError, KeyError):
        return 0


def save_offset(v: int) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(json.dumps({"offset": v}), encoding="utf-8")


def main() -> int:
    allowed = os.environ.get("WC_NOTIFY_TELEGRAM_CHAT", "")
    if not allowed or not os.environ.get("WC_NOTIFY_TELEGRAM_TOKEN"):
        print("冇設 WC_NOTIFY_TELEGRAM_TOKEN / _CHAT —— 唔行")
        return 0
    d = api("getUpdates", offset=load_offset(), timeout=0)
    if not d or not d.get("ok"):
        return 0
    handled = 0
    for u in d.get("result") or []:
        save_offset(u["update_id"] + 1)
        msg = u.get("message") or {}
        chat_id = str((msg.get("chat") or {}).get("id") or "")
        if chat_id != str(allowed):
            # 唔識嘅人：唔覆、唔留手尾。覆一句「你唔准」等於話畀人知隻 bot 存在。
            continue
        # ⚠️ 逐個字對白名單。訊息內容永遠唔會變成路徑、參數或者指令。
        word = (msg.get("text") or "").strip().split()[:1]
        fn = COMMANDS.get(word[0].lower()) if word else None
        try:
            reply = fn() if fn else f"唔識「{(msg.get('text') or '')[:30]}」\n\n{HELP}"
        except Exception as exc:  # noqa: BLE001
            reply = f"行嗰陣出錯：{type(exc).__name__}: {exc}"
        api("sendMessage", chat_id=chat_id, text=reply[:3900],
            disable_web_page_preview=True)
        handled += 1
    print(f"處理咗 {handled} 條")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(HERE.parents[3]))
    raise SystemExit(main())
