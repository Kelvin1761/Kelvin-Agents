"""AU 場地與地況適性（維度 `track`）＋ 濕地 overlay —— 唯一計算位置（EXP-20261102-10）。

`RacingEngine._track_score`／`_going_adjustment`／`_wet_state` 同綜合分嘅濕地 overlay 只係叫呢度。

今場地況分級（`wet_state`）：Heavy → heavy；Soft 7+ → soft7plus；Soft 5–6 → soft56；其他（包括冇數字）→ ""。
地況 bucket：Heavy／重 → 重地；Soft／軟 → 軟地；其餘 → 好地。

場地分 = 60 + 同場往績 + 地況往績，clip 0–100：

    同場：有上名 → min(9, 上名 × 5.0 + 贏 × 2.4)；≥2 戰 0 上名 → −8.81；1 戰 0 上名 → −0.81
    今場地況 bucket：有上名 → min(10, 上名 × 0.8)（濕地兼曾贏 +3.77）；
                    ≥2 戰 0 上名 → 濕 −4.75／乾 −3.46；1 戰 0 上名 → 濕 −4.14／乾 −3.0
                    （好地 bucket 永遠冇數：Facts 第一段冇「好地:」標籤，好地往績只做報告）

逐條消融（EXP-20261102-10，3,283 場）：同場兩個 0 上名扣分有訊號（剷走 Gold −0.18pp，CI 全負）；
「爛地未經驗證 −6.4」同「重地專項三條」剷走冇代價（合併 Gold +0.03pp、Good 0），已剷。
地況往績 ② 剷走排序指標 CI 全正但 Good −0.03pp（1 場），照登記規則保留，另行跟進。

濕地 overlay（直接加落綜合分；`scoring.wet_form_feature`）：今日地況含 soft／heavy 先開；
    今日嗰個濕地 bucket 全份、另一個半份；率 = (上名 + 4 × 0.3758) ÷ (出賽 + 4)；
    14.852 × (率 − 0.3758)，封頂 ±6.1818。冇濕地出賽 = 0。
"""
from __future__ import annotations

import os
import re

from .scoring import (TRACK_MICRO_WEIGHTS, WET_FORM_PRIOR, WET_FORM_SHRINK_A, _parse_going_segment, _parse_wet_record,
                      clip_score, wet_form_feature)

NEUTRAL = 60.0

# EXP-20261103-01（實驗中，預設關）：""＝現行；SPG＝好地日讀好地往績（現行規則）；
# SP＝相對生涯專長；SPW＝SP＋剷濕地 overlay。常數預先登記，唔准睇結果改。
SPECIALISM_ARM = os.environ.get("WC_AU_TRACK_SPECIALISM_ARM", "")
SPEC_K, SPEC_P0, SPEC_SCALE = 4.0, 0.3715, 50.0
_RECORD = re.compile(r"(\d+)\s*:\s*(\d+)-(\d+)-(\d+)")


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
    if stats["places"] > 0:
        return [(min(9, stats["places"] * w["same_track_place_bonus"] + stats["wins"] * w["same_track_win_bonus"]),
                 "同場有實際上名支持")]
    if stats["starts"] >= 2:
        return [(w["same_track_poor_pen1"], "同場已有多次出賽但仍未交到成績")]
    if stats["starts"] > 0:
        return [(w["same_track_poor_pen2"], "有同場出賽紀錄但仍未交到成績")]
    return []


def going_parts(going_stats, bucket):
    """今場地況 bucket 往績 → [(加減, 說明)]。going_stats：{好地／軟地／重地: stats}。"""
    w = TRACK_MICRO_WEIGHTS
    sample = going_stats.get(bucket, {})
    wet_bucket = bucket in {"軟地", "重地"}
    if sample.get("starts", 0) > 0 and sample.get("places", 0) > 0:
        parts = [(min(10, sample["places"] * w["going_place_bonus"]),
                  f"{bucket}有上名（{sample['places']}／{sample['starts']}）")]
        if sample.get("wins", 0) > 0 and wet_bucket:
            parts.append((w["going_win_bonus"], f"{bucket}曾贏"))
        return parts
    if sample.get("starts", 0) >= 2 and sample.get("places", 0) == 0:
        return [(w["going_poor_pen1_wet"] if wet_bucket else w["going_poor_pen1_dry"],
                 f"{bucket} {sample['starts']} 戰未有前列")]
    if sample.get("starts", 0) > 0 and sample.get("places", 0) == 0:
        return [(w["going_poor_pen2_wet"] if wet_bucket else w["going_poor_pen2_dry"],
                 f"{bucket} 1 戰未有成績")]
    return []


def record(text):
    """`21 : 8-3-0` → (出賽, 上名)；讀唔到 → (0, 0)。"""
    m = _RECORD.search(str(text or ""))
    if not m:
        return 0, 0
    s, w, a, b = map(int, m.groups())
    return s, w + a + b


def going_record(going_stats_line, bucket):
    """好地 = 第一段（冇標籤）；軟地／重地 = 有標籤嗰段。"""
    line = str(going_stats_line or "")
    if bucket == "好地":
        return record(line.split("|", 1)[0])
    m = re.search(rf"{bucket}:\s*([^|]+)", line)
    return record(m.group(1)) if m else (0, 0)


def specialism(rec, career_rate):
    """相對生涯：(上名 + K·c)/(出賽 + K) − c；冇出賽 → 0。"""
    starts, places = rec
    return (places + SPEC_K * career_rate) / (starts + SPEC_K) - career_rate if starts else 0.0


def specialism_score(track_stats_line, going_stats_line, career_record_line, going):
    """EXP-20261103-01 SP：→ (分數, parts)。"""
    cs, cp = record(career_record_line)
    c = (cp + SPEC_K * SPEC_P0) / (cs + SPEC_K)
    bucket = going_bucket(going)
    same = record(str(track_stats_line or "").split("|", 1)[0])
    today = going_record(going_stats_line, bucket)
    parts = []
    for label, rec in (("同場", same), (f"今日{bucket}", today)):
        if rec[0]:
            delta = SPEC_SCALE * specialism(rec, c)
            parts.append((delta, f"{label} {rec[1]}／{rec[0]} 上名，對比生涯上名率 {c:.0%} → {delta:+.1f}"))
    return clip_score(NEUTRAL + sum(d for d, _ in parts)), parts


def track_score(same_stats, going_stats, going):
    """→ (分數, 同場 parts, 地況 parts)。"""
    st = same_track_parts(same_stats)
    gp = going_parts(going_stats, going_bucket(going))
    score = NEUTRAL
    for delta, _ in st:
        score += delta
    for delta, _ in gp:
        score += delta
    return clip_score(score), st, gp


def wet_overlay(going, going_stats_line):
    if SPECIALISM_ARM == "SPW":
        return 0.0
    return wet_form_feature(going, going_stats_line)


def wet_overlay_detail(going, going_stats_line):
    """濕地 overlay 嘅報告明細；乾地 → None。數字同 `wet_form_feature` 一樣。"""
    g = str(going or "").lower()
    if "soft" not in g and "heavy" not in g:
        return None
    starts, places = _parse_wet_record(going, going_stats_line)
    rate = (places + WET_FORM_SHRINK_A * WET_FORM_PRIOR) / (starts + WET_FORM_SHRINK_A)
    heavy_today = "heavy" in g
    buckets = [("重地", _parse_going_segment(going_stats_line, "重地")),
               ("軟地", _parse_going_segment(going_stats_line, "軟地"))]
    if not heavy_today:
        buckets.reverse()
    return {"going": str(going), "starts": round(starts, 1), "places": round(places, 1),
            "today_bucket": buckets[0][0], "other_bucket": buckets[1][0],
            "today_record": list(buckets[0][1]), "other_record": list(buckets[1][1]),
            "rate": round(rate, 4), "prior": WET_FORM_PRIOR,
            "value": wet_form_feature(going, going_stats_line)}


def wet_overlay_line(detail):
    """→ 一句人話；None → ""。"""
    if not detail:
        return ""
    if not detail["starts"]:
        return f"今日 {detail['going']}，本駒未有濕地出賽，濕地往績調整 +0.00（中性）。"
    (ts, tp), (os_, op) = detail["today_record"], detail["other_record"]
    return (f"今日 {detail['going']}：{detail['today_bucket']} {ts} 戰 {tp} 上名（全計）、"
            f"{detail['other_bucket']} {os_} 戰 {op} 上名（半計），收縮後上名率 {detail['rate']:.1%} 對比"
            f"平均 {detail['prior']:.1%} → 濕地往績調整 {detail['value']:+.2f}，直接加落綜合戰力分。")
