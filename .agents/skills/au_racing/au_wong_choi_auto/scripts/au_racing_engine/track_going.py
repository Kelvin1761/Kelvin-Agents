"""AU 場地與地況適性（維度 `track`）＋ 濕地 overlay —— 唯一計算位置（EXP-20261102-10）。

`RacingEngine._track_score`／`_going_adjustment`／`_wet_state` 同綜合分嘅濕地 overlay 只係叫呢度。

今場地況分級（`wet_state`）：Heavy → heavy；Soft 7+ → soft7plus；Soft 5–6 → soft56；其他（包括冇數字）→ ""。
地況 bucket：Heavy／重 → 重地；Soft／軟 → 軟地；其餘 → 好地。

場地分 = 60 + 同場往績 + 地況往績 + 爛地專項，clip 0–100：

    同場：有上名 → min(9, 上名 × 5.0 + 贏 × 2.4)；≥2 戰 0 上名 → −8.81；1 戰 0 上名 → −0.81
    今場地況 bucket：有上名 → min(10, 上名 × 0.8)（濕地兼曾贏 +3.77）；
                    ≥2 戰 0 上名 → 濕 −4.75／乾 −3.46；1 戰 0 上名 → 濕 −4.14／乾 −3.0
                    （好地 bucket 永遠冇數：Facts 第一段冇「好地:」標籤，好地往績只做報告）
    Soft 7+／Heavy：冇任何濕地上名 → −6.4；Heavy 兼有濕地上名：重地曾贏 +3.87，否則重地曾上名 +2.0，
                    否則重地 ≥2 戰 0 上名 −5.94

濕地 overlay（直接加落綜合分；`scoring.wet_form_feature`）：今日地況含 soft／heavy 先開；
    今日嗰個濕地 bucket 全份、另一個半份；率 = (上名 + 4 × 0.3758) ÷ (出賽 + 4)；
    14.852 × (率 − 0.3758)，封頂 ±6.1818。冇濕地出賽 = 0。
"""
from __future__ import annotations

import os
import re

from .scoring import TRACK_MICRO_WEIGHTS, clip_score, wet_form_feature

NEUTRAL = 60.0
# EXP-20261102-10 判決用 arm 開關（逗號分隔）；判完會拆走。
ARMS = frozenset(a for a in os.environ.get("WC_AU_TRACK_ARM", "").upper().split(",") if a)


def wet_state(going):
    m = re.search(r"(Soft|Heavy)\s*([0-9]+)", str(going or ""), re.I)
    if not m:
        return ""
    if m.group(1).lower() == "heavy":
        return "heavy"
    level = int(m.group(2))
    return "soft7plus" if level >= 7 else "soft56" if level >= 5 else ""


def going_bucket(going):
    g = str(going or "")
    if "Heavy" in g or "重" in g:
        return "重地"
    if "Soft" in g or "軟" in g:
        return "軟地"
    return "好地"


def same_track_parts(stats):
    """stats：{starts, wins, places}（同場）→ [(加減, 說明)]。"""
    w = TRACK_MICRO_WEIGHTS
    if "ST" in ARMS:
        return []
    if stats["places"] > 0:
        return [(min(9, stats["places"] * w["same_track_place_bonus"] + stats["wins"] * w["same_track_win_bonus"]),
                 "同場有實際上名支持")]
    if "STP" in ARMS:
        return []
    if stats["starts"] >= 2:
        return [(w["same_track_poor_pen1"], "同場已有多次出賽但仍未交到成績")]
    if stats["starts"] > 0:
        return [(w["same_track_poor_pen2"], "有同場出賽紀錄但仍未交到成績")]
    return []


def going_parts(going_stats, bucket, state):
    """地況適應：今場 bucket 往績 ＋ 爛地專項 → [(加減, 說明)]。going_stats：{好地／軟地／重地: stats}。"""
    w = TRACK_MICRO_WEIGHTS
    sample = going_stats.get(bucket, {})
    wet_bucket = bucket in {"軟地", "重地"}
    parts = []
    if "GO" not in ARMS:
        if sample.get("starts", 0) > 0 and sample.get("places", 0) > 0:
            parts.append((min(10, sample["places"] * w["going_place_bonus"]),
                          f"{bucket}有上名（{sample['places']}／{sample['starts']}）"))
            if sample.get("wins", 0) > 0 and wet_bucket:
                parts.append((w["going_win_bonus"], f"{bucket}曾贏"))
        elif sample.get("starts", 0) >= 2 and sample.get("places", 0) == 0:
            parts.append((w["going_poor_pen1_wet"] if wet_bucket else w["going_poor_pen1_dry"],
                          f"{bucket} {sample['starts']} 戰未有前列"))
        elif sample.get("starts", 0) > 0 and sample.get("places", 0) == 0:
            parts.append((w["going_poor_pen2_wet"] if wet_bucket else w["going_poor_pen2_dry"],
                          f"{bucket} 1 戰未有成績"))
    if state in {"soft7plus", "heavy"}:
        wet_places = going_stats["軟地"]["places"] + going_stats["重地"]["places"]
        wet_starts = going_stats["軟地"]["starts"] + going_stats["重地"]["starts"]
        if wet_places == 0:
            if "WU" not in ARMS and not ("WU0" in ARMS and wet_starts == 0):
                parts.append((w["wet_unverified_pen"], "爛地實績未經驗證"))
        elif state == "heavy" and "HV" not in ARMS:
            heavy = going_stats.get("重地", {})
            if heavy.get("wins", 0) > 0:
                parts.append((w["heavy_win_bonus"], "重地曾奪冠"))
            elif heavy.get("places", 0) > 0:
                parts.append((w["heavy_place_bonus"], "具備重地作戰能力"))
            elif heavy.get("starts", 0) >= 2 and heavy.get("places", 0) == 0:
                parts.append((w["heavy_poor_pen"], "重地多戰全無表現"))
    return parts


def track_score(same_stats, going_stats, going):
    """→ (分數, 同場 parts, 地況 parts)。"""
    if "TR0" in ARMS:
        return NEUTRAL, [], []
    st = same_track_parts(same_stats)
    gp = going_parts(going_stats, going_bucket(going), wet_state(going))
    score = NEUTRAL
    for delta, _ in st:
        score += delta
    for delta, _ in gp:
        score += delta
    return clip_score(score), st, gp


def wet_overlay(going, going_stats_line):
    if "WO" in ARMS or ("WOS" in ARMS and wet_state(going) not in {"soft7plus", "heavy"}):
        return 0.0
    return wet_form_feature(going, going_stats_line)
