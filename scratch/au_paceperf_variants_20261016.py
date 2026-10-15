"""EXP-20261016-01 研究變體切換（只喺研究 process 入面 patch，唔改 production 檔）。

production 而家係 F6a（用戶 2026-10-16 揀定）。
  base  F6 之前：舊 pace_perf 組合（A0）
  f6a   production：只剷 trial_score leaf，PF 試閘行同初出馬時間代理照舊用 cutoff 6
  f6b／f6c 要喺 commit 11214518 先重現得到（嗰時 production 係三條路全剷）。

dump 同 refit 兩個 process 都要用同一個變體，否則 refit 會用新 registry 重算舊 dump。
"""
from __future__ import annotations

OLD_PACE_PERF = (("pace_figure_score", 0.941744), ("trial_score", 0.058256))
OLD_PACE_PERF_COEF = 0.12093934478578448
VARIANTS = ("base", "f6a", "f6b", "f6c")


def apply(variant: str) -> None:
    if variant not in VARIANTS:
        raise SystemExit(f"unknown variant {variant!r}; choose {VARIANTS}")
    from au_racing_engine import dimensions

    if variant == "base":
        dimensions.MATRIX_FORMULAS["pace_perf"] = OLD_PACE_PERF
        dimensions.MATRIX_WEIGHTS["pace_perf"] = OLD_PACE_PERF_COEF
    if variant in ("f6b", "f6c"):
        raise SystemExit("f6b/f6c only reproduce at commit 11214518")
