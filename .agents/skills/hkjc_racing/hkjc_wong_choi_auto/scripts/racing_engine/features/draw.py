import re
import pandas as pd
from pathlib import Path
import scoring
from scoring import BaseScorer

_DRAW_BIAS_CACHE = None

def _get_draw_bias():
    global _DRAW_BIAS_CACHE
    if _DRAW_BIAS_CACHE is not None:
        return _DRAW_BIAS_CACHE
    
    root = Path(".")
    stats_root = root / "Archive_Race_Analysis" / "HK_Racing" / "HKJC_Race_Results_Database" / "comprehensive_stats"
    paths = [
        stats_root / "24_25" / "draw_bias_stats.csv",
        stats_root / "25_26" / "draw_bias_stats.csv"
    ]
    
    frames = [pd.read_csv(p, encoding="utf-8-sig") for p in paths if p.exists()]
    if not frames:
        _DRAW_BIAS_CACHE = {}
        return {}
        
    df = pd.concat(frames, ignore_index=True)
    df["Starts"] = pd.to_numeric(df["Starts"], errors="coerce").fillna(0.0)
    df["Places"] = pd.to_numeric(df["Places"], errors="coerce").fillna(0.0)
    
    def norm_v(v):
        v = str(v).strip()
        if v in ["ST", "Sha Tin", "沙田"]: return "沙田"
        if v in ["HV", "Happy Valley", "跑馬地"]: return "跑馬地"
        return v
        
    df["Venue"] = df["Venue"].apply(norm_v)
    df["Track"] = df["Track"].apply(lambda t: "Turf" if "turf" in str(t).lower() or "草" in str(t) else "AWT")
    
    grouped = df.groupby(["Venue", "Track", "Distance", "Draw"])[["Starts", "Places"]].sum().reset_index()
    records = {}
    for row in grouped.to_dict(orient="records"):
        starts = float(row.get("Starts", 0.0))
        places = float(row.get("Places", 0.0))
        key = (str(row["Venue"]), str(row["Track"]), int(row["Distance"]), int(row["Draw"]))
        if starts > 0:
            records[key] = {
                "starts": starts,
                "place_rate": (places / starts * 100.0)
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
        
        venue_norm = "沙田" if "沙田" in str(venue) or "ShaTin" in str(venue) or "ST" in str(venue) else "跑馬地"
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

        db = _get_draw_bias()
        db_key = (venue_norm, track_norm, distance, draw_num)
        row = db.get(db_key)
        
        if row and row["starts"] >= 15:
            score = row["place_rate"] + scoring.DRAW_MICRO_WEIGHTS.get("stats_base_add", 35.0)
            self.score = round(max(50.0, min(75.0, score)), 2)
            self.reason = f"Stats (PR {row['place_rate']:.1f}%)"
        else:
            self.score = prior_score
            self.reason = "Prior (Starts < 15)"

        return self.score, self.reason
