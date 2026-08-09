#!/usr/bin/env python3
"""獨立核實：今日賽事分析咗未？上咗 dashboard 未？唔得就補、補唔到就嗌。

⚠️ **要獨立過個排程 process 先有意義。** 現有嘅補救（補發、補覆盤、補抽）全部住喺
排程自己入面 —— 個 run 早死、crash、或者根本冇開（部機瞓咗、launchd 出事、鎖俾
人霸住），就冇任何嘢會發現。2026-08-05 至 08-10 三次多日空白，每次都係「有嘢
失敗咗，而冇人去問今日到底出咗未」。

判斷一律睇**實物**，唔睇 log：live JSON 有冇今日場次，本機有冇評分檔。一個報
「成功」嘅 run log 已經呃過我哋兩次。

自愈只做一件事：**由本機已評分嘅場次重建再發佈**（唔出網、成本低、唔會同人爭）。
「分析根本冇做」修唔到 —— 嗰個要抽幾百版，唔應該由一個 healthcheck 靜靜咁觸發，
所以出通知畀人決定。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[3]))

LIVE_URL = "https://wongchoi-dashboard.pages.dev/dashboard-data.json"
RUNNER = HERE / "run_au_daily_schedule.sh"


def live_meetings() -> set[str] | None:
    """⚠️ 一定要繞開 CDN cache，否則會攞到舊副本而誤判成「冇發佈」。"""
    url = f"{LIVE_URL}?cb={int(datetime.now().timestamp() * 1000)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "WongChoi-Healthcheck/1.0",
        "Cache-Control": "no-cache, max-age=0", "Pragma": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
    except Exception:  # noqa: BLE001
        return None
    return {f"{m.get('date')}|{m.get('venue')}" for m in d.get("meetings") or []}


def au_venues_today(day: str) -> set[str] | None:
    """今日應該有邊幾個澳洲馬場（Sportsbet API，curl 得到，唔使瀏覽器）。"""
    try:
        import au_daily_schedule as S

        class _Quiet:
            def warn(self, *a, **k): pass
            def step(self, *a, **k): pass
            def retry(self, *a, **k): pass
            data: dict = {}

        events = S.api_next_events(_Quiet())
        by_day = S.events_by_day(events)
        return set(by_day.get(day) or [])
    except Exception:  # noqa: BLE001
        return None


def local_scored(day: str) -> dict[str, int]:
    """{venue: 已評分場數}，本機（未歸檔）嗰批。"""
    from wongchoi_paths import AU_RACING

    out = {}
    for d in Path(AU_RACING).glob(f"{day} *"):
        if not d.is_dir():
            continue
        venue = re.sub(r"\s+Race\s+[\d\-]+$", "", d.name[11:]).strip()
        out[venue] = len(list(d.glob("Race_*_Auto_Analysis.md")))
    return out


def heal() -> tuple[bool, str]:
    """由本機重建再發佈。唔出網抽頁，所以安全、快、唔會同排程爭資源。"""
    try:
        r = subprocess.run([str(RUNNER), "morning", "--skip-refresh"],
                           capture_output=True, text=True, timeout=3600)
        return r.returncode in (0, 75), (r.stdout or "")[-400:]
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def check(day: str) -> dict:
    live = live_meetings()
    expect = au_venues_today(day)
    scored = local_scored(day)
    if live is None:
        return {"state": "unknown", "detail": "讀唔到 live dashboard"}
    live_today = {k.split("|", 1)[1] for k in live if k.startswith(day)}
    if expect is None:
        # API 唔通就退而求其次：本機有評分而 live 冇，一樣係漏咗。
        expect = set(scored)
    missing_live = sorted(v for v in expect if v not in live_today)
    if not missing_live:
        return {"state": "ok", "live": sorted(live_today), "expected": sorted(expect)}
    # 本機有冇評分？有 = 純發佈問題（補得到）；冇 = 分析根本未做（補唔到）。
    publishable = [v for v in missing_live if scored.get(v, 0) > 0]
    return {"state": "unpublished" if publishable else "unanalysed",
            "missing": missing_live, "publishable": publishable,
            "live": sorted(live_today), "expected": sorted(expect),
            "scored": scored}


def main() -> int:
    day = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    res = check(day)
    print(json.dumps(res, ensure_ascii=False, indent=2))

    def notify(text: str):
        try:
            import au_notify
            print("通知:", au_notify.push(text) or "冇出口")
        except Exception as exc:  # noqa: BLE001
            print("通知送唔出:", exc)

    if res["state"] == "ok":
        return 0
    if res["state"] == "unknown":
        notify(f"⚠️ AU 體檢 {day}\n讀唔到 live dashboard —— 未能核實今日賽事有冇上線")
        return 1
    if res["state"] == "unanalysed":
        notify(f"❌ AU 體檢 {day}\n未分析：{'、'.join(res['missing'])}\n"
               f"本機都冇評分檔 —— 體檢補唔到（要重抽），需要人手處理")
        return 1

    notify(f"⚠️ AU 體檢 {day}\n分析做咗但冇上 dashboard：{'、'.join(res['publishable'])}\n"
           f"正在自動補發佈…")
    ok, detail = heal()
    after = check(day)
    if after["state"] == "ok":
        notify(f"✅ AU 體檢 {day}\n已補發佈，今日場次全部上線：{'、'.join(after['live'])}")
        return 0
    notify(f"❌ AU 體檢 {day}\n補發佈失敗，仲係缺：{'、'.join(after.get('missing', []))}\n"
           f"{detail[-200:]}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
