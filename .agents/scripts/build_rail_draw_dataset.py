#!/usr/bin/env python3
"""build_rail_draw_dataset.py — 累積 rail-tagged 檔位賽果數據集

檔位與走位維度想試「rail（A/B/C/C+3 賽道）× 檔位」入計分，但 comprehensive_stats
無 rail 欄、單季賽日太少 fit 唔到。呢個 script 由歷史 full_day_results.json /
*全日賽果.json 抽出「每匹馬：日期、場地、路程、賽道(rail)、檔位、名次、上名、頭馬」，
寫入可增長嘅 rail_draw_results.csv。每個賽日賽後 re-run 就會累積，儲夠一季幾就可以
用嚟做 rail-aware 檔位評分嘅 ML 驗證（見 [[hkjc-auto-tuning-ceiling]]）。

rail 位置：每場 sectional_times header 有「草地/全天候 - "X" 賽道」。
用法：
  python3 build_rail_draw_dataset.py            # 掃全部歷史，寫 CSV（去重）
  python3 build_rail_draw_dataset.py --summary  # 只印 rail×場地分佈，唔寫
"""
import os
os.environ.setdefault("PYTHONUTF8", "1")
import argparse
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from wongchoi_paths import HK_RACING  # noqa: E402

DB = HK_RACING / "HKJC_Race_Results_Database"
OUT = DB / "comprehensive_stats" / "rail_draw_results.csv"
RAIL_RE = re.compile(r'(?:草地|全天候|泥地)\s*[-–]?\s*[「"]?\s*([ABC](?:\s*\+\s*\d)?)\s*[「"]?\s*賽道')
DIST_RE = re.compile(r'(\d{3,4})\s*米')
VENUE_NORM = {"ShaTin": "沙田", "HappyValley": "跑馬地", "ST": "沙田", "HV": "跑馬地"}


def result_files():
    """所有賽果 json：季度 results DB + archive меeting 全日賽果.json。"""
    files = []
    for d in DB.glob("hkjc results *"):
        files += glob.glob(str(d / "*" / "full_day_results.json"))
    files += glob.glob(str(HK_RACING.parent / "Archive_Race_Analysis" / "HK_Racing" / "*" / "*全日賽果.json"))
    return files


def race_rail_dist(race: dict):
    txt = json.dumps(race.get("sectional_times", ""), ensure_ascii=False).replace('\\"', '"')
    rm = RAIL_RE.search(txt)
    dm = DIST_RE.search(txt)
    rail = rm.group(1).replace(" ", "") if rm else None
    dist = int(dm.group(1)) if dm else None
    surf = "AWT" if "全天候" in txt else ("Turf" if "草地" in txt else None)
    return rail, dist, surf


def collect():
    rows = {}  # dedup key → row
    for fp in result_files():
        try:
            data = json.loads(Path(fp).read_text(encoding="utf-8"))
        except Exception:
            continue
        for race_key, race in data.items():
            if not isinstance(race, dict):
                continue
            try:
                rno = int(race.get("race_no") or race_key)
            except (TypeError, ValueError):
                continue
            date = str(race.get("racedate") or "")
            venue = VENUE_NORM.get(str(race.get("venue") or "").strip(), str(race.get("venue") or "").strip())
            rail, dist, surf = race_rail_dist(race)
            for row in race.get("results", []):
                try:
                    pos = int(re.sub(r"\D", "", str(row.get("pos", ""))) or 0)
                    draw = int(re.sub(r"\D", "", str(row.get("draw", ""))) or 0)
                except (TypeError, ValueError):
                    continue
                if pos <= 0 or draw <= 0:
                    continue
                key = (date, rno, str(row.get("horse_no", "")))
                rows[key] = {
                    "Date": date, "RaceNo": rno, "Venue": venue, "Track": surf or "",
                    "Distance": dist or "", "Rail": rail or "", "Draw": draw,
                    "Pos": pos, "Win": 1 if pos == 1 else 0, "Place": 1 if pos <= 3 else 0,
                }
    return list(rows.values())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", action="store_true", help="只印分佈，唔寫 CSV")
    args = ap.parse_args()
    rows = collect()
    from collections import Counter
    rail_venue = Counter(f"{r['Venue']}/{r['Rail'] or '無'}" for r in rows)
    n_rail = sum(1 for r in rows if r["Rail"])
    print(f"抽到 {len(rows)} 個 runner 行，{n_rail} 個有 rail（{100*n_rail/max(len(rows),1):.0f}%）")
    print("rail×場地 分佈:", dict(rail_venue.most_common(12)))
    if args.summary:
        print("（--summary：未寫 CSV）")
        return 0
    import csv
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cols = ["Date", "RaceNo", "Venue", "Track", "Distance", "Rail", "Draw", "Pos", "Win", "Place"]
    rows.sort(key=lambda r: (r["Date"], r["RaceNo"], r["Draw"]))
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"✅ 寫入 {OUT}（{len(rows)} 行）。每賽日賽後 re-run 累積；儲夠一季+ 就做 rail 入計分 ML 驗證。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
