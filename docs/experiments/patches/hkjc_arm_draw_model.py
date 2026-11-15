"""EXP-20261115-19 arm：檔位分改用檔位模型（取代三級 75/65/50＋欄位調整）。
draw_score = clip(60 + S × (q − 1))，q = 檔位比率（build_table.py；季層 as-of：用今仗所屬季之前嘅季）。
查表次序 L3（場地, 欄位, 路程）→ L2 → L1。S 由 WC_DRAW_S（預設 40，預先登記；另測 25）。
"""
import json
import os
import re

ARM_NAME = f"draw_model_S{os.environ.get('WC_DRAW_S', '40')}"
S = float(os.environ.get("WC_DRAW_S", "40"))
TABLE = os.environ.get("WC_DRAW_TABLE", "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/analysis/draw_model_table.json")
_T = {}


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def dband(dist):
    return "S" if dist <= 1200 else ("M" if dist <= 1650 else "L")


def q_lookup(ctx, draw):
    if not _T:
        _T.update(json.load(open(TABLE)))
    date = str(ctx.get("race_date") or "")[:10]
    tab = _T["seasons"].get(str(season(date))) if re.match(r"\d{4}-\d{2}-\d{2}", date) else None
    tab = tab or _T["all"]
    venue = "HV" if "跑馬地" in str(ctx.get("venue")) or "happy" in str(ctx.get("venue")).lower() else "ST"
    track = str(ctx.get("track") or "")
    awt = "AWT" in track.upper() or "AWT" in str(ctx.get("venue")).upper() or "全天候" in track
    rail = "AWT" if awt else str(ctx.get("course") or "").strip()
    m = re.search(r"\d{3,4}", str(ctx.get("distance") or ""))
    dist = int(m.group()) if m else 0
    dd = min(int(draw), 13)
    surf = "AWT" if awt else "TURF"
    for k in (f"L3|{venue}|{rail}|{dist}|{dd}", f"L2|{venue}|{surf}|{dband(dist)}|{dd}", f"L1|{surf}|{dd}"):
        if k in tab:
            return tab[k], k.split("|")[0]
    return 1.0, "none"


def apply():
    from hkjc_racing_engine.features import draw as dr
    from hkjc_racing_engine import scoring
    cls = next(v for v in vars(dr).values() if isinstance(v, type) and hasattr(v, "compute") and v.__module__ == dr.__name__)

    def compute(self):
        draw = self.horse_data.get("barrier") or self.horse_data.get("draw")
        try:
            d = int(draw)
        except (TypeError, ValueError):
            return 60.0, "Invalid Draw"
        q, lvl = q_lookup(self.race_context or {}, d)
        self.score = scoring.clip_score(60.0 + S * (q - 1.0))
        self.reason = f"檔位模型 q={q:.2f}（{lvl}）"
        return self.score, self.reason
    cls.compute = compute
