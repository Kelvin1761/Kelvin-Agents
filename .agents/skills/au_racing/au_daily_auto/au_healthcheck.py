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


def run_in_progress() -> bool:
    """而家有冇排程 run 跑緊。

    ⚠️ 冇呢個判斷嘅話，任何排喺個 run 完成之前嘅體檢都**必然**報「冇上線」——
    因為發佈本身就係最後一步 —— 跟住去補發佈，俾把鎖擋住，再send一條假警報。
    假警報係最快令人開始無視通知嘅嘢，而下一次真出事就係嗰個習慣害死你。

    用嗰把共用鎖做判斷，唔數 process：鎖住喺資料根，兩個 checkout 共用，而且
    正正就係「有人喺度郁緊呢批資料」嘅權威訊號。
    """
    import fcntl

    from wongchoi_paths import AU_RACING

    lock = Path(AU_RACING) / ".au_daily_schedule.lock"
    try:
        handle = lock.open("w")
    except OSError:
        return False
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    else:
        fcntl.flock(handle, fcntl.LOCK_UN)
        return False
    finally:
        handle.close()


ATTEMPTED = HERE / "logs" / "autofix_attempted.json"


def _attempted() -> set[str]:
    try:
        return set(json.loads(ATTEMPTED.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def _mark(name: str) -> None:
    seen = _attempted()
    seen.add(name)
    ATTEMPTED.parent.mkdir(parents=True, exist_ok=True)
    # 只留最近 40 個 —— 夠防重複，又唔會無限膨脹。
    ATTEMPTED.write_text(json.dumps(sorted(seen)[-40:]), encoding="utf-8")


def last_failed_run() -> tuple[Path, dict] | None:
    """最近一個 failed／partial 而且未試過自動修嘅 run。"""
    files = sorted((HERE / "logs").glob("run-*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)[:6]
    done = _attempted()
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if d.get("status") in ("failed", "partial") and f.name not in done:
            return f, d
        if d.get("status") == "ok":
            # 之後有成功嘅 run，之前嗰個失敗已經冇意義。
            return None
    return None


def autofix_last_failure() -> str | None:
    """對得上已知模式先修，而且一個 run 只試一次。

    ⚠️ 兩道限制都係刻意：
      * **只修已知模式** —— 一個估出嚟嘅補救可以令情況變差，仲會遮蓋「呢個係新
        問題」呢個最重要嘅訊號。對唔上就淨係報告。
      * **一個 run 只試一次** —— 唔係嘅話，一個修唔到嘅問題會令每次體檢都重跑
        一次發佈，一日三次，而且每次都 send 一條通知。
    """
    import au_diagnose  # noqa: PLC0415

    got = last_failed_run()
    if not got:
        return None
    path, run = got
    remedy = au_diagnose.remedy_for(run)
    if not remedy:
        return None
    _mark(path.name)
    if remedy != "republish":
        return f"⚠️ 認得個模式但唔識執行補救「{remedy}」 —— 要人睇"
    ok, detail = heal()
    after = check(date.today().isoformat())
    good = ok and after.get("state") in ("ok", "in-progress")
    head = "✅" if good else "❌"
    return (f"{head} 自動補救（{path.name}）\n"
            f"對上已知模式 → 重建並重新發佈\n"
            + ("今日場次已上線：" + "、".join(after.get("live") or [])
               if good else f"仲未修好：{detail[-200:]}"))


def check(day: str) -> dict:
    if run_in_progress():
        return {"state": "in-progress",
                "detail": "而家有排程 run 跑緊 —— 發佈係最後一步，仲未到"}
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
        # 今日場次上晒線唔代表上一個 run 冇死喺第二度（例如剪走失敗、合併空殼）。
        fixed = autofix_last_failure()
        if fixed:
            print(fixed)
            notify(fixed)
        return 0
    if res["state"] == "in-progress":
        # 唔出聲。跑緊唔係問題，而為咗「有嘢報」而報就係製造雜訊。
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
