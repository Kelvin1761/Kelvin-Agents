#!/usr/bin/env python3
"""一個失敗嘅 run → 一份可以直接睇嘅診斷。

點解要有：出事嗰陣 Kelvin 唔喺電腦前，佢淨係收到「❌ failed」加一兩句錯誤，
然後要自己開機、搵 log、抄過嚟問。真正嘅成本唔係修，係**由發現到有足夠資料判斷**
嗰段。呢個檔把嗰段自動化：邊一步死、跑緊邊個版本、log 上下文、同一個錯有冇
發生過、係咪已知模式。

⚠️ 佢**只診斷，唔改 code、唔發佈**。自動改分析引擎再自動上線係另一個風險等級：
一個「睇落合理」嘅自動修正可以令之後每晚嘅評分靜靜咁錯，而冇人會發現 —— 呢個
codebase 今個星期已經證明咗，靜默錯誤比大聲失敗難搞好多。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE / "logs" / "au_daily_schedule.log"
BUNDLE = HERE / "logs" / "last_diagnosis.md"

# 已知模式：錯誤特徵 → 成因、已知處理、**可以自動執行嘅補救**。
#
# ⚠️ `remedy` 只可以係一個已經寫好同測試過嘅動作。冇安全補救就寫 None ——
# 為咗「有得自動修」而砌一個未驗證嘅動作出嚟，比冇自動修差好多。
#
# 而家只有一個補救：`republish` = 由本機已評分嘅場次重建再發佈（唔出網抽頁）。
# 佢修得到嘅係**發佈側**嘅失敗（剪走冇生效、合併咗空殼、deploy 掂咗 Drive）——
# 呢三種嘅共同點係「分析係好嘅，只係冇上到線」，所以重發一次就啱。
#
# 抽取側嘅失敗（個站拒絕、瀏覽器死、賽果未出）**冇** remedy：補佢哋要重抽幾百版，
# 唔應該由一個自動修觸發，而且下一次排程本身就會接住做。
KNOWN = [
    (r"Pages only supports files up to",
     "snapshot 超過 Cloudflare 25 MiB 上限",
     "shrink_to_fit 會由已跑完場次讓路；如果單日賽事本身超標就要再縮 payload",
     "republish"),
    (r"PermissionError.*CloudStorage",
     "launchd 冇 Google Drive 權限",
     "deploy 唔應該再掃 Drive（--from-snapshot 已修）；鏡像失敗屬預期",
     "republish"),
    (r"TargetClosedError|Target crashed|browser has been closed",
     "Chrome 死咗（記憶體壓力，唔係個站封鎖）",
     "已有重開重試 + 每 25 版主動重開；部機得 8GB 係底層成因",
     None),
    (r"已歸檔但仲喺 dashboard",
     "剪走冇生效，或者合併把已歸檔場次加返",
     "build_snapshot 會由 Archive 推導剪走名單並拒絕合併已歸檔 folder",
     "republish"),
    (r"一場都冇（races_by_analyst 空",
     "合併咗一個冇評分／已搬走嘅 folder",
     "多數係次序問題：合併名單喺歸檔之前影低",
     "republish"),
    (r"個站.*拒絕|HTTP 403|只有 \d+ bytes",
     "sportsbetform 真係拒絕（非 200 或者攔截頁）",
     "circuit breaker 會停手，下一次排程再試",
     None),
    (r"cache 冇任何賽果",
     "賽果未出，或者場次腰斷",
     "腰斷偵測睇馬匹往績有冇當日出賽；兩日上限兜底",
     None),
]


def runs(n: int = 12) -> list[dict]:
    out = []
    for f in sorted((HERE / "logs").glob("run-*.json"),
                    key=lambda p: p.stat().st_mtime, reverse=True)[:n]:
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def log_context(needle: str, before: int = 12, after: int = 4) -> str:
    """log 入面錯誤附近嘅上下文 —— 通常真正線索喺出錯前嗰幾行。"""
    try:
        lines = LOG.read_text(errors="replace").splitlines()
    except OSError:
        return ""
    key = needle[:50]
    for i in range(len(lines) - 1, -1, -1):
        if key and key in lines[i]:
            return "\n".join(lines[max(0, i - before):i + after + 1])
    return "\n".join(lines[-before:])


def diagnose(run: dict, history: list[dict]) -> str:
    errs = run.get("errors") or []
    ver = run.get("code_version") or {}
    steps = run.get("steps") or []
    last_step = steps[-1] if steps else {}
    first = errs[0] if errs else {}
    msg = str(first.get("message") or "")

    matched = [(cause, fix, rem) for pat, cause, fix, rem in KNOWN
               if re.search(pat, msg)]
    same = [r for r in history
            if r is not run and any(msg[:40] in str(e.get("message") or "")
                                    for e in (r.get("errors") or []))]

    out = [f"# AU 診斷 · {run.get('mode')} · {run.get('started_at', '')[:16]}",
           "",
           f"- 結果：**{run.get('status')}**，用時 "
           f"{round((run.get('duration_seconds') or 0)/60)} 分鐘",
           f"- 死喺：`{first.get('step') or last_step.get('step') or '?'}`",
           f"- 版本：`{ver.get('commit', '?')}` / `{ver.get('branch', '?')}`"
           + ("　⚠️ 引擎有未 commit 改動" if ver.get("engine_dirty") else ""),
           f"- 走到嘅步驟：{' → '.join(s['step'] for s in steps[-6:])}",
           ""]
    if errs:
        out += ["## 錯誤"] + [f"- `{e.get('step')}`：{str(e.get('message'))[:300]}"
                              for e in errs[:4]] + [""]
    if matched:
        out += ["## 已知模式"]
        for cause, fix, rem in matched:
            out += [f"- **成因**：{cause}", f"  **已有處理**：{fix}",
                    f"  **自動補救**：{rem or '冇（要人睇／下次排程接住）'}"]
        out += [""]
    else:
        out += ["## 已知模式", "- 對唔上任何已知模式 —— 呢個係新嘅，要人睇", ""]
    if same:
        out += [f"## 重複性", f"- 最近 {len(history)} 個 run 入面，同一個錯出現咗 "
                f"{len(same)} 次：" + "、".join(r.get("started_at", "")[:16]
                                                for r in same[:4]), ""]
    else:
        out += ["## 重複性", "- 最近冇出現過同一個錯", ""]
    ctx = log_context(msg)
    if ctx:
        out += ["## log 上下文（出錯前後）", "```", ctx[-1800:], "```"]
    return "\n".join(out)


def remedy_for(run: dict) -> str | None:
    """呢個 run 嘅失敗有冇一個可以自動執行嘅補救。冇就回 None。

    ⚠️ 只睇**已知模式**。對唔上嘅錯誤永遠唔會觸發任何動作 —— 一個估出嚟嘅補救
    可以令情況變差，而且會遮蓋咗「呢個係新問題」呢個最重要嘅訊號。
    """
    for e in (run.get("errors") or []):
        msg = str(e.get("message") or "")
        for pat, _cause, _fix, rem in KNOWN:
            if rem and re.search(pat, msg):
                return rem
    return None


def phone_summary(text: str) -> str:
    """手機用嘅短版 —— 長版寫落檔，唔好塞爆通知。"""
    keep, take = [], False
    for line in text.splitlines():
        if line.startswith("## log"):
            break
        if line.startswith("#"):
            take = True
        if take and line.strip():
            keep.append(line.replace("**", "").replace("`", ""))
    return "\n".join(keep)[:1200]


def main() -> int:
    hist = runs()
    if not hist:
        print("冇 run 記錄")
        return 1
    target = next((r for r in hist if r.get("status") in ("failed", "partial")),
                  hist[0])
    if len(sys.argv) > 1 and sys.argv[1] != "--send":
        target = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    text = diagnose(target, hist)
    BUNDLE.write_text(text, encoding="utf-8")
    print(text)
    print(f"\n（完整版寫咗落 {BUNDLE}）")
    if "--send" in sys.argv:
        sys.path.insert(0, str(HERE))
        import au_notify
        print("送出：", au_notify.push("🔎 " + phone_summary(text)) or "冇出口")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
