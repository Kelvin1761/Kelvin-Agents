#!/usr/bin/env python3
"""EXP-20261028-14 walk-forward 揀值 + v3 判決。規格見 protocol —— 唔准喺度改。

    python3 au_g5_walkforward_20261028.py --dir X --out result.json

讀 X/g5_<值>.json（每個網格值一份真引擎 dump），逐窗只用之前嘅乾淨賽日揀值，
再用 `evaluate_full_record(mode="walk_forward_oos")` 對 2.31 判決（只計測試窗）。
"""
import argparse
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
for p in (SCRIPTS, SCRIPTS.parents[2] / "shared_racing"):
    sys.path.insert(0, str(p))
from au_eval import _counts, _stage4_metric_rows  # noqa: E402
from au_racing_engine.scoring import parse_placing  # noqa: E402
from model_evaluation_decision import evaluate_full_record  # noqa: E402

GRID = ("0", "1.0", "2.31", "3.5", "5.0", "7.0", "10.0")
ANCHOR = "2.31"
WARMUP, WINDOW = 30, 7
SCORE = lambda r: r["ability"]  # noqa: E731


def load(path):
    races = [r for r in json.loads(Path(path).read_text())["races"] if r["date"] >= "2026-08-05"
             and sum(x["pos"] <= 3 for x in r["rows"]) >= 3 and any(x["pos"] == 1 for x in r["rows"])]
    return sorted(races, key=lambda r: (r["date"], r["meeting"], r["race"]))


def pick(train):
    """合資格值嘅中位數；冇合資格就 anchor。唔取 argmax。"""
    c = {v: _counts(train[v], SCORE) for v in GRID}
    a = c[ANCHOR]
    ok = [v for v in GRID if v != ANCHOR and c[v]["gold"] >= a["gold"] and c[v]["good_positional"] >= a["good_positional"]
          and c[v]["gold"] + c[v]["good_positional"] > a["gold"] + a["good_positional"]]
    if not ok:
        return ANCHOR, c
    ok = sorted(ok, key=float)
    mid = len(ok) // 2
    if len(ok) % 2 == 0:   # 偶數個：兩個中間值取較近 2.31 嗰個
        lo, hi = ok[mid - 1], ok[mid]
        return (lo if abs(float(lo) - 2.31) <= abs(float(hi) - 2.31) else hi), c
    return ok[mid], c


def g5_flag(x):
    c = x["cls"]
    starts = c.get("career_starts") or 0
    if not 1 <= starts <= 5:
        return False
    place, n = parse_placing(c.get("latest_placing")), c.get("latest_field_size")
    if place is not None and n and n >= 2 and place <= n:
        return (place - 1) / (n - 1) <= 0.25
    return place is not None and place <= 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True); ap.add_argument("--out", required=True)
    args = ap.parse_args()
    data = {v: load(Path(args.dir) / f"g5_{v}.json") for v in GRID}
    keys = [(r["meeting"], r["race"]) for r in data[ANCHOR]]
    for v in GRID:
        assert [(r["meeting"], r["race"]) for r in data[v]] == keys, v
    days = sorted({r["date"] for r in data[ANCHOR]})
    windows, chosen = [], []
    for start in range(WARMUP, len(days), WINDOW):
        test_days = set(days[start:start + WINDOW])
        train = {v: [r for r in data[v] if r["date"] < days[start]] for v in GRID}
        value, counts = pick(train)
        windows.append({"test": [min(test_days), max(test_days)], "train_races": len(train[ANCHOR]), "chosen": value,
                        "train": {v: {k: round(counts[v][k], 3) for k in ("gold", "good_positional")} for v in GRID}})
        chosen += [(i, value) for i, r in enumerate(data[ANCHOR]) if r["date"] in test_days]
    base = [data[ANCHOR][i] for i, _ in chosen]
    cand = [data[v][i] for i, v in chosen]
    dates = [r["date"] for r in base]
    rb, rc = _stage4_metric_rows(base, SCORE), _stage4_metric_rows(cand, SCORE)
    verdict = evaluate_full_record(domain="au", mode="walk_forward_oos", dates=dates, baseline_rows=rb, candidate_rows=rc,
                                   leakage_audit_passed=True,
                                   ranking_metrics=("top3_capture_at5", "ndcg_at5", "top5_pairwise_auc"))
    final_value, final_counts = pick(data)

    def sp(x):
        try:
            return float(str(x).replace("$", ""))
        except (TypeError, ValueError):
            return None

    def top(r):
        return min(r["rows"], key=lambda x: (-x["ability"], x["n"]))
    fns = {"field": lambda r: "<=8" if len(r["rows"]) <= 8 else "9-10" if len(r["rows"]) <= 10 else "11-12" if len(r["rows"]) <= 12 else "13+",
           "top_pick_sp": lambda r: (lambda s: "unknown" if s is None else "$1-3" if s < 3 else "$3-5" if s < 5 else "$5-8" if s < 8 else "$8-15" if s < 15 else "$15+")(sp(top(r).get("sp"))),
           "has_g5_bonus": lambda r: str(any(g5_flag(x) for x in r["rows"]))}
    cohorts = {}
    for name, fn in fns.items():
        for key in sorted({fn(r) for r in base}):
            idx = [i for i, r in enumerate(base) if fn(r) == key]
            for metric in ("gold", "good_positional"):
                per = {}
                for i in idx:
                    per.setdefault(dates[i], []).append(float(rc[i][metric]) - float(rb[i][metric]))
                ds = sorted(per); rng = random.Random(7); samples = []
                for _ in range(2000):
                    pk = [ds[rng.randrange(len(ds))] for _ in ds]
                    flat = [d for day in pk for d in per[day]]
                    samples.append(sum(flat) / len(flat))
                samples.sort()
                flat = [d for day in ds for d in per[day]]
                cohorts[f"{name}:{key}:{metric}"] = {"n": len(idx), "delta_pp": round(100 * sum(flat) / len(flat), 2),
                                                    "ci_pp": [round(100 * samples[50], 2), round(100 * samples[1949], 2)]}
    out = {"test_races": len(base), "test_days": len(set(dates)), "windows": windows,
           "verdict": verdict["verdict"], "reason": verdict["reason"],
           "primary": {k: {kk: e[kk] for kk in ("delta", "ci_low", "ci_high", "p_value")} for k, e in verdict["detail"]["primary"].items()},
           "ranking": {k: {kk: e[kk] for kk in ("delta", "ci_low", "ci_high", "p_value")} for k, e in verdict["detail"]["ranking"].items()},
           "counts_base": _counts(base, SCORE), "counts_cand": _counts(cand, SCORE),
           "full_record_pick": final_value,
           "full_record_counts": {v: {k: round(final_counts[v][k], 3) for k in ("gold", "good_positional", "pass")} for v in GRID},
           "cohorts": cohorts, "cohort_ci_all_negative": [k for k, c in cohorts.items() if c["ci_pp"][1] < 0]}
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps({k: out[k] for k in ("test_races", "test_days", "verdict", "reason", "primary", "ranking",
                                          "full_record_pick", "cohort_ci_all_negative")}, indent=1))
    print("chosen per window:", [w["chosen"] for w in windows])
    for k in ("gold", "good_positional", "pass"):
        print(k, round(out["counts_base"][k], 2), "→", round(out["counts_cand"][k], 2))
    print("full record:", json.dumps(out["full_record_counts"]))


if __name__ == "__main__":
    main()
