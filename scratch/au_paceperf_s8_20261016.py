#!/usr/bin/env python3
"""合約 §8 四 arm 判決（EXP-20261016-01）。

輸入兩份 `au_walkforward_refit.py predict` 輸出：baseline（A0=live、B0=refit）同
candidate（A1=live、B1=refit）。逐場對齊（日期、場次、場號、馬號、名次）先判。

procedure hash：兩份嘅程序只可以喺 `anchor_weights` 唔同（每個 arm 用自己嘅
live 權重做 anchor／fallback，§8 本身就係咁定義）。其餘設定同工具 source 一定要
一樣，否則拒絕。

歷史來源 availability 仍係 FLAG：正式判決用 leakage_audit_passed=False（一定
REJECT / leakage_audit_failed）；另報 True 嘅研究診斷，**唔准當 WIN**。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parents[2] / "shared_racing"))

from au_eval import _counts  # noqa: E402
from au_walkforward_refit import RANKING_METRICS, arm_metric_rows, arm_races  # noqa: E402
from model_evaluation_decision import evaluate_with_refit_arms  # noqa: E402


def key(race):
    return (race["date"], race["meeting"], race["race"],
            tuple((r["n"], r["pos"]) for r in race["rows"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--cand", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    base = json.loads(Path(args.base).read_text(encoding="utf-8"))
    cand = json.loads(Path(args.cand).read_text(encoding="utf-8"))
    tool_source = (SCRIPTS / "au_walkforward_refit.py").read_bytes()
    hashes = []
    for pred in (base, cand):
        procedure = {k: v for k, v in pred["procedure"].items() if k != "anchor_weights"}
        body = json.dumps(procedure, sort_keys=True, ensure_ascii=False).encode()
        hashes.append(hashlib.sha256(body + b"\0" + tool_source).hexdigest())

    bmap = {key(r): r for r in base["predictions"]}
    cmap = {key(r): r for r in cand["predictions"]}
    common = sorted(set(bmap) & set(cmap))
    dropped = {"base_only": len(bmap) - len(common), "cand_only": len(cmap) - len(common)}
    bp = [bmap[k] for k in common]
    cp = [cmap[k] for k in common]
    dates = [r["date"] for r in bp]
    rows = {"A0": arm_metric_rows(bp, "live"), "B0": arm_metric_rows(bp, "refit"),
            "A1": arm_metric_rows(cp, "live"), "B1": arm_metric_rows(cp, "refit")}
    score = lambda r: r["ability"]  # noqa: E731
    counts = {"A0": _counts(arm_races(bp, "live"), score), "B0": _counts(arm_races(bp, "refit"), score),
              "A1": _counts(arm_races(cp, "live"), score), "B1": _counts(arm_races(cp, "refit"), score)}

    def judge(passed):
        return evaluate_with_refit_arms(
            domain="au", dates=dates,
            live_baseline_rows=rows["A0"], live_candidate_rows=rows["A1"],
            refit_baseline_rows=rows["B0"], refit_candidate_rows=rows["B1"],
            baseline_refit_procedure_hash=hashes[0], candidate_refit_procedure_hash=hashes[1],
            leakage_audit_passed=passed, ranking_metrics=RANKING_METRICS)

    formal, research = judge(False), judge(True)
    out = {"label": args.label, "races": len(common), "meeting_days": len(set(dates)),
           "alignment": dropped, "algorithm_hashes": hashes,
           "anchor_weights": {"base": base["procedure"]["anchor_weights"],
                              "cand": cand["procedure"]["anchor_weights"]},
           "windows_fallback": {"base": [w.get("fallback") for w in base["windows"]],
                                "cand": [w.get("fallback") for w in cand["windows"]]},
           "counts": counts, "formal": formal, "research_diagnostic": research}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    print(f"== {args.label}: races {len(common)} days {len(set(dates))} alignment {dropped}")
    print(f"   hash symmetric: {hashes[0] == hashes[1]}")
    for arm in ("A0", "A1", "B0", "B1"):
        c = counts[arm]
        print(f"   {arm}  gold {c['gold']:6.2f}%  good {c['good_positional']:6.2f}%  pass {c['pass']:6.2f}%")
    print(f"   formal   : {formal['verdict']} / {formal['reason']}")
    print(f"   research : {research['verdict']} / {research['reason']}  package={research.get('package')}")
    detail = research.get("detail") or {}
    for name in ("fixed", "refit"):
        arm = (detail.get("arms") or {}).get(name) or {}
        print(f"   arm {name:5}: {arm.get('verdict')} / {arm.get('reason')}")
        for sec in ("primary", "ranking"):
            for metric, ev in ((arm.get("detail") or {}).get(sec) or {}).items():
                print(f"      {metric:20} Δ {ev['delta']:+.5f} CI [{ev['ci_low']:+.5f}, {ev['ci_high']:+.5f}] "
                      f"p {ev['p_value']:.3f} blocks " + " ".join(f"{b:+.3f}" for b in ev["block_deltas"]))
    guard = detail.get("live_guard") or {}
    print(f"   live guard B1 vs A0: {guard.get('verdict')} / {guard.get('reason')}")
    print(f"   baseline_weights_stale: {detail.get('baseline_weights_stale')}  arm p holm {detail.get('arm_p_holm')}")


if __name__ == "__main__":
    main()
