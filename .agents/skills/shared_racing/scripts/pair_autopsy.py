#!/usr/bin/env python3
"""逐對深入覆盤（自學循環 L1.5 Phase P1，設計 docs/plans/2026-11-27-deep-autopsy.md §1 Case A）。

只做診斷：回答「大熱贏咗但模型排第 2，點解我哋首選分數高過大熱」。
絕對唔會改模型、調權重、或者揀 leaf。

輸出：
  select_case_a(race_rows, results) -> (cases, counters)
  decompose_au(pa_top, pa_win, decision_trace=None) -> dict
  decompose_hkjc(pa_top, pa_win, field_pas=None) -> dict
  autopsy_meeting(platform, meeting_dir) -> dict
  autopsy_day(platform, day, root=None) -> dict
  render_md(result) -> str

    python3 pair_autopsy.py --platform au|hkjc --date YYYY-MM-DD [--meeting DIR] [--json]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SHARED = HERE.parent
REPO = HERE.parents[3]
AU_SCRIPTS = REPO / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"
HKJC_SCRIPTS = REPO / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi_auto" / "scripts"

for _p in (str(HERE), str(SHARED), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

VERSION = "pair-autopsy-v1"
VERSION_GUARD_TOL = 0.05
RESIDUAL_UNEXPLAINED_TOL = 0.05
DEFAULT_60_TOL = 0.005

AU_OVERLAY_KEYS = (
    "wet_form_feature",
    "proven_class_feature",
    "full_time_speed_feature",
    "draw_feature",
    "old_horse_feature",
    "trainer_residual_feature",
    "people_prize_feature",
    "winning_time_speed_feature",
)

AU_OVERLAY_FALLBACK_LABELS = {
    "wet_form_feature": "濕地往績調整",
    "proven_class_feature": "班次證明",
    "full_time_speed_feature": "逐駒全程速度",
    "draw_feature": "大場次檔位",
    "old_horse_feature": "老馬調整",
    "trainer_residual_feature": "練馬師剩餘表現",
    "people_prize_feature": "騎練總獎金",
    "winning_time_speed_feature": "頭馬時間速度分",
}

HKJC_DERIVED_LABELS = {
    "formline_strength_score": "賽績線強度分",
    "margin_trend_score": "輸距趨勢分",
    "same_distance_signal_score": "同程訊號分",
    "trackwork_trend_score": "晨操趨勢分",
    "race_shape_context_score": "檔位走位情境分",
    "distance_fit_score": "同程表現分",
}

HKJC_DELTA_FIELDS = (
    ("market_history", "market_history_delta"),
    ("draw_style", "draw_style_delta"),
    ("incident_history", "incident_history_delta"),
    ("distance_move", "distance_move_delta"),
    ("surface_move", "surface_move_delta"),
    ("same_distance_venue", "same_distance_venue_delta"),
    ("horse_age", "horse_age_delta"),
    ("excuse_streak", "excuse_streak_delta"),
    ("thin_evidence", "thin_evidence_delta"),
    ("performance_figure", "performance_figure_delta"),
    ("debut_trainer", "debut_trainer_delta"),
    ("trial_time", "trial_time_delta"),
    ("straight_figure", "straight_figure_delta"),
)

HKJC_EXTRA_ADJUSTMENT_LABELS = {
    "overlays": "情境修正",
    "sip_boost": "shadow／SIP 調整",
    "trial_time": "試閘時間（實驗性）",
}

WEAK_EVIDENCE_STATES = frozenset({"missing", "fallback"})
WEAK_PROVENANCE_TOKENS = ("missing", "neutral", "fallback", "disabled", "no_spread", "career_tag", "unknown")


# ---------------------------------------------------------------- Engine loaders

def _ensure_sys_path(path: Path) -> None:
    s = str(path)
    if s not in sys.path:
        sys.path.insert(0, s)


def _au_engine():
    _ensure_sys_path(AU_SCRIPTS)
    from au_racing_engine import dimensions, matrix_mapper, renderer, scoring
    return dimensions, matrix_mapper, renderer, scoring


def _hkjc_engine():
    _ensure_sys_path(HKJC_SCRIPTS)
    from hkjc_racing_engine import dimensions, matrix_mapper, renderer, scoring
    return dimensions, matrix_mapper, renderer, scoring


def _core():
    _ensure_sys_path(SHARED / "race_reflector" / "scripts")
    import unified_reflector_core as core
    return core


def _labels(platform: str) -> dict[str, str]:
    if platform == "au":
        dim, _mm, ren, _sco = _au_engine()
        out = dict(AU_OVERLAY_FALLBACK_LABELS)
        for _k, field, label, _d in getattr(ren, "OVERLAYS", ()):
            out[field] = label
        for spec in dim.DIMENSION_SPECS:
            out[spec.key] = spec.label
        out.update(dim.FEATURE_LABELS)
        return out
    dim, _mm, ren, sco = _hkjc_engine()
    out = dict(HKJC_DERIVED_LABELS)
    out.update(HKJC_EXTRA_ADJUSTMENT_LABELS)
    for item in getattr(sco, "RANKING_ADJUSTMENTS", ()):
        out[item["key"]] = item["label"]
    out.update(dim.labels())
    out.update(getattr(ren, "FEATURE_LABELS", {}))
    return out


# ---------------------------------------------------------------- Numeric / field helpers

def _float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(str(value).replace("$", "").strip())
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _sp_or_none(value: Any) -> float | None:
    f = _float_or_none(value)
    return f if f is not None and f > 0.0 else None


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _published_rank(row: dict[str, Any]) -> int | None:
    rk = _int_or_none(row.get("rank"))
    if rk is not None and 0 < rk < 999:
        return rk
    drk = _int_or_none(row.get("derived_rank"))
    if drk is not None and 0 < drk < 999:
        return drk
    return None


def _unwrap_pa(obj: dict[str, Any]) -> dict[str, Any]:
    if isinstance(obj, dict) and "python_auto" in obj and "matrix_scores" not in obj:
        return obj.get("python_auto") or {}
    return obj or {}


def _empty_counters() -> dict[str, Any]:
    return {
        "races_with_results": 0,
        "fav_won": 0,
        "fav_won_rank1": 0,
        "fav_won_rank2": 0,
        "fav_won_rank3plus": 0,
        "sp_missing": 0,
        "winner_unranked": 0,
        "dead_heat": [],
        "notes": [],
    }


def _prov_is_weak(prov: Any) -> bool:
    if not prov:
        return False
    low = str(prov).strip().lower()
    return any(tok in low for tok in WEAK_PROVENANCE_TOKENS)


def _leaf_evidence(pa: dict[str, Any], leaf_key: str, leaf_value: float, *, has_evidence_state: bool) -> dict[str, Any]:
    prov = (pa.get("score_provenance") or {}).get(leaf_key)
    state = (pa.get("feature_evidence_state") or {}).get(leaf_key) if has_evidence_state else None
    if state is not None:
        weak_source = state in WEAK_EVIDENCE_STATES
        state_label = state
    else:
        weak_source = _prov_is_weak(prov)
        state_label = prov
    default_60 = bool(weak_source and abs(float(leaf_value) - 60.0) <= DEFAULT_60_TOL)
    return {
        "state": state_label,
        "provenance": prov,
        "default_60": default_60,
        "weak": bool(weak_source or default_60),
    }


def _ev_is_weak(ev: Any) -> bool:
    if not isinstance(ev, dict):
        return False
    return bool(ev.get("default_60") or ev.get("weak") or ev.get("state") in WEAK_EVIDENCE_STATES)


# ---------------------------------------------------------------- Case A selection

def select_case_a(race_rows: dict[Any, list[dict[str, Any]]], results: dict[Any, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """揀出「大熱贏但模型排第 2」嘅場次（Case A）同當日統計計數。"""
    counters = _empty_counters()
    cases: list[dict[str, Any]] = []

    def _race_sort_key(k: Any) -> tuple[int, str]:
        ik = _int_or_none(k)
        return (ik if ik is not None else 999999, str(k))

    for race_key in sorted(results, key=_race_sort_key):
        race_num = _int_or_none(race_key)
        if race_num is None:
            continue
        res_entry = results[race_key]
        raw_rows = res_entry.get("results") if isinstance(res_entry, dict) else res_entry
        scratched = (
            {_int_or_none(h) for h in (res_entry.get("scratched_horse_numbers") or []) if _int_or_none(h) is not None}
            if isinstance(res_entry, dict)
            else set()
        )
        started = [
            r for r in (raw_rows or [])
            if isinstance(r, dict)
            and not r.get("is_scratched")
            and _int_or_none(r.get("horse_no")) is not None
            and _int_or_none(r.get("horse_no")) not in scratched
        ]
        if not started:
            continue

        counters["races_with_results"] += 1

        winners = [r for r in started if _int_or_none(r.get("placing")) == 1]
        if len(winners) > 1:
            counters["dead_heat"].append(race_num)
            counters["notes"].append({"race": race_num, "note": "dead_heat"})
            continue
        if len(winners) == 0:
            continue

        winner = winners[0]
        winner_no = _int_or_none(winner.get("horse_no"))

        sp_by_horse: dict[int, float] = {}
        missing_any = False
        for r in started:
            hno = _int_or_none(r.get("horse_no"))
            raw_sp = r.get("odds") if r.get("odds") is not None else r.get("sp")
            sp_val = _sp_or_none(raw_sp)
            if hno is None or sp_val is None:
                missing_any = True
                break
            sp_by_horse[hno] = sp_val

        if missing_any or not sp_by_horse:
            counters["sp_missing"] += 1
            continue

        min_sp = min(sp_by_horse.values())
        favs = [h for h, sp in sp_by_horse.items() if abs(sp - min_sp) <= 1e-9]
        fav_tied = len(favs) > 1
        if winner_no not in favs:
            continue

        preds = race_rows.get(race_num)
        if preds is None:
            preds = race_rows.get(str(race_num)) or []
        published: dict[int, int] = {}
        for p in preds:
            hno = _int_or_none(p.get("horse_no"))
            rk = _published_rank(p)
            if hno is not None and rk is not None:
                published[hno] = rk
        # 只計真係有跑嘅馬：賽前首選臨場退出，就用「有跑嘅馬入面」嘅次序（Hydrogen 2026-11-27）
        starters = sorted((rk, h) for h, rk in published.items() if h in sp_by_horse)
        rank_by_horse = {h: i + 1 for i, (_rk, h) in enumerate(starters)}
        if rank_by_horse.get(winner_no) is None:
            counters["winner_unranked"] += 1
            continue
        if any(published[h] != rank_by_horse[h] for h in rank_by_horse if rank_by_horse[h] <= 2):
            counters["notes"].append({"race": race_num, "note": "rank_shifted_by_scratching"})
        top_pick_no = next((h for h, r in rank_by_horse.items() if r == 1), None)
        counters["fav_won"] += 1
        winner_rank = rank_by_horse[winner_no]
        if winner_rank == 1:
            counters["fav_won_rank1"] += 1
        elif winner_rank == 2:
            counters["fav_won_rank2"] += 1
            cases.append({
                "race": race_num,
                "field_size": len(started),
                "winner_no": winner_no,
                "winner_sp": sp_by_horse[winner_no],
                "top_pick_no": top_pick_no,
                "fav_tied": fav_tied,
            })
        else:
            counters["fav_won_rank3plus"] += 1

    return cases, counters


# ---------------------------------------------------------------- Decomposition

def _finalize_decomposition(
    *,
    parts: list[dict[str, Any]],
    total_gap: float,
    official_gap: float | None,
    leaf_rounding: dict[str, float],
    leaf_level_valid: bool,
    nonlinear: bool,
    swap: dict[str, Any] | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dim_sum = sum(p["contribution"] for p in parts if p["kind"] == "dimension")
    adj_sum = sum(p["contribution"] for p in parts if p["kind"] in ("overlay", "adjustment"))
    residual = total_gap - dim_sum - adj_sum
    unexplained = abs(residual) > RESIDUAL_UNEXPLAINED_TOL

    sorted_parts = sorted(parts, key=lambda p: (-abs(p["contribution"]), p["kind"], p["key"]))
    driver_kinds = ("leaf", "overlay", "adjustment") if leaf_level_valid else ("dimension", "overlay", "adjustment")
    drivers = [p for p in sorted_parts if p["kind"] in driver_kinds]

    top_reasons = [p for p in drivers if p["contribution"] > 1e-9][:3]
    against = [p for p in drivers if p["contribution"] < -1e-9][:3]
    weak_evidence_reasons = [
        p for p in drivers
        if p["contribution"] > 1e-9
        and (_ev_is_weak(p.get("top_evidence")) or _ev_is_weak(p.get("win_evidence")))
    ]

    out = {
        "total_gap": total_gap,
        "official_gap": official_gap,
        "parts": sorted_parts,
        "leaf_rounding": leaf_rounding,
        "top_reasons": top_reasons,
        "against": against,
        "weak_evidence_reasons": weak_evidence_reasons,
        "leaf_level_valid": leaf_level_valid,
        "unexplained": unexplained,
        "residual": residual,
        "nonlinear": nonlinear,
        "swap": swap,
    }
    if extra:
        out.update(extra)
    return out


def _au_version_guard(pa: dict[str, Any], au_mm: Any) -> tuple[bool, dict[str, float]]:
    raw_feats = pa.get("feature_scores") or {}
    feats = au_mm.with_form_quality(raw_feats)
    snap_matrix = pa.get("matrix_scores") or {}
    if not isinstance(snap_matrix, dict) or not snap_matrix:
        return False, feats
    recomputed = au_mm.map_features_to_matrix_scores(feats)
    for dim_key, rec_val in recomputed.items():
        if dim_key in snap_matrix:
            snap_val = _float_or_none(snap_matrix[dim_key])
        elif dim_key == "pace_perf" and "sectional" in snap_matrix:
            snap_val = _float_or_none(snap_matrix["sectional"])
        else:
            continue
        if snap_val is None or abs(rec_val - snap_val) > VERSION_GUARD_TOL:
            return False, feats
    return True, feats


def _snapshot_weights(pa: dict[str, Any]) -> dict[str, float]:
    """快照自己計分嗰陣用嘅維度權重（grade_transparency.rows[].weight）。
    引擎權重會變（AU 2026-11-27 pace_perf ×1.64、HKJC 11-14 外層權重），用現行權重拆舊快照會對唔返數；
    每匹馬嘅 rows 亦已經反映佢自己（初出馬）嘅權重。冇就返空，由 caller 退返現行引擎權重。"""
    out: dict[str, float] = {}
    rows = ((pa.get("grade_transparency") or {}).get("rows")) or []
    for row in rows:
        if isinstance(row, dict) and row.get("key") and not row.get("retired"):
            w = _float_or_none(row.get("weight"))
            if w is not None:
                out[str(row["key"])] = w
    return out


def decompose_au(
    pa_top: dict[str, Any],
    pa_win: dict[str, Any],
    decision_trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """拆解 AU 模型首選（#1）同大熱（#2）之間嘅分數差距。"""
    au_dim, au_mm, _au_ren, au_sco = _au_engine()
    top = _unwrap_pa(pa_top)
    win = _unwrap_pa(pa_win)

    top_score = float(top.get("final_rank_score") if top.get("final_rank_score") is not None else top.get("ability_score", 60.0))
    win_score = float(win.get("final_rank_score") if win.get("final_rank_score") is not None else win.get("ability_score", 60.0))
    total_gap = top_score - win_score
    top_off = top.get("ability_score") if top.get("ability_score") is not None else top_score
    win_off = win.get("ability_score") if win.get("ability_score") is not None else win_score
    official_gap = float(top_off) - float(win_off)

    valid_top, top_feats = _au_version_guard(top, au_mm)
    valid_win, win_feats = _au_version_guard(win, au_mm)
    leaf_level_valid = valid_top and valid_win

    top_matrix = top.get("matrix_scores") or {}
    win_matrix = win.get("matrix_scores") or {}

    parts: list[dict[str, Any]] = []
    leaf_rounding: dict[str, float] = {}

    snap_top, snap_win = _snapshot_weights(top), _snapshot_weights(win)
    weights_source = "snapshot" if snap_top and snap_win else "engine"
    dim_keys = list(au_dim.MATRIX_WEIGHTS)
    if weights_source == "snapshot":   # 舊快照可能有已退役維度、或者未有新維度：以快照為準，冇就當 0（Hydrogen 2026-11-27）
        dim_keys = list(dict.fromkeys([*snap_top, *snap_win]))
    for dim_key in dim_keys:
        coeff = au_dim.MATRIX_WEIGHTS.get(dim_key, 0.0)
        ct = float(snap_top.get(dim_key, 0.0)) if weights_source == "snapshot" else float(coeff)
        cw = float(snap_win.get(dim_key, 0.0)) if weights_source == "snapshot" else float(coeff)
        dim_top = au_mm.matrix_score(top_matrix, dim_key)
        dim_win = au_mm.matrix_score(win_matrix, dim_key)
        dim_contrib = ct * (dim_top - 60.0) - cw * (dim_win - 60.0)
        parts.append({
            "kind": "dimension",
            "key": dim_key,
            "dimension": dim_key,
            "contribution": dim_contrib,
            "top_value": dim_top,
            "win_value": dim_win,
            "top_evidence": None,
            "win_evidence": None,
        })
        if leaf_level_valid:
            leaf_sum = 0.0
            for leaf_key, leaf_w in au_dim.MATRIX_FORMULAS.get(dim_key, ()):
                lw = float(leaf_w)
                tv = au_sco.clip_score(top_feats.get(leaf_key, 60.0))
                wv = au_sco.clip_score(win_feats.get(leaf_key, 60.0))
                lc = ct * lw * (tv - 60.0) - cw * lw * (wv - 60.0)
                leaf_sum += lc
                parts.append({
                    "kind": "leaf",
                    "key": leaf_key,
                    "dimension": dim_key,
                    "contribution": lc,
                    "top_value": tv,
                    "win_value": wv,
                    "top_evidence": _leaf_evidence(top, leaf_key, tv, has_evidence_state=True),
                    "win_evidence": _leaf_evidence(win, leaf_key, wv, has_evidence_state=True),
                })
            leaf_rounding[dim_key] = dim_contrib - leaf_sum

    for ov_key in AU_OVERLAY_KEYS:
        top_ov = float(top.get(ov_key) or 0.0)
        win_ov = float(win.get(ov_key) or 0.0)
        contrib = top_ov - win_ov
        if abs(contrib) > 1e-12 or abs(top_ov) > 1e-12 or abs(win_ov) > 1e-12:
            parts.append({
                "kind": "overlay",
                "key": ov_key,
                "dimension": None,
                "contribution": contrib,
                "top_value": top_ov,
                "win_value": win_ov,
                "top_evidence": None,
                "win_evidence": None,
            })

    swap = dict(decision_trace) if isinstance(decision_trace, dict) and decision_trace.get("changed") else None
    return dict(weights_source=weights_source, **_finalize_decomposition(
        parts=parts,
        total_gap=total_gap,
        official_gap=official_gap,
        leaf_rounding=leaf_rounding,
        leaf_level_valid=leaf_level_valid,
        nonlinear=False,
        swap=swap,
    ))


def _hkjc_is_debut(pa: dict[str, Any]) -> bool:
    if pa.get("is_debut") or pa.get("debut_runner"):
        return True
    for field in ("reason_codes", "risk_flags"):
        if any("debut" in str(code).lower() for code in (pa.get(field) or [])):
            return True
    return False


def _hkjc_all_features(pa: dict[str, Any], hkjc_sco: Any) -> dict[str, float]:
    merged: dict[str, float] = {}
    for src in (pa.get("feature_scores") or {}, pa.get("derived_feature_scores") or {}):
        if isinstance(src, dict):
            for k, v in src.items():
                fv = _float_or_none(v)
                if fv is not None:
                    merged[k] = fv
    if "distance_fit_score" not in merged:
        dist_w = float((hkjc_sco.CENTRED_MATRIX_WEIGHTS or {}).get("distance_fit") or 0.0)
        adj = pa.get("distance_suitability_adjustment")
        if isinstance(adj, dict) and adj.get("raw_adjustment") is not None and dist_w:
            merged["distance_fit_score"] = 60.0 + float(adj["raw_adjustment"]) / dist_w
        elif isinstance(pa.get("matrix_scores"), dict) and "distance_fit" in pa["matrix_scores"]:
            df = _float_or_none(pa["matrix_scores"]["distance_fit"])
            if df is not None:
                merged["distance_fit_score"] = df
    return merged


def _hkjc_version_guard(pa: dict[str, Any], is_debut: bool, hkjc_mm: Any, hkjc_sco: Any) -> tuple[bool, dict[str, float]]:
    feats = _hkjc_all_features(pa, hkjc_sco)
    snap_matrix = pa.get("matrix_scores") or {}
    if not isinstance(snap_matrix, dict) or not snap_matrix:
        return False, feats
    recomputed = hkjc_mm.map_features_to_matrix_scores(feats, debut=is_debut)
    rsr = pa.get("race_shape_robustness")
    for dim_key, rec_val in recomputed.items():
        if dim_key not in snap_matrix:
            continue
        if dim_key == "race_shape" and isinstance(rsr, dict) and rsr.get("applied") and rsr.get("base_race_shape") is not None:
            snap_val = _float_or_none(rsr.get("base_race_shape"))
        else:
            snap_val = _float_or_none(snap_matrix[dim_key])
        if snap_val is None or abs(rec_val - snap_val) > VERSION_GUARD_TOL:
            return False, feats
    return True, feats


def _hkjc_adjustments_map(pa: dict[str, Any]) -> dict[str, float]:
    adj: dict[str, float] = {}
    sip = sum(float(flag.get("boost", 0) or 0) for flag in (pa.get("sip_flags") or []) if isinstance(flag, dict))
    if abs(sip) > 1e-12:
        adj["sip_boost"] = sip
    ov = sum(
        float((item or {}).get("applied_delta", 0.0) or 0.0)
        for item in (pa.get("overlays") or {}).values()
    )
    if abs(ov) > 1e-12:
        adj["overlays"] = ov
    for key, field in HKJC_DELTA_FIELDS:
        if field in pa and pa.get(field) is not None:
            adj[key] = float(pa.get(field) or 0.0)
    gt = pa.get("grade_transparency") or {}
    for item in gt.get("adjustments") or []:
        if isinstance(item, dict) and item.get("key") and item["key"] not in adj:
            val = _float_or_none(item.get("raw"))
            if val is not None:
                adj[str(item["key"])] = val
    return adj


def decompose_hkjc(
    pa_top: dict[str, Any],
    pa_win: dict[str, Any],
    field_pas: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """拆解 HKJC 模型首選（#1）同大熱（#2）之間嘅分數差距（原始分尺 ability_score_raw）。"""
    hkjc_dim, hkjc_mm, _hkjc_ren, hkjc_sco = _hkjc_engine()
    top = _unwrap_pa(pa_top)
    win = _unwrap_pa(pa_win)

    top_raw = float(top.get("ability_score_raw") if top.get("ability_score_raw") is not None else top.get("ability_score", 60.0))
    win_raw = float(win.get("ability_score_raw") if win.get("ability_score_raw") is not None else win.get("ability_score", 60.0))
    total_gap = top_raw - win_raw

    top_off = _float_or_none(top.get("official_ranking_score", top.get("ability_score")))
    win_off = _float_or_none(win.get("official_ranking_score", win.get("ability_score")))
    official_gap = (top_off - win_off) if (top_off is not None and win_off is not None) else None

    top_debut = _hkjc_is_debut(top)
    win_debut = _hkjc_is_debut(win)

    valid_top, top_feats = _hkjc_version_guard(top, top_debut, hkjc_mm, hkjc_sco)
    valid_win, win_feats = _hkjc_version_guard(win, win_debut, hkjc_mm, hkjc_sco)
    leaf_level_valid = valid_top and valid_win

    w_base_top = hkjc_sco.DEBUT_MATRIX_WEIGHTS if top_debut else hkjc_sco.MATRIX_WEIGHTS
    w_base_win = hkjc_sco.DEBUT_MATRIX_WEIGHTS if win_debut else hkjc_sco.MATRIX_WEIGHTS
    w_cent = hkjc_sco.CENTRED_MATRIX_WEIGHTS
    f_top = hkjc_mm.DEBUT_MATRIX_FORMULAS if top_debut else hkjc_mm.MATRIX_FORMULAS
    f_win = hkjc_mm.DEBUT_MATRIX_FORMULAS if win_debut else hkjc_mm.MATRIX_FORMULAS

    top_matrix = top.get("matrix_scores") or {}
    win_matrix = win.get("matrix_scores") or {}

    parts: list[dict[str, Any]] = []
    leaf_rounding: dict[str, float] = {}

    snap_top, snap_win = _snapshot_weights(top), _snapshot_weights(win)
    weights_source = "snapshot" if snap_top and snap_win else "engine"
    for dim_key in hkjc_dim.all_keys():
        wt = float(w_base_top.get(dim_key, 0.0)) + (0.0 if top_debut else float(w_cent.get(dim_key, 0.0)))
        ww = float(w_base_win.get(dim_key, 0.0)) + (0.0 if win_debut else float(w_cent.get(dim_key, 0.0)))
        if weights_source == "snapshot":
            wt = snap_top.get(dim_key, 0.0)
            ww = snap_win.get(dim_key, 0.0)
        if wt == 0.0 and ww == 0.0:
            continue
        dim_top = float(top_matrix.get(dim_key, 60.0))
        dim_win = float(win_matrix.get(dim_key, 60.0))
        # 因 MATRIX_WEIGHTS 同 DEBUT_MATRIX_WEIGHTS 總和都係 1.0，全場置中 (dim - 60)
        # 加總等價於 w_top*dim_top - w_win*dim_win，而單維度喺 60 分時剛好歸零。
        dim_contrib = wt * (dim_top - 60.0) - ww * (dim_win - 60.0)
        parts.append({
            "kind": "dimension",
            "key": dim_key,
            "dimension": dim_key,
            "contribution": dim_contrib,
            "top_value": dim_top,
            "win_value": dim_win,
            "top_evidence": None,
            "win_evidence": None,
        })
        if leaf_level_valid:
            leaf_map_top = dict(f_top.get(dim_key, ()))
            leaf_map_win = dict(f_win.get(dim_key, ()))
            leaf_keys = list(dict.fromkeys([*leaf_map_top.keys(), *leaf_map_win.keys()]))
            leaf_sum = 0.0
            for lk in leaf_keys:
                lw_t = float(leaf_map_top.get(lk, 0.0))
                lw_w = float(leaf_map_win.get(lk, 0.0))
                if lk == "distance_fit_score":
                    tv = float(top_feats.get(lk, 60.0))
                    wv = float(win_feats.get(lk, 60.0))
                else:
                    tv = hkjc_sco.clip_score(top_feats.get(lk, 60.0))
                    wv = hkjc_sco.clip_score(win_feats.get(lk, 60.0))
                lc = wt * lw_t * (tv - 60.0) - ww * lw_w * (wv - 60.0)
                leaf_sum += lc
                parts.append({
                    "kind": "leaf",
                    "key": lk,
                    "dimension": dim_key,
                    "contribution": lc,
                    "top_value": tv,
                    "win_value": wv,
                    "top_evidence": _leaf_evidence(top, lk, tv, has_evidence_state=False),
                    "win_evidence": _leaf_evidence(win, lk, wv, has_evidence_state=False),
                })
            if dim_key == "race_shape":
                # 全場走位分封頂（median ± 10）會原地改 matrix_scores["race_shape"]，leaf 仲係未封頂嘅值：
                # 封頂差額獨立列一項，唔好收埋喺 leaf_rounding 入面（Hydrogen 2026-11-27）
                def _cap(pa: dict[str, Any]) -> float:
                    rsr = pa.get("race_shape_robustness")
                    if isinstance(rsr, dict) and rsr.get("applied") and rsr.get("base_race_shape") is not None:
                        return float(pa["matrix_scores"].get("race_shape", 60.0)) - float(rsr["base_race_shape"])
                    return 0.0
                cap_c = wt * _cap(top) - ww * _cap(win)
                if abs(cap_c) > 1e-12:
                    leaf_sum += cap_c
                    parts.append({"kind": "leaf", "key": "race_shape_robustness", "label": "走位分全場封頂",
                                  "dimension": dim_key, "contribution": cap_c, "top_value": _cap(top),
                                  "win_value": _cap(win), "top_evidence": None, "win_evidence": None})
            leaf_rounding[dim_key] = dim_contrib - leaf_sum

    top_adj = _hkjc_adjustments_map(top)
    win_adj = _hkjc_adjustments_map(win)
    all_adj_keys = list(dict.fromkeys([*top_adj.keys(), *win_adj.keys()]))
    for ak in all_adj_keys:
        tv = float(top_adj.get(ak, 0.0))
        wv = float(win_adj.get(ak, 0.0))
        contrib = tv - wv
        if abs(contrib) > 1e-12 or abs(tv) > 1e-12 or abs(wv) > 1e-12:
            parts.append({
                "kind": "adjustment",
                "key": ak,
                "dimension": None,
                "contribution": contrib,
                "top_value": tv,
                "win_value": wv,
                "top_evidence": None,
                "win_evidence": None,
            })

    thin_top = float(top_adj.get("thin_evidence", 0.0))
    thin_win = float(win_adj.get("thin_evidence", 0.0))
    nonlinear = bool(
        abs(thin_top) > 1e-9
        or abs(thin_win) > 1e-9
        or top.get("thin_evidence")
        or win.get("thin_evidence")
    )

    extra: dict[str, Any] = {
        "top_debut": top_debut,
        "win_debut": win_debut,
    }
    if field_pas:
        raws = [_float_or_none(_unwrap_pa(p).get("ability_score_raw")) for p in field_pas]
        valid_raws = [r for r in raws if r is not None]
        if valid_raws:
            extra["field_mean_raw"] = sum(valid_raws) / len(valid_raws)

    return _finalize_decomposition(
        parts=parts,
        total_gap=total_gap,
        official_gap=official_gap,
        leaf_rounding=leaf_rounding,
        leaf_level_valid=leaf_level_valid,
        nonlinear=nonlinear,
        swap=None,
        extra=dict(extra, weights_source=weights_source),
    )


# ---------------------------------------------------------------- Meeting / Day IO

def _load_logic_race(snapshot_dir: Path, race_num: int) -> dict[str, Any] | None:
    p = snapshot_dir / f"Race_{race_num}_Logic.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _horses_by_no(logic_data: dict[str, Any]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for key, h in (logic_data.get("horses") or {}).items():
        if not isinstance(h, dict):
            continue
        n = _int_or_none(h.get("horse_number") or key)
        if n is not None:
            out[n] = h
    return out


def _result_lookup(race_res: Any) -> dict[int, dict[str, Any]]:
    raw_rows = race_res.get("results") if isinstance(race_res, dict) else race_res
    out: dict[int, dict[str, Any]] = {}
    for r in raw_rows or []:
        if not isinstance(r, dict):
            continue
        n = _int_or_none(r.get("horse_no"))
        if n is not None:
            out[n] = r
    return out


def _pred_lookup(preds: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for p in preds or []:
        n = _int_or_none(p.get("horse_no"))
        if n is not None:
            out[n] = p
    return out


def _runner_summary(
    horse_no: int | None,
    *,
    rank: int | None,
    pa: dict[str, Any] | None,
    horse_obj: dict[str, Any] | None,
    pred_row: dict[str, Any] | None,
    res_row: dict[str, Any] | None,
    platform: str,
) -> dict[str, Any]:
    name = (
        (horse_obj or {}).get("horse_name")
        or (pred_row or {}).get("horse_name")
        or (res_row or {}).get("horse_name")
        or (f"#{horse_no}" if horse_no is not None else "未知")
    )
    score = None
    official_score = None
    if pa:
        if platform == "au":
            score = _float_or_none(pa.get("final_rank_score") if pa.get("final_rank_score") is not None else pa.get("ability_score"))
            official_score = _float_or_none(pa.get("ability_score"))
        else:
            score = _float_or_none(pa.get("ability_score_raw") if pa.get("ability_score_raw") is not None else pa.get("ability_score"))
            official_score = _float_or_none(pa.get("official_ranking_score", pa.get("ability_score")))
    sp = _sp_or_none((res_row or {}).get("odds") if (res_row or {}).get("odds") is not None else (res_row or {}).get("sp"))
    pos = _int_or_none((res_row or {}).get("placing"))
    return {
        "no": horse_no,
        "name": str(name).strip(),
        "rank": rank,
        "score": score,
        "official_score": official_score,
        "sp": sp,
        "pos": pos,
    }


def autopsy_meeting(platform: str, meeting_dir: Path | str) -> dict[str, Any]:
    """對單個賽日場次執行 Case A 逐對拆解（只讀賽前快照）。"""
    from wongchoi_paths import SnapshotArchiveOffline

    meeting_dir = Path(meeting_dir)
    core = _core()
    results_file = (
        (sorted(meeting_dir.glob("*全日賽果.json")) or [None])[0]
        if platform == "hkjc"
        else core.find_existing_results_file(platform, meeting_dir)
    )
    if not results_file:
        return {"meeting": meeting_dir.name, "reason": "no_results", "counters": _empty_counters(), "cases": []}

    results = core.load_structured_results(platform, Path(results_file))
    try:
        snapshot, _created, cutoff = core.select_prerace_snapshot(meeting_dir, platform)
    except SnapshotArchiveOffline:
        return {"meeting": meeting_dir.name, "reason": "offline", "counters": _empty_counters(), "cases": []}
    if cutoff is None:
        return {"meeting": meeting_dir.name, "reason": "缺開跑時間", "counters": _empty_counters(), "cases": []}
    if snapshot is None:
        return {"meeting": meeting_dir.name, "reason": "no_snapshot", "counters": _empty_counters(), "cases": []}

    snapshot_dir = Path(snapshot)
    preds = core.load_prediction_rows(snapshot_dir, platform)
    raw_cases, counters = select_case_a(preds, results)

    detailed_cases: list[dict[str, Any]] = []
    for case in raw_cases:
        race_num = int(case["race"])
        logic = _load_logic_race(snapshot_dir, race_num)
        if not logic:
            counters["notes"].append({"race": race_num, "note": "missing_logic_json"})
            continue

        horses = _horses_by_no(logic)
        top_no = case["top_pick_no"]
        win_no = case["winner_no"]
        top_h = horses.get(top_no) if top_no is not None else None
        win_h = horses.get(win_no)
        pa_top = (top_h or {}).get("python_auto")
        pa_win = (win_h or {}).get("python_auto")
        if not isinstance(pa_top, dict) or not isinstance(pa_win, dict):
            counters["notes"].append({"race": race_num, "note": "missing_python_auto"})
            continue

        if platform == "au":
            dtrace = (logic.get("python_auto_verdict") or {}).get("decision_trace")
            decomp = decompose_au(pa_top, pa_win, decision_trace=dtrace)
        else:
            field_pas = [
                h["python_auto"] for h in horses.values()
                if isinstance(h.get("python_auto"), dict)
            ]
            decomp = decompose_hkjc(pa_top, pa_win, field_pas)

        pred_map = _pred_lookup(preds.get(race_num) or preds.get(str(race_num)) or [])
        res_map = _result_lookup(results.get(race_num) or results.get(str(race_num)) or {})

        top_summary = _runner_summary(
            top_no, rank=1, pa=pa_top, horse_obj=top_h,
            pred_row=pred_map.get(top_no), res_row=res_map.get(top_no), platform=platform,
        )
        win_summary = _runner_summary(
            win_no, rank=2, pa=pa_win, horse_obj=win_h,
            pred_row=pred_map.get(win_no), res_row=res_map.get(win_no), platform=platform,
        )

        detailed_cases.append({
            "race": race_num,
            "field_size": case["field_size"],
            "fav_tied": case["fav_tied"],
            "top_pick": top_summary,
            "winner": win_summary,
            **decomp,
        })

    return {
        "meeting": meeting_dir.name,
        "reason": None,
        "counters": counters,
        "cases": detailed_cases,
    }


def autopsy_day(platform: str, day: str, root: Path | str | None = None) -> dict[str, Any]:
    """對指定日期所有場次執行 Case A 逐對拆解。"""
    import model_probability as M

    data_root = Path(root) if root is not None else M.default_root(platform)
    meetings_out: list[dict[str, Any]] = []
    total_counters = _empty_counters()
    all_cases: list[dict[str, Any]] = []

    for m in sorted(M.meeting_list(platform, data_root), key=lambda p: p.name):
        if m.name[:10] != day:
            continue
        try:   # 已知無效嘅 live 紀錄（例如 2026-10-07 跑馬地）一律剔走，同 model_probability 一樣（Hydrogen 2026-11-27）
            from live_record_exclusions import is_excluded
            if is_excluded(platform, m.name):
                continue
        except ImportError:
            pass
        res = autopsy_meeting(platform, m)
        meetings_out.append(res)
        c = res["counters"]
        for k in ("races_with_results", "fav_won", "fav_won_rank1", "fav_won_rank2", "fav_won_rank3plus", "sp_missing"):
            total_counters[k] += int(c.get(k) or 0)
        for r in c.get("dead_heat") or []:
            total_counters["dead_heat"].append({"meeting": res["meeting"], "race": r})
        for n in c.get("notes") or []:
            total_counters["notes"].append({"meeting": res["meeting"], **n})
        for case in res["cases"]:
            all_cases.append({"meeting": res["meeting"], **case})

    labels = _labels(platform)
    for case in all_cases:
        for key in ("parts", "top_reasons", "against", "weak_evidence_reasons"):
            for p in case.get(key) or []:
                p.setdefault("label", labels.get(p.get("key"), p.get("key")))

    return {
        "version": VERSION,
        "platform": platform,
        "date": day,
        "counters": total_counters,
        "meetings": meetings_out,
        "cases": all_cases,
    }


# ---------------------------------------------------------------- Markdown rendering

def _venue_label(meeting_name: str) -> str:
    if not meeting_name:
        return "未知場地"
    s = re.sub(r"^\d{4}-\d{2}-\d{2}[_\s]*", "", meeting_name).strip()
    s = re.sub(r"\s+Race\s+\d+(?:-\d+)?$", "", s, flags=re.IGNORECASE).strip()
    return s or meeting_name


def _fmt_sp(sp: Any) -> str:
    f = _sp_or_none(sp)
    if f is None:
        return "缺"
    return f"{f:.2f}".rstrip("0").rstrip(".") if f >= 10 else f"{f:.2f}"


def _fmt_part(p: dict[str, Any], labels: dict[str, str]) -> str:
    name = labels.get(p["key"], p["key"])
    return f"{name} {p['contribution']:+.2f}"


def _fmt_weak_part(p: dict[str, Any], labels: dict[str, str]) -> str:
    name = labels.get(p["key"], p["key"])
    tags = []
    for who, ev in (("首選", p.get("top_evidence")), ("大熱", p.get("win_evidence"))):
        if _ev_is_weak(ev):
            if ev.get("default_60"):
                tags.append(f"{who}預設60")
            else:
                tags.append(f"{who}{ev.get('state') or '缺資料'}")
    suffix = f"（{'、'.join(tags)}）" if tags else ""
    return f"{name} {p['contribution']:+.2f}{suffix}"


def _detect_platform(result: dict[str, Any]) -> str:
    if result.get("platform") in ("au", "hkjc"):
        return result["platform"]
    for case in result.get("cases") or []:
        if "top_debut" in case or "nonlinear" in case and case.get("official_gap") != case.get("total_gap"):
            return "hkjc"
    return "au"


def render_md(result: dict[str, Any]) -> str:
    """輸出香港粵語 Markdown 逐對拆解報告。"""
    platform = _detect_platform(result)
    labels = _labels(platform)
    plat_title = {"au": "AU", "hkjc": "HKJC"}.get(platform, platform.upper())

    if "meetings" in result:
        title_tail = result.get("date") or ""
        cases = result.get("cases") or []
        skipped = [m for m in result.get("meetings") or [] if m.get("reason")]
    else:
        title_tail = result.get("meeting") or ""
        cases = [dict(c, meeting=result.get("meeting", "")) for c in (result.get("cases") or [])]
        skipped = [result] if result.get("reason") else []

    c = result.get("counters") or {}
    dh_count = len(c.get("dead_heat") or [])
    lines = [
        f"# {plat_title} 逐對深入覆盤（Case A：大熱贏但模型排第 2）{title_tail}".strip(),
        "",
        (
            f"統計：有賽果 {c.get('races_with_results', 0)} 場；"
            f"大熱贏 {c.get('fav_won', 0)} 場"
            f"（模型第 1：{c.get('fav_won_rank1', 0)}、"
            f"第 2：{c.get('fav_won_rank2', 0)}、"
            f"第 3+：{c.get('fav_won_rank3plus', 0)}）；"
            f"缺 SP {c.get('sp_missing', 0)} 場；平頭冠軍 {dh_count} 場。"
        ),
        "",
    ]

    for m in skipped:
        lines.append(f"- 略過 {m.get('meeting', '?')}：{m.get('reason')}")
    if skipped:
        lines.append("")

    if not cases:
        lines.append("今期冇符合 Case A（大熱贏但模型排第 2）嘅場次。")
        return "\n".join(lines) + "\n"

    for case in cases:
        venue = _venue_label(str(case.get("meeting") or result.get("meeting") or ""))
        top = case.get("top_pick") or {}
        win = case.get("winner") or {}
        win_sp = _fmt_sp(win.get("sp"))
        top_sp = _fmt_sp(top.get("sp"))
        top_pos = f"第 {top['pos']}" if top.get("pos") else "無名次"
        gap_str = f"{float(case['total_gap']):+.2f}"
        if platform == "hkjc" and case.get("official_gap") is not None:
            gap_str += f"（顯示尺 {float(case['official_gap']):+.2f}）"

        top_r = "、".join(_fmt_part(p, labels) for p in (case.get("top_reasons") or [])) or "無"
        agn_r = "、".join(_fmt_part(p, labels) for p in (case.get("against") or [])) or "無"
        weak_r = "、".join(_fmt_weak_part(p, labels) for p in (case.get("weak_evidence_reasons") or [])) or "無"

        flags: list[str] = []
        if case.get("fav_tied"):
            flags.append("並列大熱")
        swap = case.get("swap")
        if isinstance(swap, dict) and swap.get("changed"):
            ts = swap.get("thin_evidence_swap") or {}
            if ts:
                flags.append(f"⚠️ 安全欄對調（原首選 #{ts.get('demoted')} 有 {ts.get('default_leaf_count')} 個預設 60，同 #{ts.get('promoted')} 互換）")
            else:
                flags.append(f"⚠️ 排名曾對調（{swap.get('reason') or 'decision_trace'}）")
        if case.get("nonlinear"):
            flags.append("⚠️ 含薄證據乘數收窄（非線性）")
        if not case.get("leaf_level_valid", True):
            flags.append("舊版快照（僅維度層）")
        if case.get("unexplained"):
            flags.append(f"⚠️ 未解釋殘差 {float(case.get('residual', 0.0)):+.2f}")

        flag_txt = (" [" + "；".join(flags) + "]") if flags else ""
        block = (
            f"R{case['race']} {venue}：大熱 {win.get('name', '?')}（SP {win_sp}，模型第 2）贏；"
            f"我哋首選 {top.get('name', '?')}（SP {top_sp}，{top_pos}）。"
            f"分差 {gap_str}。拉高首選：{top_r}；幫大熱：{agn_r}；證據薄：{weak_r}。{flag_txt}"
        )
        lines.append(f"- {block}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", choices=("au", "hkjc"), required=True)
    ap.add_argument("--date", help="YYYY-MM-DD（冇 --meeting 時必填）")
    ap.add_argument("--meeting", help="指定單一場次資料夾")
    ap.add_argument("--data-root", help="自訂資料根目錄")
    ap.add_argument("--json", action="store_true", help="輸出 JSON")
    args = ap.parse_args(argv)

    if args.meeting:
        res = autopsy_meeting(args.platform, Path(args.meeting))
        res.setdefault("platform", args.platform)
    else:
        if not args.date:
            ap.error("要有 --date 或者 --meeting")
        res = autopsy_day(args.platform, args.date, root=args.data_root)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    else:
        print(render_md(res), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
