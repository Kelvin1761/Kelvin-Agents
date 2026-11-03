"""AU 騎練訊號（維度 `jockey_trainer`）—— 騎師分、練馬師分、人馬配搭分嘅唯一計算位置。

維度 = 0.333 騎師分 + 0.286 練馬師分 + 0.381 人馬配搭分（`dimensions.py`）。

騎師分／練馬師分（60 中性；來源 Sportsbet 去年官方 LY，`<kind>_ly`，賽前抽取）：

    LY ≥ 10 場（統一率）：
        騎師   勝率   r = (冠 + 20 × 0.1271) ÷ (場 + 20)   → 60 + 247 × (r − 0.1271)   （冇冠數 → 用下面上名率式）
        練馬師 上名率 r = (上名 + 20 × 0.3673) ÷ (場 + 20) → 60 + 140 × (r − 0.3673)   （騎師上名率 prior 0.3564）
    LY 少過 10 場：
        騎練資料庫 tier（`as_of` 早過賽日）→ tier 嘅 base_score
        騎師再冇 tier 而 LY 有場數 → (上名 + 20 × 0.365) ÷ (場 + 20) → 60 + 100 × (r − 0.365)
    其餘 → 60

    點解騎師用勝率、練馬師用上名率：2026-08-05，713 場場內 AUC 騎師勝率 0.5943 > 上名率 0.5885；
    練馬師以冠軍數為基礎嘅變體全部用 gold 換 champ，所以留上名率。

人馬配搭分（60 起計，`fit_parts`；冇任何證據 → 58）：

    試閘 ≥2 課兼 ≥2 課前列                    +3.38（再配頂級騎／練 +1.0）  ← 搬去試閘備戰維度
    現役騎師曾策騎此駒正式賽                  +min(4.05, 0.31 × 上名次數)
        上名次數 × 2 ≥ 策騎次數                +0.65
        ≥2 騎而上名率 ≥ 66%                    +1.47
    否則現役騎師試閘策騎過而入前三            +min(2.57, 3.8 × 試閘前三次數)
    換騎訊號：沿用歷來最佳配搭 +3.85；試閘手接手 +2.0

    剷走（實測符號反，EXP-20260901-06／EXP-20261016-12）：離開上仗已證明配搭、未及上仗騎師、回配、沿用上仗騎師
    —— 照舊出敘述（標明不入分）。「上仗騎師對此駒往績」連續項 13 個變體都改善唔到排名，已剷。
    冇證據 58：713 場冇配搭紀錄嘅馬前三率 21.7%（平均 28.3%），58 係 holdout 唯一完全唔傷嘅點位。

報告用、唔入分：練馬師同場館往績、同場館騎練組合（`AU_Jockey_Trainer_Combo_Stats.csv`）、首仗／二出往績、見習減磅。
重建記錄：EXP-20261103-05。
"""
from __future__ import annotations

from .scoring import clip_score

NEUTRAL = 60.0
MIN_RUNS = 10
SHRINK_K = 20.0
JOCKEY_WIN_PRIOR, JOCKEY_WIN_SPREAD = 0.1271, 247.0
PLACE_PRIOR = {"jockey": 0.3564, "trainer": 0.3673}
PLACE_SPREAD = 140.0
THIN_JOCKEY_PRIOR, THIN_JOCKEY_SPREAD = 0.365, 100.0
FIT_NO_EVIDENCE = 58.0

# 一個 dict：`au_runtime_micro_ablation` 喺 runtime 逐個 key 改做 0 嚟消融，所以計分時先讀。
FIT_WEIGHTS = {
    "trial_ok_bonus": 3.38,
    "trial_ok_top_jt_bonus": 1.0,
    "current_formal_cap": 4.05,
    "current_formal_mult": 0.31,
    "current_basic_fit_bonus": 0.65,
    "current_high_fit_bonus": 1.47,
    "current_trial_cap": 2.57,
    "current_trial_mult": 3.8,
    "signal_best_jockey_bonus": 3.85,
    "signal_trial_rider_bonus": 2.0,
}
# 呢兩項係試閘證據：`analyze_horse` 會將佢哋由人馬配搭分搬去試閘備戰（`preparation_score`）。
PREPARATION_FACTORS = frozenset({"試閘交代密度足夠", "備戰同騎練配置方向一致"})

TIER_TEXT = {
    "jockey": {"T1": "Tier 1 頂級騎師", "T2": "Tier 2 主力騎師", "T3": "Tier 3 發展型騎師"},
    "trainer": {"T1": "Tier 1 精英馬房", "T2": "Tier 2 主力馬房", "T3": "Tier 3 標準馬房"},
}


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def tier_text(tier, kind):
    return TIER_TEXT[kind].get(str(tier or "").strip(), "中性級別")


def ly_record(ly):
    """`<kind>_ly` → (場, 冠, 上名)；冇 → (0, None, 0)。"""
    ly = ly or {}
    runs = _num(ly.get("rides")) or 0.0
    return runs, _num(ly.get("wins")), _num(ly.get("places")) or 0.0


def rate_score(kind, ly):
    """LY ≥ 10 場嘅統一率 → (分數, 說明)；唔夠場 → None。"""
    runs, wins, places = ly_record(ly)
    if runs < MIN_RUNS:
        return None
    if kind == "jockey" and wins is not None:
        shrunk = (wins + SHRINK_K * JOCKEY_WIN_PRIOR) / (runs + SHRINK_K)
        score = clip_score(NEUTRAL + (shrunk - JOCKEY_WIN_PRIOR) * JOCKEY_WIN_SPREAD)
        return score, (f"去年官方 {int(runs)} 場、{int(wins)} 冠（勝率 {wins / runs * 100:.0f}%，收縮後 "
                       f"{shrunk * 100:.0f}%，全國基準 {JOCKEY_WIN_PRIOR * 100:.0f}%）")
    prior = PLACE_PRIOR[kind]
    shrunk = (places + SHRINK_K * prior) / (runs + SHRINK_K)
    score = clip_score(NEUTRAL + (shrunk - prior) * PLACE_SPREAD)
    return score, (f"去年官方 {int(runs)} 場、上名 {int(places)} 次（原始 {places / runs * 100:.0f}%，"
                   f"收縮後 {shrunk * 100:.0f}%，全國基準 {prior * 100:.0f}%）")


def thin_jockey_score(ly):
    """騎師 LY 少過 10 場（而冇 tier）→ (分數, 收縮率, 場, 上名)；冇場數 → None。"""
    runs, _wins, places = ly_record(ly)
    if runs <= 0:
        return None
    rate = (places + SHRINK_K * THIN_JOCKEY_PRIOR) / (runs + SHRINK_K)
    return clip_score(NEUTRAL + (rate - THIN_JOCKEY_PRIOR) * THIN_JOCKEY_SPREAD), rate, int(runs), places


def venue_note(stats):
    """練馬師同場館往績 → (標籤, 說明) 或者 None。只做報告。"""
    runs, rate = stats.get("runs", 0), stats.get("place_rate", 0.0)
    evidence = f"馬房同場館 {int(runs)} 次、上名率 {rate * 100:.0f}%"
    for min_runs, min_rate, label in ((20, 0.44, "今場場館高密度高上名"), (12, 0.40, "今場場館穩定上名"),
                                      (8, 0.32, "今場場館有基本對位")):
        if runs >= min_runs and rate >= min_rate:
            return label, evidence
    return None


def fit_parts(f):
    """人馬配搭分嘅入分項 → [(加減, 因子, 證據)]，次序同報告一樣。`f` 係 `RacingEngine` 砌好嘅數字。"""
    w = FIT_WEIGHTS
    parts = []
    if f["trial_count"] >= 2 and f["trial_top3"] >= 2:
        parts.append((w["trial_ok_bonus"], "試閘交代密度足夠",
                      f"往績表試閘{f['trial_count']}課、{f['trial_top3']}課跑入試閘前列"))
        if f["top_jt"]:
            parts.append((w["trial_ok_top_jt_bonus"], "備戰同騎練配置方向一致", "試閘密度足夠且配頂級騎/練"))
    rides, places = f["current_rides"], f["current_places"]
    if rides > 0:
        parts.append((min(w["current_formal_cap"], places * w["current_formal_mult"]),
                      f"現役騎師曾策騎此駒 {rides} 次正式賽",
                      f"{f['jockey']}策此駒{rides}次：{f['current_wins']}勝{places}上名"))
        if places * 2 >= max(1, rides):
            parts.append((w["current_basic_fit_bonus"], "現役騎師對此駒有基本交代", f"上名{places}次／{rides}騎"))
        rate = places / rides
        if rides >= 2 and rate >= 0.66:
            parts.append((w["current_high_fit_bonus"], "現役騎師對此駒配合率偏高",
                          f"配合率{rate * 100:.0f}%（{rides}騎)"))
    elif f["current_trial_rides"] > 0 and f["current_trial_top3"] > 0:
        parts.append((min(w["current_trial_cap"], f["current_trial_top3"] * w["current_trial_mult"]),
                      "現役騎師已透過試閘熟習此駒",
                      f"{f['jockey']}試閘策此駒{f['current_trial_rides']}次、{f['current_trial_top3']}次入前三"))
    signal = f["change_signal"]
    if "沿用歷來最佳配搭" in signal:
        parts.append((w["signal_best_jockey_bonus"], "沿用歷來最佳人馬配搭", signal))
    elif "試閘手接手" in signal and not any(k in signal for k in ("較強騎師", "換下較高級騎師", "沿用上仗騎師")):
        parts.append((w["signal_trial_rider_bonus"], "試閘手接手，備戰線完整", signal))
    return parts
