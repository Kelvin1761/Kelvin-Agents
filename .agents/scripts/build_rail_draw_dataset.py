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
from __future__ import annotations

import os
os.environ.setdefault("PYTHONUTF8", "1")
import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from wongchoi_paths import HK_RACING  # noqa: E402

DB = HK_RACING / "HKJC_Race_Results_Database"
OUT = DB / "comprehensive_stats" / "rail_draw_results.csv"
LEGACY_ARCHIVE = HK_RACING.parent / "Archive_Race_Analysis" / "HK_Racing"
RAIL_RE = re.compile(r'(?:草地|全天候|泥地)\s*[-–]?\s*[「"“]?\s*([ABC](?:\s*\+\s*\d+)?)\s*[」"”]?\s*賽道')
DIST_RE = re.compile(r'(\d{3,4})\s*米')
DATE_RE = re.compile(r'(20\d{2})[-/](\d{2})[-/](\d{2})')
RACE_RE = re.compile(r'Race[_ ](\d+)', re.I)
VENUE_NORM = {
    "ShaTin": "沙田", "Sha Tin": "沙田", "ST": "沙田", "沙田": "沙田",
    "HappyValley": "跑馬地", "Happy Valley": "跑馬地", "HV": "跑馬地", "跑馬地": "跑馬地",
}
OUTPUT_COLUMNS = [
    "Date", "RaceNo", "HorseNo", "Venue", "Track", "Going", "Distance", "Rail",
    "FieldSize", "Draw", "FirstCall", "EarlyGroup", "Pos", "Win", "Place",
]


def normalise_venue(value: Any) -> str:
    text = str(value or "").strip()
    compact = text.replace(" ", "").casefold()
    if "沙田" in text or "shatin" in compact:
        return "沙田"
    if "跑馬地" in text or "happyvalley" in compact:
        return "跑馬地"
    if compact in {"", "unknown", "none", "n/a", "na"}:
        return ""
    return VENUE_NORM.get(text, text)


def normalise_date(value: Any) -> str:
    match = DATE_RE.search(str(value or ""))
    return "-".join(match.groups()) if match else ""


def result_files(
    hk_root: Path = HK_RACING,
    db_root: Path = DB,
    legacy_root: Path = LEGACY_ARCHIVE,
) -> list[Path]:
    """所有本機賽果，包括現役 HK_RACING meeting folders。"""
    files: set[Path] = set()
    patterns = (
        (db_root, "hkjc results */*/full_day_results.json"),
        (hk_root, "*/*全日賽果.json"),
        (hk_root, "*/full_day_results.json"),
        (legacy_root, "*/*全日賽果.json"),
        (legacy_root, "*/full_day_results.json"),
    )
    for base, pattern in patterns:
        if base.exists():
            files.update(path for path in base.glob(pattern) if path.is_file())
    return sorted(files)


def race_rail_dist(race: dict):
    txt = json.dumps(race.get("sectional_times", ""), ensure_ascii=False).replace('\\"', '"')
    rm = RAIL_RE.search(txt)
    dm = DIST_RE.search(txt)
    rail = rm.group(1).replace(" ", "") if rm else None
    dist = int(dm.group(1)) if dm else None
    surf = "AWT" if "全天候" in txt or "泥地" in txt else ("Turf" if "草地" in txt else None)
    if surf == "AWT" and not rail:
        rail = "AWT"
    return rail, dist, surf


def race_going(race: dict[str, Any]) -> str:
    direct = str(race.get("going") or race.get("track_condition") or "").strip()
    if direct:
        return direct
    for row in race.get("sectional_times") or []:
        if not isinstance(row, list):
            continue
        for index, cell in enumerate(row):
            if "場地狀況" not in str(cell):
                continue
            for candidate in row[index + 1:]:
                value = str(candidate or "").strip()
                if value:
                    return value
    return ""


def logic_metadata(result_path: Path, race_number: int) -> dict[str, Any]:
    """Backfill metadata from the pre-race Logic beside a results file."""
    candidates = [result_path.parent / f"Race_{race_number}_Logic.json"]
    candidates.extend(result_path.parent.glob(f"*Race_{race_number}_Logic.json"))
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        context = data.get("race_analysis") if isinstance(data, dict) else None
        if not isinstance(context, dict):
            continue
        distance_match = re.search(r"\d{3,4}", str(context.get("distance") or ""))
        track_text = str(context.get("track") or context.get("surface") or "")
        return {
            "date": normalise_date(context.get("race_date")),
            "venue": normalise_venue(context.get("venue")),
            "rail": str(context.get("rail") or context.get("course") or "").strip(),
            "going": str(context.get("going") or context.get("track_condition") or "").strip(),
            "distance": int(distance_match.group()) if distance_match else None,
            "track": "AWT" if any(token in track_text.casefold() for token in ("awt", "泥", "全天候"))
            else ("Turf" if track_text else None),
        }
    return {}


def racecard_metadata(result_path: Path, race_number: int) -> dict[str, Any]:
    """Last-resort metadata fallback for older result payloads without headers."""
    for path in sorted(result_path.parent.glob("*.md")):
        if not any(token in path.name for token in ("排位表", "Racecard")):
            continue
        race_match = RACE_RE.search(path.name)
        if not race_match or int(race_match.group(1)) != race_number:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rail_match = re.search(
            r"賽道\s*[:：]\s*(?:草地\s*[-–]\s*)?[「\"“]?\s*([ABC](?:\s*\+\s*\d+)?)",
            text,
        )
        distance_match = DIST_RE.search(text)
        is_awt = "全天候" in text or "泥地" in text
        going_match = re.search(r"場地狀況\s*[:：]\s*([^\n|]+)", text)
        return {
            "date": normalise_date(text),
            "venue": "跑馬地" if "跑馬地" in text else ("沙田" if "沙田" in text else ""),
            "rail": rail_match.group(1).replace(" ", "") if rail_match else ("AWT" if is_awt else ""),
            "going": going_match.group(1).strip() if going_match else "",
            "distance": int(distance_match.group(1)) if distance_match else None,
            "track": "AWT" if is_awt else ("Turf" if "草地" in text else None),
        }
    return {}


def meeting_metadata(result_path: Path, race_number: int, race: dict[str, Any]) -> dict[str, Any]:
    rail, distance, track = race_rail_dist(race)
    metadata: dict[str, Any] = {
        "date": normalise_date(race.get("racedate")) or normalise_date(result_path.parent.name),
        "venue": normalise_venue(race.get("venue")),
        "rail": rail,
        "going": race_going(race),
        "distance": distance,
        "track": track,
    }
    for fallback in (logic_metadata(result_path, race_number), racecard_metadata(result_path, race_number)):
        for key, value in fallback.items():
            if metadata.get(key) in (None, "") and value not in (None, ""):
                metadata[key] = value
    if not metadata["venue"]:
        folder_venue = normalise_venue(result_path.parent.name)
        metadata["venue"] = folder_venue if folder_venue in {"沙田", "跑馬地"} else ""
    if metadata.get("track") == "AWT" and not metadata.get("rail"):
        metadata["rail"] = "AWT"
    return metadata


def positive_int(value: Any) -> int:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else 0


def position_group(position: int) -> str:
    if position <= 0:
        return "unknown"
    if position <= 4:
        return "front_1_4"
    if position <= 8:
        return "mid_5_8"
    return "back_9_plus"


def collect(files: Iterable[Path] | None = None):
    rows = {}  # dedup key → row
    for fp in files if files is not None else result_files():
        fp = Path(fp)
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        for race_key, race in data.items():
            if not isinstance(race, dict):
                continue
            try:
                rno = int(race.get("race_no") or race_key)
            except (TypeError, ValueError):
                continue
            metadata = meeting_metadata(fp, rno, race)
            raw_results = race.get("results") if isinstance(race.get("results"), list) else []
            valid_results = [
                row for row in raw_results
                if positive_int(row.get("pos")) > 0 and positive_int(row.get("draw")) > 0
            ]
            field_size = len(valid_results)
            for row in valid_results:
                pos = positive_int(row.get("pos"))
                draw = positive_int(row.get("draw"))
                if pos <= 0 or draw <= 0:
                    continue
                horse_no = str(row.get("horse_no", "")).strip()
                first_call = positive_int(row.get("running_positions"))
                key = (str(metadata.get("date") or ""), str(metadata.get("venue") or ""), rno, horse_no)
                rows[key] = {
                    "Date": metadata.get("date") or "", "RaceNo": rno, "HorseNo": horse_no,
                    "Venue": metadata.get("venue") or "", "Track": metadata.get("track") or "",
                    "Going": metadata.get("going") or "", "Distance": metadata.get("distance") or "",
                    "Rail": metadata.get("rail") or "",
                    "FieldSize": field_size, "Draw": draw, "FirstCall": first_call or "",
                    "EarlyGroup": position_group(first_call),
                    "Pos": pos, "Win": 1 if pos == 1 else 0, "Place": 1 if pos <= 3 else 0,
                }
    return list(rows.values())


def metadata_coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    required = ("Date", "Venue", "Track", "Distance", "Rail")
    def present(row: dict[str, Any], key: str) -> bool:
        value = str(row.get(key) or "").strip()
        if key == "Venue":
            return value in {"沙田", "跑馬地"}
        return bool(value) and value.casefold() not in {"unknown", "none", "n/a", "na"}

    complete = sum(all(present(row, key) for key in required) for row in rows)
    return {
        "rows": len(rows),
        "complete_rows": complete,
        "coverage": complete / len(rows) if rows else 0.0,
        "missing": {key: sum(not present(row, key) for row in rows) for key in required},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", action="store_true", help="只印分佈，唔寫 CSV")
    ap.add_argument("--output", type=Path, default=OUT)
    ap.add_argument("--min-metadata-coverage", type=float, default=0.95)
    ap.add_argument("--allow-incomplete", action="store_true", help="研究 debug 用；容許低覆蓋輸出")
    args = ap.parse_args()
    rows = collect()
    coverage = metadata_coverage(rows)
    print(
        f"抽到 {coverage['rows']} 個 runner 行；完整 rail metadata "
        f"{coverage['complete_rows']} 行（{coverage['coverage']:.1%}）"
    )
    print("缺欄:", coverage["missing"])
    from collections import Counter
    rail_venue = Counter(f"{r['Venue']}/{r['Track']}/{r['Rail'] or '無'}" for r in rows)
    print("rail×場地 分佈:", dict(rail_venue.most_common(16)))
    if args.summary:
        print("（--summary：未寫 CSV）")
        return 0
    if coverage["coverage"] < args.min_metadata_coverage and not args.allow_incomplete:
        print(
            f"❌ metadata coverage {coverage['coverage']:.1%} 低過 gate "
            f"{args.min_metadata_coverage:.1%}；拒絕覆蓋 dataset",
            file=sys.stderr,
        )
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda r: (r["Date"], r["Venue"], r["RaceNo"], r["Draw"]))
    with args.output.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"✅ 寫入 {args.output}（{len(rows)} 行）；研究用，未接入 live scoring。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
