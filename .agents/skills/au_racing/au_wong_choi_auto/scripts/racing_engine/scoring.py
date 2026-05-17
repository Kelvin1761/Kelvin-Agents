#!/usr/bin/env python3
"""AU Wong Choi Auto scoring primitives."""
from __future__ import annotations
import re

FEATURE_KEYS = ("form_score","trial_score","sectional_score","pace_map_score","jockey_score","trainer_score","jockey_horse_fit_score","class_score","weight_score","distance_score","track_score","formline_score","consistency_score","health_score","confidence_score","speed_rating_score")

MATRIX_WEIGHTS = {"stability":0.16,"sectional":0.15,"race_shape":0.10,"jockey_trainer":0.14,"class_weight":0.12,"track":0.10,"form_line":0.15,"speed_performance":0.08}
_WEIGHT_FLOOR = {"stability":0.10}
_WEIGHT_CEILING = {"class_weight":0.20,"track":0.17}

def get_dynamic_matrix_weights(race_context):
    weights = dict(MATRIX_WEIGHTS)
    field_summary = race_context.get("field_summary",{})
    field_count = int(field_summary.get("count",0))
    going = str(race_context.get("going","") or "").lower()
    race_class = str(race_context.get("race_class","") or "").lower()
    if field_count >= 13:
        weights["race_shape"] -= 0.02; weights["sectional"] -= 0.01; weights["stability"] += 0.02; weights["form_line"] += 0.01
    elif field_count >= 9:
        weights["race_shape"] -= 0.01; weights["sectional"] -= 0.005; weights["stability"] += 0.01; weights["form_line"] += 0.005
    if "soft" in going or "heavy" in going:
        weights["race_shape"] -= 0.005; weights["track"] += 0.01; weights["stability"] -= 0.005
    if "bm" in race_class:
        bm_tokens = tuple(f"bm{n}" for n in range(50,100))
        if any(t in race_class for t in bm_tokens): weights["class_weight"] += 0.005
    total = sum(weights.values())
    if total > 0:
        for key in weights: weights[key] = weights[key] / total
    for key, floor_val in _WEIGHT_FLOOR.items():
        if weights[key] < floor_val: weights[key] = floor_val
    for key, ceil_val in _WEIGHT_CEILING.items():
        if weights[key] > ceil_val: weights[key] = ceil_val
    for key in weights: weights[key] = round(weights[key],4)
    return weights

PLACE_TIGHTENING_FEATURE_WEIGHTS = {"form_score":0.103,"trial_score":0.199,"trainer_score":0.234,"jockey_horse_fit_score":0.170,"consistency_score":0.093,"distance_score":-0.033,"confidence_score":0.027,"weight_score":-0.141}
PLACE_TIGHTENING_SCALE = 1.4
PLACE_TIGHTENING_MAX_ABS_BONUS = 4.0
GRADE_THRESHOLDS = ((96,"S+"),(92,"S"),(88,"S-"),(84,"A+"),(80,"A"),(76,"A-"),(72,"B+"),(68,"B"),(64,"B-"),(60,"C+"),(56,"C"),(52,"C-"),(48,"D"),(0,"E"))

def clip_score(value, default=60.0):
    try: score = float(value)
    except (TypeError, ValueError): score = default
    return max(0.0, min(100.0, score))

def compute_grade(ability_score):
    score = clip_score(ability_score,0)
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold: return grade
    return "E"

def score_band(score):
    score = clip_score(score)
    if score >= 85: return "✅✅"
    if score >= 70: return "✅"
    if score >= 55: return "➖"
    if score >= 40: return "❌"
    return "❌❌"

def parse_float(value):
    if isinstance(value,(int,float)): return float(value)
    if not value: return None
    match = re.search(r"-?\d+(?:\.\d+)?",str(value))
    return float(match.group(0)) if match else None

def parse_numbers(text):
    if not text: return []
    return [int(m.group(0)) for m in re.finditer(r"\d+",str(text))]

def parse_record_line(line):
    if not line: return {"starts":0,"wins":0,"seconds":0,"thirds":0,"places":0}
    nums = parse_numbers(str(line))
    if len(nums) >= 4:
        wins = nums[1]
        seconds = nums[2]
        thirds = nums[3]
        return {
            "starts": nums[0],
            "wins": wins,
            "seconds": seconds,
            "thirds": thirds,
            "places": wins + seconds + thirds,
        }
    if len(nums) >= 3:
        wins = nums[1]
        places = nums[1] + nums[2]
        return {"starts":nums[0],"wins":wins,"seconds":nums[2],"thirds":0,"places":places}
    return {"starts":0,"wins":0,"seconds":0,"thirds":0,"places":0}

def parse_recent_finishes(text):
    if not text: return None
    nums = parse_numbers(str(text))
    if nums: return [n for n in nums if 1 <= n <= 24]
    return None

def safe_ratio(numerator, denominator):
    if not denominator: return 0.0
    return min(1.0, max(0.0, numerator / denominator))
