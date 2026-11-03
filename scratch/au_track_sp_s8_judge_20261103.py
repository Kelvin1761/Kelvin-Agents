#!/usr/bin/env python3
"""EXP-20261103-04 判決：場地 SP 用合約 §8 四個 arm（A0／A1 現行權重、B0／B1 walk-forward refit）。

    judge.py DUMP_DIR OUT.json

DUMP_DIR 要有 BASE.json、SP.json（`au_dump_engine_leaves.py`）同 wf_BASE.json、wf_SP.json
（`au_walkforward_refit.py predict`）。四個 arm 全部喺 walk-forward 預測覆蓋嘅場次上判（warmup 之後）。
另外報告 stale（B0 vs A0）同 B1 vs B0 嘅分層。預先登記：`EXP-20261103-04-au-track-specialism-s8-protocol.md`。
"""
import json
import random
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[1]
S = W / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path[:0] = [str(S), str(W / ".agents/skills/shared_racing")]
from au_walkforward_refit import arm_metric_rows, arm_races, stale_check  # noqa: E402
from au_eval import _counts  # noqa: E402
from model_evaluation_decision import evaluate_with_refit_arms  # noqa: E402

RANKING = ("top3_capture_at5", "ndcg_at5", "top5_pairwise_auc")


def sp(x):
    try:
        return float(str(x).replace("$", ""))
    except (TypeError, ValueError):
        return None


def going_state(g):
    import re
    m = re.search(r"(Soft|Heavy)\s*([0-9]+)", str(g or ""), re.I)
    if not m:
        return "good/other"
    return "heavy" if m.group(1).lower() == "heavy" else ("soft7+" if int(m.group(2)) >= 7 else "soft5-6")


def cohorts(preds, meta, rb, rc):
    """分層 Gold／Good Δ（賽日 bootstrap 2000、seed 7）。meta：(meeting, race) → dump race。"""
    def top_sp(i):
        rows = sorted(preds[i]["rows"], key=lambda r: (-r["ability_live"], r["n"]))
        dump = {r["n"]: r for r in meta[(preds[i]["meeting"], preds[i]["race"])]["rows"]}
        s = sp(dump[rows[0]["n"]].get("sp"))
        return "unknown" if s is None else "$1-3" if s < 3 else "$3-6" if s < 6 else "$6+"

    def dist(i):
        try:
            d = float(str(meta[(preds[i]["meeting"], preds[i]["race"])]["rows"][0].get("distance")).rstrip("m"))
        except (TypeError, ValueError):
            return "?"
        return "<=1200" if d <= 1200 else "1201-1600" if d <= 1600 else ">1600"

    fns = {"field": lambda i: "<=8" if len(preds[i]["rows"]) <= 8 else "9-12" if len(preds[i]["rows"]) <= 12 else "13+",
           "going": lambda i: going_state(meta[(preds[i]["meeting"], preds[i]["race"])]["rows"][0].get("going")),
           "top_pick_sp": top_sp, "distance": dist}
    out = {}
    for name, fn in fns.items():
        keys = [fn(i) for i in range(len(preds))]
        for key in sorted(set(keys)):
            idx = [i for i, k in enumerate(keys) if k == key]
            for metric in ("gold", "good_positional"):
                by_day = {}
                for i in idx:
                    by_day.setdefault(preds[i]["date"], []).append(float(rc[i][metric]) - float(rb[i][metric]))
                days = sorted(by_day)
                rng = random.Random(7)
                samples = []
                for _ in range(2000):
                    flat = [d for day in (days[rng.randrange(len(days))] for _ in days) for d in by_day[day]]
                    samples.append(sum(flat) / len(flat))
                samples.sort()
                flat = [d for day in days for d in by_day[day]]
                out[f"{name}:{key}:{metric}"] = {"n": len(idx), "delta_pp": round(100 * sum(flat) / len(flat), 2),
                                                 "ci_pp": [round(100 * samples[50], 2), round(100 * samples[1949], 2)]}
    return out


def main():
    root, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    wb, wc = (json.loads((root / f).read_text()) for f in ("wf_BASE.json", "wf_SP.json"))
    pb, pc = wb["predictions"], wc["predictions"]
    assert [(r["meeting"], r["race"]) for r in pb] == [(r["meeting"], r["race"]) for r in pc]
    meta = {(r["meeting"], r["race"]): r for r in json.loads((root / "BASE.json").read_text())["races"]}
    dates = [r["date"] for r in pb]
    a0, a1 = arm_metric_rows(pb, "live"), arm_metric_rows(pc, "live")
    b0, b1 = arm_metric_rows(pb, "refit"), arm_metric_rows(pc, "refit")
    verdict = evaluate_with_refit_arms(
        domain="au", dates=dates, live_baseline_rows=a0, live_candidate_rows=a1,
        refit_baseline_rows=b0, refit_candidate_rows=b1,
        baseline_refit_procedure_hash=wb["procedure_hash"], candidate_refit_procedure_hash=wc["procedure_hash"],
        leakage_audit_passed=True, ranking_metrics=RANKING)
    score = lambda r: r["ability"]  # noqa: E731
    counts = {arm: _counts(arm_races(p, k), score)
              for arm, p, k in (("A0", pb, "live"), ("A1", pc, "live"), ("B0", pb, "refit"), ("B1", pc, "refit"))}
    stale = stale_check(pb)
    coh_fixed, coh_refit = cohorts(pb, meta, a0, a1), cohorts(pb, meta, b0, b1)
    report = {"races": len(pb), "meeting_days": len(set(dates)), "procedure_hash": wb["procedure_hash"],
              "verdict": verdict, "counts": counts,
              "stale_B0_vs_A0": {"verdict": stale["verdict"]["verdict"], "reason": stale["verdict"]["reason"],
                                 "detail": stale["verdict"]["detail"]},
              "cohorts_fixed": coh_fixed, "cohorts_refit": coh_refit,
              "cohort_ci_all_negative_fixed": [k for k, c in coh_fixed.items() if c["ci_pp"][1] < 0],
              "cohort_ci_all_negative_refit": [k for k, c in coh_refit.items() if c["ci_pp"][1] < 0],
              "fallback_windows": {"BASE": sum(bool(w["fallback"]) for w in wb["windows"]),
                                   "SP": sum(bool(w["fallback"]) for w in wc["windows"]),
                                   "total": len(wb["windows"])}}
    out_path.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    print(json.dumps({k: report[k] for k in ("races", "meeting_days", "fallback_windows")}, ensure_ascii=False))
    print("verdict:", verdict.get("verdict"), "| reason:", verdict.get("reason"), "| package:", verdict.get("package"))
    d = verdict.get("detail") or {}
    print("arm p:", d.get("arm_p_values"), "holm:", d.get("arm_p_holm"))
    for arm in ("fixed", "refit"):
        a = (d.get("arms") or {}).get(arm) or {}
        print(f" {arm}: {a.get('verdict')}/{a.get('reason')}")
        for sec in ("primary", "ranking"):
            for name, ev in ((a.get("detail") or {}).get(sec) or {}).items():
                print(f"   {name:20s} {100*ev['delta']:+.3f} [{100*ev['ci_low']:+.3f},{100*ev['ci_high']:+.3f}] p={ev['p_value']:.3f}")
    lg = d.get("live_guard") or {}
    print(" live_guard:", lg.get("verdict"), lg.get("reason"))
    for k, v in counts.items():
        print(f"  {k}: gold {v['gold']:.2f}  good {v['good_positional']:.2f}  pass {v['pass']:.2f}")
    print("stale B0 vs A0:", report["stale_B0_vs_A0"]["verdict"], report["stale_B0_vs_A0"]["reason"])
    print("cohort CI<0 fixed:", report["cohort_ci_all_negative_fixed"], " refit:", report["cohort_ci_all_negative_refit"])


if __name__ == "__main__":
    main()
