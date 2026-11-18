"""歷史回放：馬匹頁往績改由存檔馬匹頁（parsed/horses.jsonl.gz）供應（EXP-20261118-03）。

live 嘅 `hkjc_auto_orchestrator._enrich_profile_history` 用排位表 trackwork 嘅 horseid 上 HKJC 抓馬匹頁，
再砌 `_data.hk_history`（轉場組件 K2）同 `_data.prev_distance`（大幅增程組件 D1）。
回放語料嘅 Logic 冇 horseid，所以以前回放入面兩個組件**完全冇郁**（1,676／1,676 匹冇往績），
而且就算有 horseid 都會即時上網抓（48 小時 cache），結果睇網絡同 cache 狀態。

呢度：
  * 用賽果（同日、同馬名）搵返馬匹編號，暫時塞入 trackwork.horseid，叫**原版** `_enrich_profile_history`，
    所以回放同 live 行同一段 code（as-of 過濾、新→舊、40 場上限、prev_distance 全部一樣）；
  * 抓頁換成讀存檔（同一個 HKJC 馬匹頁來源，parsed 過），永遠唔上網。
用法：`install()`，喺 harness import orchestrator 之後、評分之前叫。
"""
from __future__ import annotations

import gzip
import json
import re
from functools import lru_cache
from pathlib import Path

ARCHIVE = Path("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/parsed/horses.jsonl.gz")


def _int(x):
    try:
        return int(str(x).strip())
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=1)
def _archive() -> dict:
    """馬匹編號（例如 C127）→ scraper 格式 entries（新 → 舊）。"""
    out = {}
    if not ARCHIVE.exists():
        raise FileNotFoundError(f"回放馬匹頁存檔唔見咗（外置碟冇掛載？）：{ARCHIVE}")
    for line in gzip.open(ARCHIVE, "rt", encoding="utf-8"):
        r = json.loads(line)
        code = str(r.get("horse_id") or "").rsplit("_", 1)[-1]
        ents = []
        for q in r.get("runs") or []:
            d = str(q.get("date") or "")
            if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", d):
                continue
            ents.append({
                "date": d, "venue_track": q.get("venue_track"), "distance": _int(q.get("distance")),
                "class_grade": str(q.get("class") or "").strip(), "placing": _int(q.get("pos")),
                "jockey": q.get("jockey"), "weight_carried": _int(q.get("actual_wt")), "rating": _int(q.get("rating")),
            })
        ents.sort(key=lambda e: (e["date"][6:], e["date"][3:5], e["date"][:2]), reverse=True)
        out[code] = ents
    return out


@lru_cache(maxsize=1)
def _name_index() -> dict:
    """(日期, 馬名) → 馬匹編號，來自回放賽果（hkjc_history_replay_pit）。"""
    import hkjc_history_replay_pit as p
    df = p.load_all_rows_extended()
    idx = {}
    for date, horse, hid in zip(df["Date"].astype(str), df["Horse"].astype(str), df["HorseID"].astype(str)):
        name = re.sub(r"\(.*\)$", "", horse).strip()
        idx[(date[:10], name)] = hid
    return idx


def _scraper(horse_id: str) -> dict:
    return {"horse_id": horse_id, "entries": list(_archive().get(horse_id, [])), "age": None, "error": None}


def install() -> None:
    import hkjc_auto_orchestrator as orch
    original = orch._enrich_profile_history
    if getattr(original, "_replay_profile", False):
        return
    orch._get_profile_scraper = lambda: _scraper

    def enrich(horses, *, as_of_date=None):
        injected = []
        if as_of_date is not None:
            idx = _name_index()
            for h in (horses or {}).values():
                if not isinstance(h, dict):
                    continue
                tw = h.get("trackwork")
                if isinstance(tw, dict) and tw.get("horseid"):
                    continue
                hid = idx.get((as_of_date.isoformat(), str(h.get("horse_name") or "").strip()))
                if not hid:
                    continue
                if not isinstance(tw, dict):
                    tw = {}
                    h["trackwork"] = tw
                    injected.append((h, None))
                else:
                    injected.append((h, tw))
                tw["horseid"] = hid
        try:
            original(horses, as_of_date=as_of_date)
        finally:
            for h, tw in injected:         # 還原：唔好令 trackwork 多咗嘢（晨操分讀 trackwork）
                if tw is None:
                    h.pop("trackwork", None)
                else:
                    tw.pop("horseid", None)

    enrich._replay_profile = True
    orch._enrich_profile_history = enrich
