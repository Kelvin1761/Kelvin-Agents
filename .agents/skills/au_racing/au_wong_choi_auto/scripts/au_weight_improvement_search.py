#!/usr/bin/env python3
"""Walk-forward weight search over the 7 LIVE matrix dimensions.

Tests whether re-weighting the already-extracted matrix scores (notably the
currently zero-weighted `form_line` dimension) improves OUT-OF-SAMPLE Top-3
accuracy vs the current live MATRIX_WEIGHTS. No engine re-run: it re-ranks the
matrix_scores already stored in the archive Auto_Scoring.csv files.

Rigour:
  * Walk-forward by meeting date: optimise on all earlier races, evaluate on a
    later held-out fold. Out-of-sample only — no peeking.
  * Reports baseline (current weights) vs optimised, on the SAME held-out races.
  * Also prints a form_line sensitivity sweep for interpretability.
"""
from __future__ import annotations

import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))

from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    MATRIX_KEYS,
    choose_track_rows,
    detect_meeting_date,
    load_scoring_rows,
    load_historical_results,
    normalize_horse_name,
    parse_int,
)
from scoring import MATRIX_WEIGHTS as LIVE  # noqa: E402

KEYS = list(MATRIX_KEYS)  # stability, sectional, race_shape, jockey_trainer, class_weight, track, form_line


def af(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def meeting_track(md: Path) -> str:
    name = md.name
    if name[:10].count("-") == 2:
        name = name[11:]
    for s in (" Race 1-10", " Race 1-9", " Race 1-8", " Race 1-7", " Race 1-6"):
        name = name.replace(s, "")
    return name.strip()


def load_races() -> list[dict]:
    """Return list of races: {date, horses:[{mx:{...}, pos, num}]}."""
    historical = load_historical_results(HISTORICAL_RESULTS_CSV)
    races = []
    for md in sorted(p for p in ARCHIVE_ROOT.iterdir() if p.is_dir()):
        mdate = detect_meeting_date(md)
        mtrack = meeting_track(md)
        if not mdate or not mtrack:
            continue
        for sp in sorted(md.glob("Race_*_Auto_Scoring.csv")):
            rno = parse_int(sp.stem)
            if not rno:
                continue
            result_rows = choose_track_rows(historical.get((mdate, rno), []), mtrack)
            if not result_rows:
                continue
            lookup = {r["horse_slug"]: r for r in result_rows}
            horses = []
            for sr in load_scoring_rows(sp):
                rr = lookup.get(normalize_horse_name(sr.get("horse_name", "")))
                if not rr:
                    continue
                mx = sr.get("matrix_scores") or {}
                horses.append({
                    "mx": {k: af(mx.get(k), 60.0) for k in KEYS},
                    "pos": int(rr["pos"]),
                    "num": parse_int(sr.get("horse_number")) or 0,
                })
            if len(horses) < 4 or sum(1 for h in horses if h["pos"] <= 3) < 3:
                continue
            races.append({"date": mdate, "horses": horses})
    races.sort(key=lambda r: r["date"])
    return races


def score(race: dict, w: dict) -> list[dict]:
    ranked = sorted(race["horses"], key=lambda h: (-sum(h["mx"][k] * w[k] for k in KEYS), h["num"]))
    return ranked


def metrics(races: list[dict], w: dict) -> dict:
    b = Counter()
    for race in races:
        ranked = score(race, w)
        top3 = ranked[:3]
        hits = sum(1 for h in top3 if h["pos"] <= 3)
        b["n"] += 1
        b["top3_hits"] += hits
        b["gold"] += 1 if hits == 3 else 0
        b["good"] += 1 if hits >= 2 else 0
        b["pass"] += 1 if hits >= 1 else 0
        b["miss"] += 1 if hits == 0 else 0
        b["win_t3"] += 1 if any(h["pos"] == 1 for h in top3) else 0
        b["top2_both"] += 1 if all(h["pos"] <= 3 for h in ranked[:2]) else 0
    n = max(1, b["n"])
    return {
        "n": b["n"], "gold": b["gold"], "good": b["good"], "pass": b["pass"], "miss": b["miss"],
        "good_rate": b["good"] / n, "top3": b["top3_hits"] / (3 * n), "win_t3": b["win_t3"] / n,
        "top2_both": b["top2_both"] / n,
    }


# OBJECTIVE: set by --target ("good" or "top2"); top2 optimises #1&#2 both placing.
OBJ_TARGET = "good"


def objective(m: dict) -> float:
    if OBJ_TARGET == "top2":
        # primary = top-2-both, tie-break on top3 precision then winner capture
        return m["top2_both"] * 1000 + m["top3"] * 10 + m["win_t3"]
    return m["good_rate"] * 1000 + m["top3"] * 10 + m["win_t3"]


def normalize(w: dict) -> dict:
    s = sum(max(0.0, w[k]) for k in KEYS) or 1.0
    return {k: max(0.0, w[k]) / s for k in KEYS}


def search_weights(train: list[dict], seed: int, iters: int = 1500) -> dict:
    """Random + local search on the simplex; seed-anchored on live weights."""
    rng = random.Random(seed)
    best = normalize(dict(LIVE))
    best_obj = objective(metrics(train, best))
    # try a form_line-enabled start too
    for start in (best, normalize({**LIVE, "form_line": 0.08, "stability": LIVE["stability"] - 0.08})):
        cur = dict(start)
        cur_obj = objective(metrics(train, cur))
        if cur_obj > best_obj:
            best, best_obj = dict(cur), cur_obj
    cur, cur_obj = dict(best), best_obj
    for i in range(iters):
        cand = dict(cur)
        # perturb 1-3 dims
        for _ in range(rng.randint(1, 3)):
            k = rng.choice(KEYS)
            cand[k] = max(0.0, cand[k] + rng.uniform(-0.06, 0.06))
        cand = normalize(cand)
        o = objective(metrics(train, cand))
        if o > cur_obj:
            cur, cur_obj = cand, o
            if o > best_obj:
                best, best_obj = dict(cand), o
        elif rng.random() < 0.10:  # occasional jump to escape local optima
            cur, cur_obj = cand, o
    return best


def walk_forward(races: list[dict], folds: int = 5, min_train: float = 0.5, seed: int = 7) -> None:
    dates = sorted({r["date"] for r in races})
    start = max(1, int(len(dates) * min_train))
    valid_dates = dates[start:]
    fsize = max(1, math.ceil(len(valid_dates) / folds))
    base_oos, opt_oos = [], []
    chosen = []
    for i in range(0, len(valid_dates), fsize):
        fold = set(valid_dates[i:i + fsize])
        first = min(fold)
        train = [r for r in races if r["date"] < first]
        test = [r for r in races if r["date"] in fold]
        if not train or not test:
            continue
        w = search_weights(train, seed + i)
        chosen.append(w)
        base_oos.extend(test)
        opt_oos.append((test, w))

    base_m = metrics(base_oos, normalize(dict(LIVE)))
    # apply each fold's own optimised weights to that fold's test set
    ob = Counter()
    for test, w in opt_oos:
        m = metrics(test, w)
        for k in ("gold", "good", "pass", "miss"):
            ob[k] += m[k]
        ob["n"] += m["n"]
        ob["top3_num"] += m["top3"] * 3 * m["n"]
        ob["win_num"] += m["win_t3"] * m["n"]
        ob["top2_num"] += m["top2_both"] * m["n"]
    n = max(1, ob["n"])
    opt_m = {"n": ob["n"], "gold": ob["gold"], "good": ob["good"], "pass": ob["pass"], "miss": ob["miss"],
             "good_rate": ob["good"] / n, "top3": ob["top3_num"] / (3 * n), "win_t3": ob["win_num"] / n,
             "top2_both": ob["top2_num"] / n}

    print("\n" + "=" * 78)
    print(f"WALK-FORWARD OUT-OF-SAMPLE  ({base_m['n']} held-out races)  —  optimising '{OBJ_TARGET}'")
    print("=" * 78)
    hdr = f"{'model':<26}{'Top2both%':>10}{'Good%':>8}{'Top3%':>8}{'Win-T3%':>9}{'Gold':>6}{'Miss':>6}"
    print(hdr)
    print("-" * len(hdr))
    print(f"{'baseline (live weights)':<26}{base_m['top2_both']*100:>9.2f}{base_m['good_rate']*100:>8.2f}"
          f"{base_m['top3']*100:>8.2f}{base_m['win_t3']*100:>8.2f}{base_m['gold']:>6}{base_m['miss']:>6}")
    print(f"{'optimised (walk-fwd)':<26}{opt_m['top2_both']*100:>9.2f}{opt_m['good_rate']*100:>8.2f}"
          f"{opt_m['top3']*100:>8.2f}{opt_m['win_t3']*100:>8.2f}{opt_m['gold']:>6}{opt_m['miss']:>6}")
    d_t2 = (opt_m['top2_both'] - base_m['top2_both']) * 100
    d_good = (opt_m['good_rate'] - base_m['good_rate']) * 100
    d_top3 = (opt_m['top3'] - base_m['top3']) * 100
    print(f"{'Δ':<26}{d_t2:>+9.2f}{d_good:>+8.2f}{d_top3:>+8.2f}")
    print("\nMean optimised weights across folds:")
    avg = {k: sum(w[k] for w in chosen) / len(chosen) for k in KEYS}
    for k in KEYS:
        print(f"  {k:<16} live={LIVE[k]:.3f}  opt={avg[k]:.3f}")


def formline_sensitivity(races: list[dict]) -> None:
    print("\n" + "=" * 70)
    print("FORM_LINE SENSITIVITY (whole archive, in-sample — direction only)")
    print("=" * 70)
    print(f"{'form_line w':>12}{'Good%':>9}{'Top3%':>9}{'Win-T3%':>10}")
    for fw in (0.0, 0.03, 0.05, 0.08, 0.12, 0.18):
        w = normalize({**LIVE, "form_line": fw, "stability": max(0.0, LIVE["stability"] - fw)})
        m = metrics(races, w)
        print(f"{fw:>12.2f}{m['good_rate']*100:>9.2f}{m['top3']*100:>9.2f}{m['win_t3']*100:>10.2f}")


def main() -> int:
    import argparse
    global OBJ_TARGET
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["good", "top2"], default="good")
    args = ap.parse_args()
    OBJ_TARGET = args.target
    print("Loading archive races (re-ranking matrix_scores, no engine re-run)...", flush=True)
    races = load_races()
    print(f"Loaded {len(races)} labelled races.  Objective = {OBJ_TARGET}", flush=True)
    if len(races) < 40:
        print("Not enough races.")
        return 1
    base = metrics(races, normalize(dict(LIVE)))
    print(f"\nWhole-archive baseline (live weights): Top2both {base['top2_both']*100:.2f}% | "
          f"Good {base['good_rate']*100:.2f}% | Top3 {base['top3']*100:.2f}% | Gold {base['gold']} | Miss {base['miss']}")
    walk_forward(races)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
