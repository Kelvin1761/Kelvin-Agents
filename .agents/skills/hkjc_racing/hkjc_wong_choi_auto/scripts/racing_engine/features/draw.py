import re
import scoring
from scoring import BaseScorer

# 檔位評分 = 位置先驗公式（1-4檔好 / 直路8+好）。
# ⚠️ 2026-07-05 backtest（RICH 131場 + 高覆蓋 60場，harness 重現 production baseline）：
#    將 HKJC 官方檔位數據入評分——無論用 verdict tier(有利/中性/不利)、上位率+35、
#    上位率 steep、定 hybrid——喺 benchmark(good/min) 全部輸畀呢個位置先驗
#    （高覆蓋組 good −5~−7pp、min −5~−8pp），甚至同「一律 neutral」差唔多。
#    原因：官方檔位上位率係細樣本+混質雜訊；排名只需穩定嘅位置梯度，馬匹實力由其餘
#    6 個 7D 維度負責。同 2026-07-02 ML 結論一致。故評分保留先驗；HKJC 官方數據
#    只用於「顯示」(數據判讀 _draw_stats_note + 詳細分析 draw_verdict)，不入評分。
# 舊 _get_draw_bias() 讀自家 draw_bias_stats.csv 亦已移除。

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

        self.score = prior_score
        self.reason = "Prior formula"

        return self.score, self.reason
