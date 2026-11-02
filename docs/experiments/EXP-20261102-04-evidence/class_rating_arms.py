# EXP-20261102-04 判決時用嘅 arm 版本（重建，供重跑）：放返 au_racing_engine/class_rating.py 位置，
# engine 嘅 _class_score 要傳 (career_starts, is_2yo, latest_good, class_drop, metro_from_provincial, proven_z)，
# 即係 commit 29309d9b 嘅 engine_core（加返 _metro_from_provincial／_venue_tier／METRO_VENUE_TOKENS），
# scoring.CLASS_MICRO_WEIGHTS 加返 career0_2yo_bonus 0.84、metro_prov_pen −5.48。
"""AU 官方評分對位維度（`class_weight`）—— 唯一計算位置。

`RacingEngine._class_score`／`_rating_score`／`_weight_score`／`_handicap_weight_proxy`／
`_proven_class_feature` 只係叫呢度，再砌說明。重建記錄：EXP-20261102-04。

維度 = 0.70 × 評分分 + 0.15 × 級數分（`dimensions.py`；級數份額 EXP-20261009-04，forward 中）。

評分分（官方讓磅分，場內相對；讓磅官嘅能力判斷，負磅已經喺入面 —— EXP-20260831-06／20261102 重測）：

    場內 ≥2 匹有評分而本駒有：
        pstdev ≥ 0.5：60 + clip(6 × z, ±12)
        否則：        60 + clip(1.5 × (評分 − 場均), ±6)
    本駒冇評分（或者場內 <2 匹有）→ 代理：
        負磅代理 = 60 + clip(6 × z(分配負磅), ±12)，只限讓磅賽、≥4 匹有負磅、pstdev ≥ 0.3
        混合場（場內 ≥2 匹有評分）兼有負磅代理 → 負磅代理
        冇負磅代理                           → 級數分
        其餘（多數冇評分嘅讓磅賽）          → ½ 級數分 + ½ 負磅代理
        代理用咗級數分就扣返 (0.15/0.70) × (級數分 − 60)，等級數分喺維度入面只計一次（R2x）；
        淨用負磅代理冇用級數分，唔扣（EXP-20261102-04 F1：舊版照扣，令呢批馬維度入面嘅級數份額變零）。

級數分（60 起計）：初出馬 57.7；出賽 1–5 場、上仗跑入場內頭 25% +2.31，否則 −0.82；
    今場獎金 ≤ 上仗 0.7 倍（降班）+2.1。clip 0–100。逐條消融（EXP-20261102-04）：剷走呢三條任何一條都會令
    primary 跌或者分層 CI 全負；全部剷走 top3 capture CI 全負。「兩歲初出 +0.84」（3,283 場只郁 1 場）同
    「省賽轉都會 −5.48」（剷走 Gold、Good 都 +0.03pp）已剷。

高班實績 overlay = 0.5 × z(proven_class)（場內 ≥3 匹有值兼有分散；proven_class 喺 `engine_core`
`horse_proven_class_level` 由往績真班次 × 嗰仗場內名次百分位計）。

負磅分只做顯示（2026-07-30 退出排名）：60；讓磅賽「降班仍輕磅（≤56.5）」或「升班兼高磅（≥58）」−3。
"""
from __future__ import annotations

from .dimensions import CLASS_SCORE_LIVE, CLASS_SCORE_LIVE_WEIGHT, RATING_SCORE_SHARE
from .scoring import CLASS_MICRO_WEIGHTS, PROVEN_CLASS_Z_WEIGHT, clip_score

NEUTRAL = 60.0
RATING_POINTS_PER_SD = 6.0
RATING_CAP = 12.0
RATING_MIN_SD = 0.5
RATING_FLAT_SLOPE = 1.5
RATING_FLAT_CAP = 6.0
WEIGHT_MIN_RUNNERS = 4
WEIGHT_MIN_SD = 0.3
PROVEN_MIN_FIELD = 3


import os
ARMS = frozenset(a for a in os.environ.get("WC_AU_CLASS_ARM", "").upper().split(",") if a)
PROVEN_IN_CLASS_K = 0.5 / (0.3826193901797637 * CLASS_SCORE_LIVE_WEIGHT)


def class_score(career_starts, is_2yo, latest_good, class_drop, metro_from_provincial, proven_z=None):
    w = CLASS_MICRO_WEIGHTS
    adjustments = []
    drop = lambda arm: arm in ARMS or "RALL" in ARMS  # noqa: E731
    if career_starts == 0:
        if not drop("R0"):
            adjustments.append((w["career0_base"] - NEUTRAL, "初出馬未有正式班際證明"))
        if is_2yo and not drop("R0") and not drop("R2"):
            adjustments.append((w["career0_2yo_bonus"], "2歲馬初出常有爆發力"))
    elif career_starts <= 5 and not drop("R5"):
        if latest_good:
            adjustments.append((w["career5_placed_bonus"], "出賽少但上仗跑入場內頭 25%，有進步空間"))
        else:
            adjustments.append((w["career5_unplaced_pen"], "經驗較薄且上仗未跑入場內頭 25%"))
    if class_drop and not drop("C1") and not drop("RD"):
        adjustments.append((w["class_drop_bonus"], "班次有回落"))
    if metro_from_provincial and not drop("C1") and not drop("RM"):
        adjustments.append((w["metro_prov_pen"], "省賽轉都會，鄉鎮賽績含金量成疑"))
    if "C2" in ARMS and proven_z is not None:
        adjustments.append((PROVEN_IN_CLASS_K * proven_z, "高班實績"))
    score = NEUTRAL
    for delta, _ in adjustments:
        score += delta
    return clip_score(score), adjustments


def official_rating_score(rating, avg_rating, stdev):
    """→ (分數, 修正, z 或 None)。`avg_rating` 冇 = 60。"""
    if avg_rating is None:
        return clip_score(NEUTRAL), 0.0, None
    delta = rating - avg_rating
    if stdev >= RATING_MIN_SD:
        z = delta / stdev
        adjustment = max(-RATING_CAP, min(RATING_CAP, z * RATING_POINTS_PER_SD))
    else:
        z = None
        adjustment = max(-RATING_FLAT_CAP, min(RATING_FLAT_CAP, delta * RATING_FLAT_SLOPE))
    return clip_score(NEUTRAL + adjustment), adjustment, z


def weight_proxy(is_handicap, weight, avg_weight, stdev, counted):
    """讓磅官對本駒嘅判斷（負磅 z，同評分同一把尺）；用唔到 → None。

    一定要用**分配負磅**：見習減磅講騎師，唔講馬（EXP-20261014-02）。
    """
    if not is_handicap or weight is None or not avg_weight or counted < WEIGHT_MIN_RUNNERS or stdev < WEIGHT_MIN_SD:
        return None
    z = (weight - avg_weight) / stdev
    return clip_score(NEUTRAL + max(-RATING_CAP, min(RATING_CAP, z * RATING_POINTS_PER_SD)))


def proxy_rating_score(class_proxy, w_proxy, mixed_field):
    """冇評分嘅馬 → (分數, 來源)。來源：weight_only／class_only／class_weight。"""
    if mixed_field and w_proxy is not None:
        return clip_score(w_proxy if "F1" in ARMS else w_proxy - ((CLASS_SCORE_LIVE_WEIGHT / RATING_SCORE_SHARE) * (class_proxy - NEUTRAL) if CLASS_SCORE_LIVE else 0.0)), "weight_only"
    class_once = ((CLASS_SCORE_LIVE_WEIGHT / RATING_SCORE_SHARE) * (class_proxy - NEUTRAL)
                  if CLASS_SCORE_LIVE else 0.0)
    if w_proxy is None:
        return clip_score(class_proxy - class_once), "class_only"
    return clip_score(0.5 * class_proxy + 0.5 * w_proxy - class_once), "class_weight"


def proven_class_z(raw, count, mean, stdev):
    if raw is None or count < PROVEN_MIN_FIELD or mean is None or stdev is None or stdev <= 0:
        return None
    return (raw - mean) / stdev


def proven_class_overlay(z):
    if z is None or "C2" in ARMS:
        return 0.0
    return PROVEN_CLASS_Z_WEIGHT * z


def weight_score(weight, is_handicap, class_drop, class_rise):
    """顯示用（唔入排名）→ (分數, [原因])。"""
    if weight is None:
        return NEUTRAL, []
    if not is_handicap:
        return NEUTRAL, ["非讓磅賽（定磅／WFA 或賽事條件不明），負磅由年齡性別等定，唔反映能力，負磅中性"]
    notes = []
    score = NEUTRAL
    if weight >= 60.0:
        notes.append("頂磅：讓磅官評為本場能力最高之列")
    # 兩條都係方向修正後嘅讓磅官語義（EXP-20260826-03）：降班仍只得輕磅 = 讓磅官睇低佢。
    if class_drop and weight <= 56.5:
        score -= 3
        notes.append("降班仍只獲輕磅，讓磅官對佢評價偏低")
    elif class_rise and weight >= 58.0:
        score -= 3
        notes.append("升班兼高負磅，雙重打擊")
    return clip_score(score), notes
