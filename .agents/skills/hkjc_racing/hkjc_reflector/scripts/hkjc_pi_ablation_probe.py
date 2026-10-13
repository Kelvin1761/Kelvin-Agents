#!/usr/bin/env python3
"""EXP-20261013-12：HKJC 剷走「走位 PI」嘅 ablation（研究工具，唔改 live）。

做法：喺 `review_auto_weighting.MODEL_SPECS` 注入兩個模型，行完全一樣嘅路徑：
  * `ctl_replay`：feature_transform 原封不動（對照組 —— 證明路徑本身唔造差異）
  * `cand_no_pi`：用 PI 權重全部 = 0 嘅 scoring 重跑引擎，攞返佢嘅 feature
然後用 shared `model_evaluation_decision`（Stage 4 v2）比 cand vs ctl。

    PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 hkjc_pi_ablation_probe.py
"""
from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import review_auto_weighting as raw  # noqa: E402
from hkjc_racing_engine import scoring  # noqa: E402
from hkjc_racing_engine.engine_core import RacingEngine  # noqa: E402
from hkjc_no_regression_gate import _canonical_metrics  # noqa: E402
from hkjc_results_db import get_analysis_archive_root, get_season_csvs, get_season_results_roots  # noqa: E402
from model_evaluation_decision import build_evaluation_input, evaluate_candidate  # noqa: E402

PI_KEYS = {
    "RACE_SHAPE_FIT_WEIGHTS": ("pi_up_bonus", "pi_micro_up_bonus", "pi_down_pen", "pi_micro_down_pen"),
    "RACE_SHAPE_CONTEXT_DELTA_WEIGHTS": ("pi_up_bonus", "pi_down_pen"),
}


@contextmanager
def no_pi():
    saved = {}
    for table, keys in PI_KEYS.items():
        t = getattr(scoring, table)
        for k in keys:
            saved[(table, k)] = t[k]
            t[k] = 0.0
    try:
        yield
    finally:
        for (table, k), v in saved.items():
            getattr(scoring, table)[k] = v


def _features(horse, ctx):
    auto = RacingEngine(deepcopy(horse), dict(ctx or {})).analyze_horse()
    f = dict(auto.get("feature_scores") or {})
    f.update(auto.get("derived_feature_scores") or {})
    return f


def ctl_transform(horse, features, ctx=None):
    return _features(horse, ctx)


def no_pi_transform(horse, features, ctx=None):
    with no_pi():
        return _features(horse, ctx)


def main() -> int:
    raw.MODEL_SPECS["ctl_replay"] = {"formulas": raw.CURRENT_MATRIX_FORMULAS,
                                     "weights": raw.CURRENT_MATRIX_WEIGHTS,
                                     "feature_transform": ctl_transform}
    raw.MODEL_SPECS["cand_no_pi"] = {"formulas": raw.CURRENT_MATRIX_FORMULAS,
                                     "weights": raw.CURRENT_MATRIX_WEIGHTS,
                                     "feature_transform": no_pi_transform}
    review = raw.run_review([get_analysis_archive_root()],
                            get_season_results_roots() + [get_analysis_archive_root()],
                            get_season_csvs(), include_races=True)
    races = [r for r in review["race_records"]
             if {"ctl_replay", "cand_no_pi", "current_live"} <= set(r.get("models", {})) and r.get("date")]
    # 路徑檢查：對照組同 current_live 排名要一樣，否則比較冇意義
    same = sum(1 for r in races if _canonical_metrics(r, "ctl_replay") == _canonical_metrics(r, "current_live"))
    changed = sum(1 for r in races if _canonical_metrics(r, "cand_no_pi") != _canonical_metrics(r, "ctl_replay"))
    print(f"{len(races)} 場；對照組同 live 一致 {same}/{len(races)}；剷 PI 之後排名有變 {changed} 場")
    built = build_evaluation_input(
        domain="hkjc", dates=[str(r["date"]) for r in races],
        baseline_rows=[_canonical_metrics(r, "ctl_replay") for r in races],
        candidate_rows=[_canonical_metrics(r, "cand_no_pi") for r in races],
        leakage_audit_passed=True, holdout_fraction=0.15,
        ranking_metrics=("top3_capture_at5", "ndcg_at5", "competitive_recall_at5"))
    decision = evaluate_candidate(built)
    print(json.dumps({k: decision.get(k) for k in ("verdict", "reason", "detail")}, ensure_ascii=False, indent=1,
                     default=str)[:4000])
    print("summary ctl :", review["model_summary"].get("ctl_replay"))
    print("summary cand:", review["model_summary"].get("cand_no_pi"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
