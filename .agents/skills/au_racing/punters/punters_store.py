#!/usr/bin/env python3
"""將 Punters cache 解析落 SQLite。可以隨時由 cache 重建（唔出網）。

兩張主表：
- `selections`：每場比賽每匹馬（賽日、場地、場次、馬名、名次、距離）—— 交叉核對用。
- `forms`：以某個 selection 做「錨」嘅賽前往績段速。
  ⚠️ Punters 對舊 selection 只返**賽前**往績（2026-10-13 實測 08-10 Pakenham R1：
  全部往績 < 08-10）。`check_as_of()` 每次建表都會再驗一次，有違反就 raise。

欄位按「分段終點」命名（2026-10-13 由 1,337 條往績反推）：
- `l600` = 800→600、`l400` = 600→400、`l200` = 400→200、`finish` = 最後 200m —— 四格**每格 200m**；
- `l800` = 去到 800m 標記前嗰段，**長度唔定**：有完整計時係 1000→800（200m），
  冇就係由起步到 800m（例如 1200m 賽事 ≈ 25 秒）。長度 = speed × split / 3.6；
- `*_speed` 係 km/h；`lateSpeed` = finish 段速度；`averageTime` 只係五格平均（冇用）。
所以「最後 600m」= l400 + l200 + finish，唔係 `l600`。

實測長度（split × speed / 3.6，1,337 條）：l400／l200／finish **100%** ≈200m；
l600 93.9%；l800 只有 19.7%。`l600`／`l800` 一定要過 `is_200m()` 先當 200m 段用。
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SEGMENTS = ("l800", "l600", "l400", "l200", "finish")

SCHEMA = """
CREATE TABLE IF NOT EXISTS selections (
  selection_id TEXT PRIMARY KEY, race_date TEXT, meeting_slug TEXT, venue TEXT,
  event_id TEXT, race_no INTEGER, horse TEXT, horse_key TEXT, competitor_id TEXT,
  saddle_no INTEGER, barrier INTEGER, status TEXT, finish_pos INTEGER, margin TEXT,
  -- meetings v2 起。⚠️ pred_* 係 Punters 自己嘅 speed map 預測，舊賽事未證實係賽前版，
  -- 過洩漏檢查（同實際起步位比）之前唔准入模型。
  rating_official REAL, pred_label TEXT, pred_speed REAL, pred_norm_speed REAL,
  pred_barrier_speed TEXT, pred_closing_speed TEXT, pred_width REAL, pred_length REAL,
  pred_finish_speed REAL
);
CREATE TABLE IF NOT EXISTS forms (
  anchor_selection_id TEXT, form_id TEXT, anchor_race_date TEXT,
  meeting_date TEXT, venue TEXT, race_no INTEGER, distance INTEGER, track_type TEXT,
  going TEXT, going_rating INTEGER, finish_pos INTEGER, starters INTEGER, finish_time REAL,
  l800_split REAL, l800_speed REAL, l600_split REAL, l600_speed REAL,
  l400_split REAL, l400_speed REAL, l200_split REAL, l200_speed REAL,
  finish_split REAL, finish_speed REAL,
  early_speed REAL, mid_speed REAL, late_speed REAL, avg_speed REAL, avg_time REAL,
  -- v3 query 起：
  is_trial INTEGER, status_abv TEXT, meeting_name TEXT, class_name TEXT, group_type TEXT,
  margin REAL, second_margin REAL, weight REAL, barrier INTEGER, barrier_row INTEGER,
  barrier_handicap TEXT, prize_money REAL,
  sp_win REAL,              -- ⚠️ 市場數據：未經明確決定唔准入模型（AGENTS.md 證據紀律）
  days_since_last INTEGER, first_up INTEGER, second_up INTEGER, third_up INTEGER,
  jockey TEXT, jockey_id TEXT, trainer TEXT, trainer_id TEXT,
  video_comment TEXT, video_note TEXT, stewards_report TEXT,
  winner TEXT, second TEXT, third TEXT, formline_json TEXT,
  PRIMARY KEY (anchor_selection_id, form_id)
);
CREATE INDEX IF NOT EXISTS forms_anchor ON forms(anchor_selection_id);
CREATE INDEX IF NOT EXISTS sel_race ON selections(race_date, venue, race_no);
"""


def horse_key(name: str) -> str:
    import html
    name = html.unescape(name or "")
    name = re.sub(r"\(.*?\)", "", name)
    return re.sub(r"[^a-z0-9]", "", name.lower())


# Punters 嘅場地縮寫 → 我哋語料嘅寫法（對唔到嘅場次會喺 backfill 尾印出，見到新嘅就加）
VENUE_ALIASES = {"bdge": "bridge"}


def venue_key(name: str) -> str:
    words = re.findall(r"[a-z0-9]+", (name or "").lower())
    return "".join(VENUE_ALIASES.get(w, w) for w in words)


def default_db_path() -> Path:
    import wongchoi_paths
    return Path(wongchoi_paths.AU_RACING) / "_punters" / "punters_sectionals.sqlite"


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = Path(path or default_db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def _num(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


MISSING_SENTINEL = 999.0   # Punters 用 999 代表「冇計時」（2026-10-13：1,337 條有 2 條）


def _seg(v):
    """分段秒數／km/h：999 sentinel、0、負數一律當冇數據。"""
    f = _num(v)
    return None if f is None or f <= 0 or f >= MISSING_SENTINEL else f


def segment_len(split: float | None, speed: float | None) -> float | None:
    """由秒數同 km/h 反推呢段幾多米。"""
    if split is None or speed is None:
        return None
    return split * speed / 3.6


def is_200m(split: float | None, speed: float | None, tol: float = 15.0) -> bool:
    n = segment_len(split, speed)
    return n is not None and abs(n - 200.0) <= tol


def _int(v):
    f = _num(v)
    return None if f is None else int(f)


def ingest_meetings(con, date: str, payload: dict, wanted_slugs: set[str] | None = None) -> int:
    n = 0
    for m in (payload.get("data") or {}).get("meetings") or []:
        if wanted_slugs is not None and m["slug"] not in wanted_slugs:
            continue
        for ev in m.get("events") or []:
            for s in ev.get("selections") or []:
                comp = s.get("competitor") or {}
                pr = s.get("prediction") or {}
                row = {
                    "selection_id": s["id"], "race_date": date, "meeting_slug": m["slug"],
                    "venue": (m.get("venue") or {}).get("name"), "event_id": ev["id"],
                    "race_no": _int(ev.get("eventNumber")), "horse": comp.get("name"),
                    "horse_key": horse_key(comp.get("name")), "competitor_id": comp.get("id"),
                    "saddle_no": _int(s.get("competitorNumber")), "barrier": _int(s.get("barrierNumber")),
                    "status": s.get("status"), "finish_pos": _int(s.get("selectionResult")),
                    "margin": s.get("officialMargin"), "rating_official": _num(s.get("ratingOfficial")),
                    "pred_label": pr.get("speedMeasureRatingName"), "pred_speed": _num(pr.get("speedMeasure")),
                    "pred_norm_speed": _num(pr.get("normSpeedMeasure")),
                    "pred_barrier_speed": pr.get("barrierSpeedRating"),
                    "pred_closing_speed": pr.get("closingSpeedRating"),
                    "pred_width": _num(pr.get("width")), "pred_length": _num(pr.get("length")),
                    "pred_finish_speed": _num(pr.get("finishSpeed")),
                }
                con.execute(f"INSERT OR REPLACE INTO selections ({','.join(row)}) "
                            f"VALUES ({','.join('?' * len(row))})", tuple(row.values()))
                n += 1
    return n


def _bool(v):
    return None if v is None else int(bool(v))


def form_row(anchor: str, anchor_date: str | None, f: dict) -> dict:
    st = f.get("sectionalTime") or {}
    sm = f.get("sectionalTimeSummary") or {}
    row = {
        "anchor_selection_id": anchor, "form_id": f["id"], "anchor_race_date": anchor_date,
        "meeting_date": (f.get("meetingDate") or "")[:10], "venue": (f.get("venue") or {}).get("name"),
        "race_no": _int(f.get("eventNumber")), "distance": _int(f.get("eventDistance")),
        "track_type": f.get("trackType"), "going": f.get("trackCondition"),
        "going_rating": _int(f.get("trackConditionRating")), "finish_pos": _int(f.get("finishPosition")),
        "starters": _int(f.get("eventStarters")), "finish_time": _num(f.get("finishTime")),
        "early_speed": _seg(sm.get("earlySpeed")), "mid_speed": _seg(sm.get("midSpeed")),
        "late_speed": _seg(sm.get("lateSpeed")), "avg_speed": _seg(sm.get("averageSpeed")),
        "avg_time": _seg(sm.get("averageTime")),
        "is_trial": _bool(f.get("isTrial")), "status_abv": f.get("statusAbv"),
        "meeting_name": f.get("meetingName"), "class_name": f.get("eventNameForm"),
        "group_type": f.get("groupType"), "margin": _num(f.get("margin")),
        "second_margin": _num(f.get("secondMarginDecimal")), "weight": _num(f.get("weight")),
        "barrier": _int(f.get("barrier")), "barrier_row": _int(f.get("barrierRow")),
        "barrier_handicap": f.get("barrierHandicap"), "prize_money": _num(f.get("prizeMoney")),
        "sp_win": _num(f.get("startingWinPriceDecimal")),
        "days_since_last": _int(f.get("daysSinceLastRun")), "first_up": _bool(f.get("isFirstUp")),
        "second_up": _bool(f.get("isSecondUp")), "third_up": _bool(f.get("isThirdUp")),
        "jockey": (f.get("jockey") or {}).get("name"), "jockey_id": (f.get("jockey") or {}).get("id"),
        "trainer": (f.get("trainer") or {}).get("name"), "trainer_id": (f.get("trainer") or {}).get("id"),
        "video_comment": f.get("videoComment"), "video_note": f.get("videoNote"),
        "stewards_report": f.get("stewardsReport"), "winner": f.get("winnerName"),
        "second": f.get("secondName"), "third": f.get("thirdName"),
        "formline_json": json.dumps(f["formLine"], ensure_ascii=False) if f.get("formLine") else None,
    }
    for k in SEGMENTS:
        v = st.get(k) or {}
        split, speed = _seg(v.get("split")), _seg(v.get("speed"))
        if split is None or speed is None:
            split = speed = None
        row[f"{k}_split"], row[f"{k}_speed"] = split, speed
    return row


def ingest_forms(con, payload: dict, anchor_dates: dict[str, str]) -> int:
    n = 0
    for cf in (payload.get("data") or {}).get("competitorForms") or []:
        anchor = cf["selectionId"]
        for f in cf.get("forms") or []:
            row = form_row(anchor, anchor_dates.get(anchor), f)
            cols = ",".join(row)
            con.execute(f"INSERT OR REPLACE INTO forms ({cols}) VALUES ({','.join('?' * len(row))})",
                        tuple(row.values()))
            n += 1
    return n


def check_as_of(con) -> int:
    """往績日期一定要早過錨賽日。返違反數；>0 就 raise。"""
    bad = con.execute(
        "SELECT COUNT(*) FROM forms WHERE anchor_race_date IS NOT NULL AND meeting_date >= anchor_race_date"
    ).fetchone()[0]
    if bad:
        raise AssertionError(f"as-of 違反：{bad} 條往績唔早過錨賽日 —— Punters 語義變咗，唔可以用")
    return bad


def rebuild_from_cache(con, cache_dir: Path | None = None) -> dict:
    """由 cache 重建兩張表（唔出網）。只收 AU 場次（剔 `-bt` 試閘同外國）。"""
    from punters_fetch import CACHE_DIR
    cache_dir = Path(cache_dir or CACHE_DIR)
    foreign = re.compile(r"-(?:[a-z]{2})-\d{8}$")
    n_sel = n_form = 0
    from punters_fetch import QUERY_VERSION
    skipped = 0
    for p in sorted(cache_dir.glob("meetingsIndexByStartEndTime_*.json")):
        payload = json.loads(p.read_text())
        if payload.get("_query_version", 1) != QUERY_VERSION["meetingsIndexByStartEndTime"]:
            skipped += 1
            continue
        meets = (payload.get("data") or {}).get("meetings") or []
        if not meets:
            continue
        date = re.search(r"(\d{8})", meets[0]["slug"]).group(1)
        date = f"{date[:4]}-{date[4:6]}-{date[6:]}"
        au = {m["slug"] for m in meets if not m["slug"].endswith("-bt") and not foreign.search(m["slug"])}
        n_sel += ingest_meetings(con, date, payload, au)
    dates = dict(con.execute("SELECT selection_id, race_date FROM selections"))
    want = QUERY_VERSION["getSectionalsBySelectionIds"]
    for p in sorted(cache_dir.glob("getSectionalsBySelectionIds_*.json")):
        payload = json.loads(p.read_text())
        if payload.get("_query_version", 1) != want:   # 舊版 query 缺欄位，唔可以撈埋
            skipped += 1
            continue
        n_form += ingest_forms(con, payload, dates)
    con.commit()
    check_as_of(con)
    return {"selections": n_sel, "forms": n_form, "skipped_old_version": skipped}


if __name__ == "__main__":
    if "--rebuild" in sys.argv:
        print(rebuild_from_cache(connect()))
    con = connect()
    print(json.dumps({t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                      for t in ("selections", "forms")}))
