"""EXP-20261014-11 arms. Mode from env DRAW_ARM = replace | blend | neutral.

Pre-registered: res = Place - min(3,F)/F; cell = venue x surface x rail(turf) x distance x draw;
window = current + 2 previous HK seasons (Sept 1 start), Date < race date;
excess = sum(res)/(n+60); official = clip(60 + 270*excess, 35, 85); n == 0 -> keep live score.
"""
import os
import re
from functools import lru_cache

import numpy as np
import pandas as pd

ARM = os.environ.get("DRAW_ARM", "replace")
ARM_NAME = f"official_draw_{ARM}"
RESULTS = ("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing/"
           "HKJC_Race_Results_Database/comprehensive_stats/rail_draw_results.csv")
SHRINK = 60.0
K = 270.0
LOG = os.environ.get("DRAW_ARM_LOG")


@lru_cache(maxsize=1)
def _frame():
    df = pd.read_csv(RESULTS, encoding="utf-8-sig", dtype=str)
    df["Distance"] = pd.to_numeric(df.Distance, errors="coerce")
    df["Draw"] = pd.to_numeric(df.Draw, errors="coerce")
    field = pd.to_numeric(df.FieldSize, errors="coerce").clip(lower=1)
    df["res"] = pd.to_numeric(df.Place, errors="coerce").fillna(0) - np.minimum(3.0, field) / field
    df["Rail"] = df.Rail.fillna("").str.replace(" ", "").str.upper()
    df = df[df.Venue.isin(["沙田", "跑馬地"]) & df.Track.isin(["Turf", "AWT"]) & field.notna()]
    return df


def _season_start(date):
    y, m = int(date[:4]), int(date[5:7])
    start_year = y if m >= 9 else y - 1
    return f"{start_year - 2}-09-01"


@lru_cache(maxsize=4096)
def official_excess(venue, track, rail, dist, draw, date):
    df = _frame()
    s = df[(df.Venue == venue) & (df.Track == track) & (df.Distance == dist) & (df.Draw == draw)
           & (df.Date >= _season_start(date)) & (df.Date < date)]
    if track == "Turf":
        s = s[s.Rail == rail]
    if len(s) == 0:
        return None, 0
    return float(s.res.sum()) / (len(s) + SHRINK), len(s)


def _ctx(rc):
    v = str(rc.get("venue") or "")
    venue = "跑馬地" if ("跑馬地" in v or "happy" in v.lower() or v.upper() == "HV") else "沙田"
    t = " ".join(str(rc.get(k) or "") for k in ("track", "surface", "track_type"))
    track = "AWT" if any(x in t.upper() for x in ("AWT", "ALL WEATHER")) or "全天候" in t or "泥" in t else "Turf"
    m = re.search(r"\d{3,4}", str(rc.get("distance") or ""))
    rail = str(rc.get("rail") or "").replace(" ", "").upper()
    return venue, track, rail, int(m.group()) if m else 0, str(rc.get("race_date") or "")[:10]


def apply():
    from hkjc_racing_engine import engine_core, scoring

    cls = engine_core.DrawScorer  # engine_core 用 `from draw import DrawScorer`，要 patch 佢手上嗰個
    original = cls.compute

    def compute(self):
        live, reason = original(self)
        if ARM == "neutral":
            self.score = 60.0
            return 60.0, "neutral arm"
        try:
            draw = int(self.horse_data.get("barrier") or self.horse_data.get("draw"))
        except (TypeError, ValueError):
            return live, reason
        venue, track, rail, dist, date = _ctx(self.race_context)
        if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", date) or not dist or (track == "Turf" and not rail):
            out = live
            n = -1
        else:
            exc, n = official_excess(venue, track, rail, dist, draw, date)
            if exc is None:
                out = live
            else:
                off = float(np.clip(60.0 + K * exc, 35.0, 85.0))
                out = off if ARM == "replace" else 0.5 * live + 0.5 * off
        out = scoring.clip_score(out)
        if LOG:
            with open(LOG, "a", encoding="utf-8") as fh:
                fh.write(f"{date}\t{venue}\t{track}\t{rail}\t{dist}\t{draw}\t{n}\t{live:.4f}\t{out:.4f}\n")
        self.score = out
        return out, f"{reason} | official-style {ARM}"

    cls.compute = compute
