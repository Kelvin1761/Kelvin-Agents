import re
import pandas as pd
from pathlib import Path
import scoring
from scoring import BaseScorer

_PROJECT_ROOT = Path(__file__).resolve().parents[7]
import sys as _sys; _sys.path.insert(0, str(_PROJECT_ROOT))
from wongchoi_paths import HK_RACING

_DRAW_BIAS_CACHE = None

def _get_draw_bias():
    global _DRAW_BIAS_CACHE
    if _DRAW_BIAS_CACHE is not None:
        return _DRAW_BIAS_CACHE

    # The draw-bias CSVs live under HK_RACING (data root).
    stats_root = HK_RACING / "HKJC_Race_Results_Database" / "comprehensive_stats"
    candidates = []
    if stats_root.exists():
        candidates = [stats_root / "24_25" / "draw_bias_stats.csv",
                      stats_root / "25_26" / "draw_bias_stats.csv"]

    frames = [pd.read_csv(p, encoding="utf-8-sig") for p in candidates if p.exists()]
    if not frames:
        _DRAW_BIAS_CACHE = {}
        return {}
        
    df = pd.concat(frames, ignore_index=True)
    df["Starts"] = pd.to_numeric(df["Starts"], errors="coerce").fillna(0.0)
    df["Places"] = pd.to_numeric(df["Places"], errors="coerce").fillna(0.0)
    df["Wins"] = pd.to_numeric(df.get("Wins", 0), errors="coerce").fillna(0.0)
    
    def norm_v(v):
        v = str(v).strip()
        if v in ["ST", "Sha Tin", "沙田"]: return "沙田"
        if v in ["HV", "Happy Valley", "跑馬地"]: return "跑馬地"
        return v
        
    df["Venue"] = df["Venue"].apply(norm_v)
    df["Track"] = df["Track"].apply(lambda t: "Turf" if "turf" in str(t).lower() or "草" in str(t) else "AWT")
    
    grouped = df.groupby(["Venue", "Track", "Distance", "Draw"])[["Starts", "Places", "Wins"]].sum().reset_index()
    records = {}
    for row in grouped.to_dict(orient="records"):
        starts = float(row.get("Starts", 0.0))
        places = float(row.get("Places", 0.0))
        wins = float(row.get("Wins", 0.0))
        key = (str(row["Venue"]), str(row["Track"]), int(row["Distance"]), int(row["Draw"]))
        if starts > 0:
            records[key] = {
                "starts": starts,
                "place_rate": (places / starts * 100.0),
                "win_rate": (wins / starts * 100.0),
            }
            
    _DRAW_BIAS_CACHE = records
    return _DRAW_BIAS_CACHE

class DrawScorer(BaseScorer):
    def compute(self):
        draw = self.horse_data.get("barrier") or self.horse_data.get("draw")
        try:
            draw_num = int(draw)
        except (ValueError, TypeError):
            return 60.0, "Invalid Draw"

        venue = self.race_context.get("venue", "")
        track = self.race_context.get("track", "")
        dist_str = str(self.race_context.get("distance") or "0")
        m = re.search(r"(\d+)", dist_str)
        distance = int(m.group(1)) if m else 0
        
        v = str(venue).strip()
        v_low = v.lower().replace(" ", "")
        venue_norm = "沙田" if ("沙田" in v or "shatin" in v_low or v.upper() == "ST") else "跑馬地"
        track_norm = "AWT" if "awt" in str(track).lower() or "dirt" in str(track).lower() or "泥" in str(track) else "Turf"
        
        is_straight = distance == 1000 and track_norm == "Turf" and venue_norm == "沙田"
        if is_straight:
            p_high = scoring.DRAW_MICRO_WEIGHTS.get("straight_draw_8_plus", 75.0)
            p_mid = scoring.DRAW_MICRO_WEIGHTS.get("straight_draw_5_7", 65.0)
            p_low = scoring.DRAW_MICRO_WEIGHTS.get("straight_draw_1_4", 50.0)
            prior_score = p_high if draw_num >= 8 else (p_mid if draw_num >= 5 else p_low)
        else:
            p_high = scoring.DRAW_MICRO_WEIGHTS.get("turn_draw_1_4", 75.0)
            p_mid = scoring.DRAW_MICRO_WEIGHTS.get("turn_draw_5_8", 65.0)
            p_low = scoring.DRAW_MICRO_WEIGHTS.get("turn_draw_9_plus", 50.0)
            prior_score = p_high if draw_num <= 4 else (p_mid if draw_num <= 8 else p_low)

        # ML-validated 2026-07-02（13賽日/131場，train/test 一致）：用歷史檔位
        # place_rate 取代 prior 公式係淨負累 — TEST 及格 32.1→43.4、良 +2.3pp、
        # top3_champ +6.9pp 全部喺熄咗實證取代之後先出現（同 AU barrier-bias
        # net-negative 同一 pattern）。檔位統計只保留俾報告顯示（_draw_stats_note），
        # 唔再入評分。
        self.score = prior_score
        self.reason = "Prior formula"

        return self.score, self.reason
