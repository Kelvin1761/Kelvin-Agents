#!/usr/bin/env python3
"""EXP-20261110-06 — HKJC weak last-start jockey scan (pre-registered, frozen).

Hypothesis: when a horse's last start was ridden by a weak jockey, that run
understates its ability, so with a different jockey today it places more
often than the model rank implies.

Reuses the frozen machinery of EXP-20261027-12 (`hkjc_situational_overlay_scan`):
same results database, same day-level history update (nothing from the same
day or later reaches a feature), same stratified gap, day-cluster bootstrap
and Holm.

    python3 hkjc_weak_last_jockey_scan.py --model-run model.jsonl --out result.json
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hkjc_situational_overlay_scan import (  # noqa: E402
    VENUE, _float, _int, evaluate, holm, load_model_ranks, model_band, odds_band,
)
from hkjc_results_dedup import load_days  # noqa: E402  (2026-05+ races are stored twice)

PERIODS = {"D": ("2024-09-08", "2025-07-31"), "V": ("2025-09-01", "2026-04-11"), "M": ("2026-04-12", "2026-11-08")}
PATTERNS = ("J1", "J2", "J3")
MIN_RIDES = 100
SEED = 20261110


def scan(model_ranks):
    days = load_days()
    jockey_runs, horse_runs = [], defaultdict(list)
    rows, leaks = [], 0
    for day, races in days.items():
        today = date.fromisoformat(day)
        d365 = today - timedelta(days=365)
        wins, places, rides = defaultdict(int), defaultdict(int), defaultdict(int)
        for when, jockey, won, placed in jockey_runs:
            if when >= d365:
                wins[jockey] += won
                places[jockey] += placed
                rides[jockey] += 1
        top = {j for j, _w in sorted(wins.items(), key=lambda kv: -kv[1])[:6]}
        rated = sorted((places[j] / rides[j], j) for j in rides if rides[j] >= MIN_RIDES)
        weak = {j for _r, j in rated[: len(rated) // 3]}
        day_updates = []
        for race in races:
            race_key = (day, VENUE.get(race.get("venue"), race.get("venue")), int(race.get("race_no") or 0))
            ranks = model_ranks.get(race_key, {})
            for entry in race.get("results", []):
                pos = _int(entry.get("pos"))
                ident = re.search(r"\(([A-Z]\d{3})\)", str(entry.get("horse_name") or ""))
                if pos is None or not ident:
                    continue
                horse, jockey = ident.group(1), entry.get("jockey")
                history = [h for h in horse_runs[horse] if h["date"] < today]
                leaks += len(horse_runs[horse]) - len(history)
                last = history[-1] if history else None
                j1 = bool(last) and last["jockey"] in weak and jockey != last["jockey"]
                rows.append({
                    "date": day, "race": race_key, "placed": pos <= 3,
                    "odds_band": odds_band(_float(entry.get("win_odds"))),
                    "model_band": model_band(ranks.get(_int(entry.get("horse_no")))),
                    "J1": j1,
                    "J2": j1 and jockey not in top,
                    "J3": j1 and last["pos"] >= 6,
                    "last_jockey": last["jockey"] if last else None,
                })
                day_updates.append((horse, jockey, pos))
        for horse, jockey, pos in day_updates:
            jockey_runs.append((today, jockey, int(pos == 1), int(pos <= 3)))
            horse_runs[horse].append({"date": today, "pos": pos, "jockey": jockey})
    return rows, leaks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-run", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    rng = random.Random(SEED)
    rows, leaks = scan(load_model_ranks(args.model_run))
    period = {k: [r for r in rows if lo <= r["date"] <= hi] for k, (lo, hi) in PERIODS.items()}
    m_rows = [r for r in period["M"] if r["model_band"]]
    report = {"leak_rows": leaks, "runs": {k: len(v) for k, v in period.items()},
              "model_matched_M": len(m_rows), "patterns": {}}
    pvalues = {}
    for p in PATTERNS:
        d = evaluate(period["D"], p, "odds_band", rng)
        v = evaluate(period["V"], p, "odds_band", rng)
        m = evaluate(m_rows, p, "model_band", rng)
        draws = m.pop("draws")
        pvalues[p] = (sum(1 for x in draws if x <= 0) + 1) / (len(draws) + 1) if draws else 1.0
        d.pop("draws"), v.pop("draws")
        report["patterns"][p] = {"direction": "+", "L1_D": d, "L1_V": v, "L2_M": m, "p_one_sided": round(pvalues[p], 4)}
    adjusted = holm(pvalues)
    for p in PATTERNS:
        entry = report["patterns"][p]
        entry["p_holm"] = round(adjusted[p], 4)
        entry["overlay_candidate"] = adjusted[p] < 0.05 and entry["L2_M"]["n_pattern"] >= 80
    # Descriptive only (not a verdict): which last-start jockeys make up J1 in M.
    mix = defaultdict(int)
    for r in m_rows:
        if r["J1"]:
            mix[r["last_jockey"]] += 1
    report["M_J1_last_jockey_mix"] = dict(sorted(mix.items(), key=lambda kv: -kv[1]))
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
