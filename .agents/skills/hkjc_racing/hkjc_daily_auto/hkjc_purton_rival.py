"""「潘頓同場揀咗另一匹」—— 定義嘅唯一真源（EXP-20261111-21）。

一匹馬算 case：佢**上仗**（賽日之前最近一次香港出賽）由潘頓策騎，**今仗**由另一個騎師策騎，
而潘頓今仗喺**同一場**騎緊另一匹馬。

只讀賽果 JSON（`fast_extract_results` 格式），唔郁評分。追蹤表（夠數提醒）同凍結篩選腳本都用呢度，
所以兩邊數嘅係同一批馬。

資料來源（逐日去重，同一日只讀一份）：
  * <HK root>/<YYYY-MM-DD>_<場地>/*全日賽果.json
  * <HK root>/HKJC_Race_Results_Database/<季度>/<YYYY-MM-DD>/full_day_results.json
  * 額外 roots（例如 `_research_old_season_results/<YYYY-MM-DD>.json`）
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable

PURTON = "潘頓"
_BRAND = re.compile(r"\(([A-Z]\d{3})\)\s*$")
_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _clean_jockey(name: str) -> str:
    return re.sub(r"\s*\(-\d+\)\s*$", "", str(name or "")).strip()


def _day_files(root: Path, extra: Iterable[Path] = ()) -> dict[str, Path]:
    """date -> one results file (meeting folder first, then DB, then extra)."""
    found: dict[str, Path] = {}
    candidates = list(sorted(root.glob("20[0-9][0-9]-[0-9][0-9]-[0-9][0-9]_*/*全日賽果.json")))
    candidates += sorted((root / "HKJC_Race_Results_Database").glob("*/20[0-9][0-9]-*/full_day_results.json"))
    for base in extra:
        candidates += sorted(Path(base).glob("20[0-9][0-9]-[0-9][0-9]-[0-9][0-9].json"))
    for path in candidates:
        m = _DATE.match(path.parent.name) or _DATE.match(path.name)
        if m and m.group(1) not in found:
            found[m.group(1)] = path
    return found


def load_runs(root: Path, extra: Iterable[Path] = ()) -> list[dict]:
    """Every finished HK run, one row per (date, race, horse), sorted by date then race."""
    runs = []
    for date, path in sorted(_day_files(root, extra).items()):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for race_key, race in payload.items():
            if not isinstance(race, dict) or not race.get("results"):
                continue
            try:
                race_no = int(race.get("race_no") or race_key)
            except (TypeError, ValueError):
                continue
            for row in race["results"]:
                brand = _BRAND.search(str(row.get("horse_name", "")))
                try:
                    pos = int(str(row.get("pos", "")).strip())
                except ValueError:
                    pos = None  # 退出／未完成：唔係出賽結果，但都要記低騎師（佢冇跑）
                try:
                    odds = float(row.get("win_odds"))
                except (TypeError, ValueError):
                    odds = None
                if not brand:
                    continue
                runs.append({
                    "date": date, "race": race_no, "horse": brand.group(1),
                    "horse_no": str(row.get("horse_no", "")).strip(),
                    "jockey": _clean_jockey(row.get("jockey")), "pos": pos, "odds": odds,
                })
    runs.sort(key=lambda r: (r["date"], r["race"]))
    return runs


def tag_runs(runs: list[dict]) -> list[dict]:
    """Adds `prev_jockey` and `purton_rival` to every finished run (history strictly before the race date)."""
    by_race = defaultdict(set)
    for r in runs:
        if r["pos"] is not None:
            by_race[(r["date"], r["race"])].add(r["jockey"])
    last: dict[str, str] = {}
    out = []
    i = 0
    while i < len(runs):
        date = runs[i]["date"]
        j = i
        while j < len(runs) and runs[j]["date"] == date:
            j += 1
        day = runs[i:j]
        for r in day:
            if r["pos"] is None:
                continue
            prev = last.get(r["horse"])
            r = dict(r, prev_jockey=prev)
            r["purton_rival"] = (prev == PURTON and r["jockey"] != PURTON
                                 and PURTON in by_race[(r["date"], r["race"])])
            out.append(r)
        for r in day:  # 成日處理完先更新：同日唔會睇到自己
            if r["pos"] is not None:
                last[r["horse"]] = r["jockey"]
        i = j
    return out


def rival_cases(root: Path, since: str = "", extra: Iterable[Path] = ()) -> list[dict]:
    return [r for r in tag_runs(load_runs(root, extra)) if r["purton_rival"] and r["date"] >= since]
