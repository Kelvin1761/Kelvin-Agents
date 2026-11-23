"""HKJC 歷史試閘結果抓取（Kelvin 2026-11-23「歷史試閘資料庫（初出馬用）」）。只讀公開頁，每個請求隔 1.5 秒，原始 HTML gzip 存外置碟。
日期 = 存檔晨操頁出現過嘅試閘日（analysis/trial_dates.txt）∪ 2019-07-01～2022-12-31 每一日（早年存檔唔齊）。
已存在就跳過（可重跑續做）。冇試閘嘅日子頁面冇「第 1 組」→ 記入 empty.txt 唔再試。
用法：python3 hkjc_trials_scrape.py
"""
import datetime as dt
import gzip
import sys
import html
import re
import time
from pathlib import Path

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_race_extractor/scripts")
import extract_trackwork as X  # noqa: E402

BASE = Path("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history")
OUT = BASE / "raw" / "trials"
URL = "https://racing.hkjc.com/zh-hk/local/information/btresult?Date={}"


def main():
    known = set((BASE / "analysis" / "trial_dates.txt").read_text().split())
    d, end = dt.date(2019, 7, 1), dt.date(2022, 12, 31)
    while d <= end:
        known.add(d.isoformat()); d += dt.timedelta(days=1)
    empty_f = OUT / "empty.txt"
    empty = set(empty_f.read_text().split()) if empty_f.exists() else set()
    todo = sorted(x for x in known if x not in empty and not (OUT / f"{x}.html.gz").exists())
    print("要抓", len(todo), flush=True)
    for i, day in enumerate(todo):
        try:
            t = X.fetch_url(URL.format(day.replace("-", "/")), timeout=30, retries=2)
        except Exception as e:
            print(day, "ERR", e, flush=True); time.sleep(5); continue
        plain = html.unescape(re.sub(r"<[^>]+>", " ", t))
        if re.search(r"第\s*1\s*組", plain):
            with gzip.open(OUT / f"{day}.html.gz", "wt", encoding="utf-8") as fh:
                fh.write(t)
        else:
            with open(empty_f, "a") as fh:
                fh.write(day + "\n")
        if i % 50 == 0:
            print(i, day, flush=True)
        time.sleep(1.5)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
