"""EXP-20261115-22 跟進（Kelvin「試下 6,000 場」）：補抓 2019-09 至 2023-10 嘅 HKJC 賽果頁（入面有競賽事件報告）。

安全同 backfill_history.py 一樣：一次一個請求、4–8 秒間隔、每 100 頁休息 2–3 分鐘、香港賽馬時段暫停、
頁面唔似預期（冇賽日日期或者冇「競賽事件報告」）→ 等 15 分鐘，連續 3 次 → 停並推 Telegram（primary）。
儲存：外置碟 hkjc-history/raw/results/<日期>_<場次>.html.gz（斷點續抓）。
用法：python3 fetch_reports.py
"""
import datetime as dt
import gzip
import os
import random
import sys
import time
from pathlib import Path

REPO = Path("/Users/imac/Antigravity-repo")
sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_race_extractor/scripts"))
sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"))
import backfill_history as bh  # noqa: E402

OUT = bh.RAW / "results"
LOG = bh.STATE / "results_fetch.log"
URL = "https://racing.hkjc.com/zh-hk/local/information/localresults?racedate={d}&Racecourse={v}&RaceNo={n}"
CUTOFF = "2023-10-15"


def log(msg):
    line = f"{dt.datetime.now(bh.HKT):%Y-%m-%d %H:%M:%S} HKT {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def main():
    bh.require_volume()
    OUT.mkdir(parents=True, exist_ok=True)
    import hkjc_history_replay_build as rb
    idx = rb.load_index()
    jobs = []
    for (d, n), race in sorted(idx["results"].items()):
        if d >= CUTOFF:
            continue
        venue = str(race.get("venue") or "")
        v = "HV" if "跑馬地" in venue else ("ST" if "沙田" in venue else None)
        if v is None:
            continue
        path = OUT / f"{d}_{n}.html.gz"
        if not path.exists():
            jobs.append((d, n, v, path))
    log(f"開始：{len(jobs)} 頁要抓")
    count = consec = 0
    started = time.time()
    for d, n, v, path in jobs:
        while bh.in_race_hours(dt.datetime.now(bh.HKT)):
            log("香港賽馬時段，暫停 10 分鐘")
            time.sleep(600)
        url = URL.format(d=d.replace("-", "/"), v=v, n=n)
        dmy = f"{d[8:10]}/{d[5:7]}/{d[:4]}"
        try:
            status, html = bh.fetch(url)
        except Exception as exc:
            status, html = -1, str(exc)
        if status != 200 or dmy not in html or "競賽事件報告" not in html:
            consec += 1
            log(f"⚠️ 失敗 {consec}/{bh.MAX_CONSEC_FAIL}：HTTP {status} {url}（{len(html)} bytes）")
            if consec >= bh.MAX_CONSEC_FAIL:
                msg = f"🛑 HKJC 事件報告補抓停咗：連續 {consec} 次失敗（最後 HTTP {status}）。已抓 {count} 頁，可以之後再跑（斷點續抓）。"
                log(msg); bh.notify(msg)
                sys.exit(2)
            time.sleep(bh.FAIL_WAIT)
            continue
        consec = 0
        tmp = path.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            fh.write(html)
        os.replace(tmp, path)
        count += 1
        if count % 50 == 0:
            log(f"已抓 {count}/{len(jobs)} 頁，{(time.time() - started) / count:.1f} 秒／頁")
        time.sleep(random.uniform(*bh.DELAY))
        if count % bh.LONG_PAUSE_EVERY == 0:
            time.sleep(random.uniform(*bh.LONG_PAUSE))
    msg = f"✅ HKJC 事件報告補抓完成：今次抓咗 {count} 頁（2019-09 至 2023-10）。"
    log(msg); bh.notify(msg)


if __name__ == "__main__":
    main()
