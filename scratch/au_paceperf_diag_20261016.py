#!/usr/bin/env python3
"""EXP-20261016-01 診斷（D1–D3）同 F4／F5 揀形狀量度。只量度，唔改模型。

讀 `au_paceperf_dump_20261016.py` 嘅 dump，離線重算 L600 leaf 嘅變體：
逐場 own_i、聚合、場內 z、60 − 20z，同 production `_pace_figure_score` 同一條式。
規格見 docs/experiments/EXP-20261016-01-au-pace-perf-protocol.md —— 唔准喺度改。
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from pathlib import Path

CLEAN_SINCE = "2026-08-05"
SEC_PER_LENGTH = 0.17
BOOT, SEED = 2000, 7


# ── leaf 重算 ───────────────────────────────────────────────────────────────
def own_values(runs, spl=None):
    """Production own_l600 for Sportsbet runs (base + margin × s/L)."""
    out = []
    for run in runs:
        base, margin = run.get("l600_delta"), run.get("margin")
        if run.get("source") != "sportsbet_race_context" or base is None or margin is None:
            continue
        sec = spl(run) if spl else SEC_PER_LENGTH
        out.append((run, float(base) + float(margin) * sec))
    return out


def race_values(runs):
    return [(run, float(run["l600_delta"])) for run in runs if run.get("l600_delta") is not None]


def mean(values):
    return sum(values) / len(values)


AGGREGATORS = {
    "base": lambda pairs: mean([v for _, v in pairs]),
    "D2a_cap6": None, "D2b_cap10": None,          # handled in own step (margin cap)
    "D2c_median": lambda pairs: statistics.median(v for _, v in pairs),
    "D2d_drop_worst": lambda pairs: (mean(sorted(v for _, v in pairs)[:-1])
                                     if len(pairs) >= 3 else mean([v for _, v in pairs])),
    "D3a_last3": lambda pairs: mean([v for _, v in pairs[:3]]),
    "D3b_last5": lambda pairs: mean([v for _, v in pairs[:5]]),
    "D3c_decay08": lambda pairs: (sum(v * 0.8 ** k for k, (_, v) in enumerate(pairs))
                                  / sum(0.8 ** k for k in range(len(pairs)))),
}


def runner_x(runs, variant, spl=None):
    """→ (basis, x). Runs are newest first, as the Formguide lists them."""
    runs = sorted(runs, key=lambda r: r.get("run_date") or "", reverse=True)
    if variant in ("D2a_cap6", "D2b_cap10"):
        cap = 6.0 if variant == "D2a_cap6" else 10.0
        capped = [{**r, "margin": min(float(r["margin"]), cap)} if r.get("margin") is not None
                  else r for r in runs]
        own, agg = own_values(capped, spl), AGGREGATORS["base"]
    else:
        own, agg = own_values(runs, spl), AGGREGATORS[variant]
    race = race_values(runs)
    return (agg(own) if own else None), (agg(race) if race else None)


def field_scores(rows, variant, spl=None, zcap=None):
    """Field-relative PF leaf for every runner, same fallback rule as production."""
    xs = [runner_x(r.get("pf_run_list") or [], variant, spl) for r in rows]
    own_field = [o for o, _ in xs if o is not None]
    race_field = [x for _, x in xs if x is not None]
    scores = []
    for own, race in xs:
        if own is not None and len(own_field) >= 3:
            value, field = own, own_field
        elif race is not None and len(race_field) >= 3:
            value, field = race, race_field
        else:
            scores.append(None)
            continue
        mu, sd = mean(field), statistics.pstdev(field)
        if sd <= 0:
            scores.append(None)
            continue
        z = (value - mu) / sd
        if zcap is not None:
            z = max(-zcap, min(zcap, z))
        scores.append(max(0.0, min(100.0, 60 - 20 * z)))
    return scores


# ── 評估 ───────────────────────────────────────────────────────────────────
def evaluable(race):
    pos = [r["pos"] for r in race["rows"]]
    return sum(p <= 3 for p in pos) >= 3 and any(p == 1 for p in pos)


def day_pairs(races, scores_by_race):
    """{day: [concordant_weight, pairs]} for in-race top3-vs-rest pairs."""
    out = {}
    for race, scores in zip(races, scores_by_race):
        ok = [(s, r["pos"] <= 3) for s, r in zip(scores, race["rows"]) if s is not None]
        hits = [s for s, top in ok if top]
        miss = [s for s, top in ok if not top]
        conc = sum(1.0 if h > m else 0.5 if h == m else 0.0 for h in hits for m in miss)
        cell = out.setdefault(race["date"], [0.0, 0])
        cell[0] += conc
        cell[1] += len(hits) * len(miss)
    return out


def auc(days, picks=None):
    keys = picks if picks is not None else list(days)
    c = sum(days[d][0] for d in keys)
    n = sum(days[d][1] for d in keys)
    return c / n if n else float("nan")


def paired_ci(base_days, cand_days):
    days = sorted(set(base_days) & set(cand_days))
    rng = random.Random(SEED)
    point = auc(cand_days, days) - auc(base_days, days)
    samples = []
    for _ in range(BOOT):
        pick = [days[rng.randrange(len(days))] for _ in days]
        samples.append(auc(cand_days, pick) - auc(base_days, pick))
    samples.sort()
    lo, hi = samples[int(BOOT * 0.025)], samples[int(BOOT * 0.975) - 1]
    p = min(1.0, 2 * min(sum(s <= 0 for s in samples), sum(s >= 0 for s in samples)) / BOOT)
    return point, lo, hi, p


def holm(pvals):
    ordered = sorted(pvals.items(), key=lambda kv: kv[1])
    out, running, m = {}, 0.0, len(ordered)
    for rank, (k, p) in enumerate(ordered):
        running = max(running, min(1.0, (m - rank) * p))
        out[k] = running
    return out


# ── D1 ─────────────────────────────────────────────────────────────────────
def settle_fraction(runs):
    vals = [(r["pos_settled"] - 1) / (r["starters"] - 1) for r in runs
            if r.get("run_kind") == "formal" and r.get("pos_settled") and (r.get("starters") or 0) >= 2
            and 1 <= r["pos_settled"] <= r["starters"]]
    return mean(vals) if vals else None


def style_bucket(frac):
    if frac is None:
        return None
    return "front" if frac < 1 / 3 else "back" if frac > 2 / 3 else "mid"


def label_bucket(line):
    text = str(line or "")
    if "後上" in text or "後追" in text or "包尾" in text:
        return "back"
    if "前置" in text or "領放" in text or "放頭" in text:
        return "front"
    if "守中" in text or "中間" in text:
        return "mid"
    return None


def d1_records(races, scores_by_race, bucket_fn):
    recs = []   # (day, quintile, bucket, excess)
    for race, scores in zip(races, scores_by_race):
        ok = [(s, r) for s, r in zip(scores, race["rows"]) if s is not None]
        if len(ok) < 5:
            continue
        ranked = sorted(ok, key=lambda sr: -sr[0])
        n_field = len(race["rows"])
        for i, (s, r) in enumerate(ranked):
            b = bucket_fn(r)
            if b is None:
                continue
            q = min(4, int(5 * i / len(ranked)))
            recs.append((race["date"], q, b, (1.0 if r["pos"] <= 3 else 0.0) - min(3, n_field) / n_field))
    return recs


def d1_stat(recs, days=None):
    if days is not None:
        mult = {}
        for d in days:
            mult[d] = mult.get(d, 0) + 1
        recs = [rec for rec in recs for _ in range(mult.get(rec[0], 0))]
    total_w, acc = 0, 0.0
    for q in range(5):
        back = [e for _, qq, b, e in recs if qq == q and b == "back"]
        front = [e for _, qq, b, e in recs if qq == q and b == "front"]
        if back and front:
            w = len(back) + len(front)
            acc += w * (mean(back) - mean(front))
            total_w += w
    return acc / total_w if total_w else float("nan")


def d1_report(recs):
    days = sorted({r[0] for r in recs})
    point = d1_stat(recs)
    rng = random.Random(SEED)
    samples = sorted(d1_stat(recs, [days[rng.randrange(len(days))] for _ in days]) for _ in range(BOOT))
    table = {}
    for q in range(5):
        for b in ("front", "mid", "back"):
            vals = [e for _, qq, bb, e in recs if qq == q and bb == b]
            table[f"q{q + 1}_{b}"] = {"n": len(vals), "excess_pp": round(100 * mean(vals), 2) if vals else None}
    return {"stat_pp": round(100 * point, 2),
            "ci_pp": [round(100 * samples[int(BOOT * 0.025)], 2), round(100 * samples[int(BOOT * 0.975) - 1], 2)],
            "n": len(recs), "cells": table}


# ── main ───────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    races = [r for r in json.loads(Path(args.data).read_text(encoding="utf-8"))["races"] if evaluable(r)]
    clean = [r for r in races if r["date"] >= CLEAN_SINCE]
    shape = [r for r in races if r["date"] < CLEAN_SINCE]
    report = {"races_clean": len(clean), "races_shape_window": len(shape),
              "days_clean": len({r["date"] for r in clean})}

    # replica check: recomputed base vs engine leaf (field stats differ: engine sees whole Logic field)
    base_scores = [field_scores(r["rows"], "base") for r in clean]
    diffs = [abs(s - r["features"]["pace_figure_score"]) for race, sc in zip(clean, base_scores)
             for s, r in zip(sc, race["rows"]) if s is not None]
    report["replica"] = {"runners": len(diffs), "exact_within_0.5": round(sum(d <= 0.5 for d in diffs) / max(1, len(diffs)), 4),
                         "median_abs_diff": round(statistics.median(diffs), 3) if diffs else None}

    # all variants on the replica, so baseline and candidate share one arithmetic
    base_days = day_pairs(clean, base_scores)
    report["leaf_auc_base"] = round(auc(base_days), 5)
    variants, pvals = {}, {}
    for name in AGGREGATORS:
        if name == "base":
            continue
        days = day_pairs(clean, [field_scores(r["rows"], name) for r in clean])
        point, lo, hi, p = paired_ci(base_days, days)
        variants[name] = {"auc": round(auc(days), 5), "delta": round(point, 5),
                          "ci": [round(lo, 5), round(hi, 5)], "p": round(p, 4)}
        pvals[name] = p
    for name, padj in holm(pvals).items():
        variants[name]["p_holm"] = round(padj, 4)
    report["D2_D3"] = variants

    runs = [run for race in clean for r in race["rows"] for run in (r.get("pf_run_list") or [])
            if run.get("margin") is not None]
    report["D2_margin_share"] = {"runs": len(runs),
                                 "gt10L": round(sum(float(x["margin"]) > 10 for x in runs) / max(1, len(runs)), 4),
                                 "gt6L": round(sum(float(x["margin"]) > 6 for x in runs) / max(1, len(runs)), 4)}

    report["D1_settle_history"] = d1_report(d1_records(
        clean, base_scores, lambda r: style_bucket(settle_fraction(r.get("pf_run_list") or []))))
    report["D1_style_label"] = d1_report(d1_records(clean, base_scores, lambda r: label_bucket(r.get("style"))))

    # F4: v_ref from the shape window only
    speeds = [run["distance"] / run["winning_time"] for race in shape for r in race["rows"]
              for run in (r.get("pf_run_list") or [])
              if run.get("distance") and run.get("winning_time") and run["winning_time"] > 20]
    report["F4"] = {"runs_with_speed": len(speeds),
                    "v_ref_mps": round(statistics.median(speeds), 4) if speeds else None}

    # F5: curve of engine PF leaf → excess top-3 rate, shape window only
    bins = {}
    for race in shape:
        n = len(race["rows"])
        for r in race["rows"]:
            s = r["features"]["pace_figure_score"]
            if s == 60.0:
                continue
            b = int(min(95, s) // 5 * 5)
            bins.setdefault(b, []).append((1.0 if r["pos"] <= 3 else 0.0) - min(3, n) / n)
    report["F5_shape_curve"] = {str(b): {"n": len(v), "excess_pp": round(100 * mean(v), 2)}
                                for b, v in sorted(bins.items())}
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())
