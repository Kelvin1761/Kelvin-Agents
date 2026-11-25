#!/usr/bin/env python3
"""AU Betfair BSP：載入（記錄器＋公開 CSV）同配對去 dump（EXP-20261124-92）。

BSP 係開跑前「以 SP 落」可執行嘅價，**只做評估基準／結算**：唔入模型、唔揀注。

來源（兩個都讀，同一匹以記錄器為準）：
  1. `au_betfair_logger.py` 每晚結算（2026-11-06 起；EXP-20261124-91 修好 BSP）：
     `<LOG_ROOT>/<悉尼日期>/catalogue.jsonl` + `settle.jsonl`（攞每個市場最後一行）。
  2. Betfair 公開 BSP CSV（`dwbfpricesaus{win,place}DDMMYYYY.csv`，人手下載）：
     預設 `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/betting/betfair_bsp*`。

配對鍵：(日期, 場地, 場次, 馬名)；後備：(日期, 馬名) 而且同場次號唯一。照搬 EXP-20261124-60 嘅做法。
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

LOG_ROOT = Path("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/betfair-market-log")
CSV_GLOB_ROOT = Path("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/betting")
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def norm(text) -> str:
    """馬名／場地 → 細階字母數字；剷走前面「8. 」號碼。"""
    return re.sub(r"[^a-z0-9]", "", re.sub(r"^\s*\d+\.\s*", "", str(text or "")).lower())


def _price(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f > 1 else None


def _put(index: dict, key: tuple, kind: str, price, *, override: bool) -> None:
    rec = index.setdefault(key, {})
    if override or rec.get(kind) is None:
        rec[kind] = price


def load_csv(dirs, index: dict | None = None) -> dict:
    """公開 CSV → {(date, venue, race, horse): {"win": p, "place": p}}。"""
    index = {} if index is None else index
    for d in dirs:
        race_at = {}   # PLACE 嘅 event_name 係「To Be Placed」冇場次號，要由同場地同時間嘅 WIN 對返
        for kind in ("win", "place"):
            for path in sorted(Path(d).glob(f"dwbfpricesaus{kind}*.csv")):
                with open(path, newline="", encoding="utf-8", errors="replace") as fh:
                    for r in csv.DictReader(fh):
                        m = re.match(r"(.+?) \(AUS\) ", r.get("menu_hint") or "")
                        dt = re.match(r"(\d{2})-(\d{2})-(\d{4})", r.get("event_dt") or "")
                        if not m or not dt:
                            continue
                        slot = (norm(m.group(1)), r.get("event_dt"))
                        rn = re.match(r"R(\d+)\b", r.get("event_name") or "")
                        if kind == "win" and rn:
                            race_at[slot] = int(rn.group(1))
                        race_no = int(rn.group(1)) if rn else race_at.get(slot)
                        if race_no is None:
                            continue
                        # event_dt 係 UTC（例：08:32）；AU 賽事 UTC 日期同悉尼日期一樣（UTC 早上 = 悉尼下晝／夜晚），
                        # 但菜單「31st Aug」先係當地賽日 —— 用 menu_hint 嘅日，年份由 event_dt 攞
                        day = re.search(r"\) (\d+)\w* (\w{3})", r.get("menu_hint") or "")
                        if not day or day.group(2) not in MONTHS:
                            continue
                        date = f"{dt.group(3)}-{MONTHS[day.group(2)]:02d}-{int(day.group(1)):02d}"
                        key = (date, norm(m.group(1)), race_no, norm(r.get("selection_name")))
                        _put(index, key, kind, _price(r.get("bsp")), override=False)
    return index


def load_logger(root: Path = LOG_ROOT, index: dict | None = None) -> dict:
    """記錄器 → 同一個 index 格式；記錄器嘅價覆蓋 CSV。"""
    index = {} if index is None else index
    for folder in sorted(p for p in Path(root).glob("20*") if p.is_dir()):
        cat = {}
        for line in _lines(folder / "catalogue.jsonl"):
            cat[line["market"]] = line
        settle = {}
        for line in _lines(folder / "settle.jsonl"):
            if line.get("status") == "CLOSED":
                settle[line["market"]] = line          # 最後一行（重新結算會 append）
        races = {}   # (event_id, start) → 場次號（PLACE 市場名冇場次號）
        for m in cat.values():
            rn = re.match(r"R(\d+)\b", m.get("name") or "")
            if (m.get("type") or "WIN") == "WIN" and rn:
                races[(m.get("event_id"), m.get("start"))] = int(rn.group(1))
        for mid, m in cat.items():
            s = settle.get(mid)
            race_no = races.get((m.get("event_id"), m.get("start")))
            if not s or race_no is None:
                continue
            kind = "win" if (m.get("type") or "WIN") == "WIN" else "place"
            names = {r["id"]: r.get("name") for r in m.get("runners") or []}
            venue = norm(m.get("venue") or re.sub(r" \(AUS\).*", "", m.get("event") or ""))
            for r in s.get("runners") or []:
                if r.get("status") == "REMOVED" or r.get("id") not in names:
                    continue
                key = (folder.name, venue, race_no, norm(names[r["id"]]))
                _put(index, key, kind, _price(r.get("bsp")), override=True)
    return index


def _lines(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def default_csv_dirs() -> list[Path]:
    return sorted(p for p in CSV_GLOB_ROOT.glob("betfair_bsp*") if p.is_dir())


def load_all(log_root: Path = LOG_ROOT, csv_dirs=None) -> dict:
    index = load_csv(default_csv_dirs() if csv_dirs is None else csv_dirs)
    return load_logger(log_root, index)


def dump_venue(meeting: str) -> str:
    """dump 嘅 meeting（'2026-08-05 Flemington Race 1-9'／'2026-08-05_Flemington_Race_1'）→ 場地 norm。"""
    v = re.sub(r"^\d{4}-\d{2}-\d{2}[ _]", "", meeting or "")
    return norm(re.split(r"[ _]Race", v)[0])


def attach(races: list[dict], index: dict) -> dict:
    """將 BSP 寫入每匹 row["bsp"]（獨贏）同 row["bsp_place"]。→ 配對統計。"""
    by_horse = defaultdict(list)
    for key, rec in index.items():
        by_horse[(key[0], key[3])].append((key, rec))
    stats = {"rows": 0, "exact": 0, "fallback": 0, "miss": 0, "races_complete": 0, "races": 0}
    for r in races:
        venue = dump_venue(r.get("meeting", ""))
        complete = True
        for x in r["rows"]:
            stats["rows"] += 1
            rec = index.get((r["date"], venue, r["race"], norm(x.get("name"))))
            if rec is not None:
                stats["exact"] += 1
            else:
                c = [v for k, v in by_horse.get((r["date"], norm(x.get("name"))), []) if k[2] == r["race"]]
                rec = c[0] if len(c) == 1 else None
                stats["fallback" if rec else "miss"] += 1
            x["bsp"] = (rec or {}).get("win")
            x["bsp_place"] = (rec or {}).get("place")
            complete &= x["bsp"] is not None
        stats["races"] += 1
        stats["races_complete"] += complete
    return stats


def place_terms(root: Path = LOG_ROOT) -> dict[tuple[str, str, int], int]:
    """→ {(日期, 場地 norm, 場次): Betfair 位置盤派幾多個位（numberOfWinners）}。由記錄器快照攞（2026-11-06 起）。

    價差測試（EXP-20261121-31）用：Sportsbet 同 Betfair 位置規則唔一樣，兩個價就唔係同一隻注（Astra 2026-11-25）。
    """
    out: dict[tuple[str, str, int], int] = {}
    for folder in sorted(p for p in Path(root).glob("20*") if p.is_dir()):
        cat = {m["market"]: m for m in _lines(folder / "catalogue.jsonl")}
        races = {}
        for m in cat.values():
            rn = re.match(r"R(\d+)\b", m.get("name") or "")
            if (m.get("type") or "WIN") == "WIN" and rn:
                races[(m.get("event_id"), m.get("start"))] = int(rn.group(1))
        winners: dict[str, int] = {}
        for snap in _lines(folder / "snapshots.jsonl"):
            w = snap.get("winners")
            if isinstance(w, int) and w > 0:
                winners[snap.get("market")] = w
        for mid, m in cat.items():
            if (m.get("type") or "WIN") != "PLACE" or mid not in winners:
                continue
            race_no = races.get((m.get("event_id"), m.get("start")))
            if race_no is None:
                continue
            venue = norm(m.get("venue") or re.sub(r" \(AUS\).*", "", m.get("event") or ""))
            out[(folder.name, venue, race_no)] = winners[mid]
    return out
