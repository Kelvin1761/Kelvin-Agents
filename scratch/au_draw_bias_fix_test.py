#!/usr/bin/env python3
"""Round-6 candidate: fix the thin-sample draw-bias modifier (Kelvin's report).

Problem (live engine `_pace_map_score`): the venue+distance draw cell needs
only sample_size >= 10 to be trusted, modifier = (win_rate − 1/field) × 110,
capped at [−9.43, +4.05]. With n=16 and a 9% baseline, a legitimate inside
draw hits 0 observed wins ~22% of the time by pure chance and gets slammed
−9.43 pace_map points (≈ −1.4 ability). Penalties cap at 2.3× bonuses.

Candidates (Δability = race_shape weight × Δmodifier on cached races):
  C1 global-only  — drop venue-specific cells entirely (Kelvin's proposal,
                    the HKJC lesson: no per-course stats without density);
  C2 shrinkage    — keep the cascade but scale the raw modifier by n/(n+k),
                    k per fold from {25, 50, 100}, no min-sample cliffs;
  C3 symmetric-cap— C2 plus a symmetric cap ±4.05 (kill the penalty skew).

Walk-forward gate as usual. Reproduction of the live modifier is validated
against stored pace_map_score before testing.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCRIPTS = Path("/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/shared_racing")

from au_cached_walkforward_ml import (  # noqa: E402
    as_float,
    date_folds,
    group_races,
    materialize_dataset,
    metrics_for_races,
)
from scoring import MATRIX_WEIGHTS, PACE_MICRO_WEIGHTS  # noqa: E402

MATRIX = json.loads((SCRIPTS / "racing_engine" / "au_draw_bias_matrix.json").read_text(encoding="utf-8"))
SANDBOX = Path("/private/tmp/claude-501/-Users-imac-Antigravity-repo/b09ea7dc-ca6d-496d-af27-41b7787ee6ae/scratchpad/data/Wong Choi Horse Race Analysis/AU_Racing")
RACE_SHAPE_W = MATRIX_WEIGHTS["race_shape"]
W = PACE_MICRO_WEIGHTS


def bucket_of(barrier: float) -> str:
    if barrier <= 4:
        return "inside"
    if barrier <= 8:
        return "middle"
    return "outside" if barrier <= 12 else "wide"


def f_cat_of(field: int) -> str:
    if field <= 8:
        return "field_1_8"
    return "field_9_12" if field <= 12 else "field_13_plus"


def load_context() -> dict:
    ctx = {}
    for d in sorted(p for p in SANDBOX.iterdir() if p.is_dir()):
        for lp in d.glob("Race_*_Logic.json"):
            try:
                data = json.loads(lp.read_text(encoding="utf-8"))
            except Exception:
                continue
            ra = data.get("race_analysis") or {}
            race_no = str(ra.get("race_number") or lp.stem.split("_")[1])
            distance = re.sub(r"[^0-9]", "", str(ra.get("distance") or ""))
            for num, h in (data.get("horses") or {}).items():
                barrier = h.get("barrier")
                try:
                    barrier = float(barrier)
                except (TypeError, ValueError):
                    barrier = None
                ctx[f"{d.name}|{race_no}|{num}"] = {"barrier": barrier, "distance": distance,
                                                    "pace_map_score": (h.get("python_auto") or {}).get("feature_scores", {}).get("pace_map_score")}
    return ctx


def lookup(track: str, distance: str, bucket: str, field: int):
    """Replicates the live cascade. Returns (stats, level) or (None, fallback)."""
    trk = MATRIX.get("tracks", {}).get(str(track).title(), {})
    d_stats = (trk.get("distances", {}).get(distance, {}) or {}).get(bucket, {})
    if d_stats.get("sample_size", 0) >= 10:
        return d_stats, "venue_distance"
    t_stats = (trk.get("track_general", {}) or {}).get(bucket, {})
    if t_stats.get("sample_size", 0) >= 30:
        return t_stats, "venue_general"
    g = MATRIX.get("global_general", {}).get(f_cat_of(field), {}).get(bucket, {})
    return (g, "global") if g.get("sample_size", 0) > 0 else (None, "none")


def modifier_from(stats, field: int, cap_min: float, cap_max: float, shrink_k: float | None) -> float:
    expected = 1.0 / max(field, 1)
    raw = (stats.get("win_rate", expected) - expected) * 100 * W["modifier_multiplier"]
    if shrink_k is not None:
        n = stats.get("sample_size", 0)
        raw *= n / (n + shrink_k)
    return max(cap_min, min(cap_max, raw))


def current_modifier(track, distance, bucket, field, barrier):
    stats, level = lookup(track, distance, bucket, field)
    if stats:
        return modifier_from(stats, field, W["modifier_cap_min"], W["modifier_cap_max"], None)
    if barrier is not None and barrier <= 4:
        return W["fallback_inside_bonus"]
    return 0.0


def candidate_modifier(mode, track, distance, bucket, field, barrier, k):
    if mode == "C1":  # global only
        g = MATRIX.get("global_general", {}).get(f_cat_of(field), {}).get(bucket, {})
        if g.get("sample_size", 0) > 0:
            return modifier_from(g, field, W["modifier_cap_min"], W["modifier_cap_max"], None)
        return W["fallback_inside_bonus"] if (barrier is not None and barrier <= 4) else 0.0
    stats, level = lookup(track, distance, bucket, field)
    cap_min = -abs(W["modifier_cap_max"]) if mode == "C3" else W["modifier_cap_min"]
    if stats:
        return modifier_from(stats, field, cap_min, W["modifier_cap_max"], k)
    return W["fallback_inside_bonus"] if (barrier is not None and barrier <= 4) else 0.0


def main() -> int:
    ctx = load_context()
    races = group_races(materialize_dataset())

    # validate reproduction against stored pace_map_score
    checked = ok = 0
    for race in races[:200]:
        field = len(race)
        track = str(race[0].get("track") or "")
        for r in race:
            info = ctx.get(f"{r['meeting']}|{r['race']}|{int(r['horse_number'])}")
            if not info or info["barrier"] is None or info["pace_map_score"] in (None, ""):
                continue
            mod = current_modifier(track, info["distance"], bucket_of(info["barrier"]), field, info["barrier"])
            predicted = max(0.0, min(100.0, W["base"] + mod))
            checked += 1
            ok += abs(predicted - float(info["pace_map_score"])) < 0.75
    print(f"reproduction check: {ok}/{checked} within 0.75 pt of stored pace_map_score ({100*ok/max(1,checked):.1f}%)")

    def scored(subset, mode, k):
        out = []
        for race in subset:
            field = len(race)
            track = str(race[0].get("track") or "")
            rows = []
            for r in race:
                info = ctx.get(f"{r['meeting']}|{r['race']}|{int(r['horse_number'])}")
                delta = 0.0
                if info and info["barrier"] is not None:
                    b = bucket_of(info["barrier"])
                    cur = current_modifier(track, info["distance"], b, field, info["barrier"])
                    if mode == "base":
                        delta = 0.0
                    else:
                        delta = candidate_modifier(mode, track, info["distance"], b, field, info["barrier"], k) - cur
                rows.append({**r, "_score": as_float(r["ability_score"], 60.0) + RACE_SHAPE_W * delta})
            out.append(rows)
        return out

    folds = date_folds(races)
    for mode in ("C1", "C2", "C3"):
        all_base, all_cand, non_worse = [], [], 0
        for train, valid in folds:
            k = None
            if mode in ("C2", "C3"):
                best_gp = -1.0
                for kk in (25.0, 50.0, 100.0):
                    m = metrics_for_races(scored(train, mode, kk))
                    gp = (m["good_positional"] + m["good"]) / max(1, m["races"])
                    if gp > best_gp:
                        best_gp, k = gp, kk
            vb = metrics_for_races(scored(valid, "base", None))
            vc = metrics_for_races(scored(valid, mode, k))
            non_worse += vc["top3_precision"] >= vb["top3_precision"]
            all_base.extend(scored(valid, "base", None))
            all_cand.extend(scored(valid, mode, k))
        base = metrics_for_races(all_base)
        cand = metrics_for_races(all_cand)
        gp = (cand["good_positional"] - base["good_positional"]) / base["races"] * 100
        g2 = (cand["good"] - base["good"]) / base["races"] * 100
        passed = (max(gp, g2) >= 1.5 and min(gp, g2) >= -0.5 and cand["miss"] <= base["miss"] and non_worse >= 4
                  and (base["top1_win"] - cand["top1_win"]) * 100 <= 0.5
                  and (base["winner_in_top3"] - cand["winner_in_top3"]) * 100 <= 0.5
                  and (base["gold"] - cand["gold"]) / base["races"] * 100 <= 0.5)
        print(f"{mode}: gp {gp:+.2f}pp g2 {g2:+.2f}pp gold {cand['gold']-base['gold']:+d} miss {cand['miss']-base['miss']:+d} "
              f"top1 {(cand['top1_win']-base['top1_win'])*100:+.2f}pp wT3 {(cand['winner_in_top3']-base['winner_in_top3'])*100:+.2f}pp "
              f"folds {non_worse}/{len(folds)} → {'PASS' if passed else 'FAIL / HOLD'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
