"""EXP-20261016-01 研究變體切換（只喺研究 process 入面 patch，唔改 production 檔）。

production 已經係 F6 全部（試閘表現三條路剷走 + pace_perf 只剩 pace_figure）。
  base  F6 之前：cutoff 6 規則 + 舊 pace_perf 組合（A0）
  f6a   只剷 trial_score leaf（新 registry），PF 試閘行同初出馬時間代理照舊用 cutoff 6
  f6b   f6a + trial_score／初出馬時間代理對所有馬停用，PF 試閘行照舊用 cutoff 6
  f6c   production（F6 全部）

dump 同 refit 兩個 process 都要用同一個變體，否則 refit 會用新 registry 重算舊 dump。
"""
from __future__ import annotations

import math

OLD_PACE_PERF = (("pace_figure_score", 0.941744), ("trial_score", 0.058256))
OLD_PACE_PERF_COEF = 0.12093934478578448
VARIANTS = ("base", "f6a", "f6b", "f6c")


def apply(variant: str) -> None:
    if variant not in VARIANTS:
        raise SystemExit(f"unknown variant {variant!r}; choose {VARIANTS}")
    from au_racing_engine import dimensions, engine_core

    if variant == "base":
        dimensions.MATRIX_FORMULAS["pace_perf"] = OLD_PACE_PERF
        dimensions.MATRIX_WEIGHTS["pace_perf"] = OLD_PACE_PERF_COEF
    if variant in ("base", "f6a"):
        engine_core.TRIAL_PERFORMANCE_REMOVED = False
    if variant == "f6b":
        _keep_pf_trial_rows_under_cutoff(engine_core)


def _keep_pf_trial_rows_under_cutoff(engine_core) -> None:
    """f6b: everything removed except the PF trial-row filter, which keeps the
    pre-F6 cutoff-6 rule (horses under 6 starts keep trial PF rows)."""
    import au_auto_orchestrator

    def old_applies(horse):
        starts = engine_core.parse_float(horse.get("career_race_starts"))
        return not (starts is not None and math.isfinite(starts)
                    and starts >= engine_core.TRIAL_PERFORMANCE_START_CUTOFF)

    def performance_pf_metrics(horse):
        metrics = ((horse.get("_data") or {}).get("pf_metrics") or {})
        if old_applies(horse):
            return metrics
        runs = metrics.get("pf_runs") or []
        kept = [run for run in runs if run.get("run_kind") != "trial"]
        if len(kept) == len(runs):
            return metrics
        source = (metrics.get("pf_aggregates") or {}).get("source", "unknown")
        return {**metrics, "pf_runs": kept,
                "pf_aggregates": engine_core._pf_aggregates([dict(run) for run in kept], source)}

    engine_core.performance_pf_metrics = performance_pf_metrics
    au_auto_orchestrator.performance_pf_metrics = performance_pf_metrics
