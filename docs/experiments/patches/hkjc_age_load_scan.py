#!/usr/bin/env python3
"""EXP-20261110-07 — HKJC horse age and racing-load scan (pre-registered, frozen).

Patterns:
  A1 age >= 8 (-)          A2 age <= 4 (+)          (age from meeting racecards, M only)
  F1 >= 4 starts in the 60 days before today (-)
  F2 3rd or 4th start of a preparation (+); a prep starts after a >= 60-day gap

Same machinery as EXP-20261027-12: day-level history update, stratified gap,
day-cluster bootstrap, Holm.

    python3 hkjc_age_load_scan.py --model-run model.jsonl --out result.json
"""
from __future__ import annotations

import argparse
import glob
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

ROOT = Path("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing")
PERIODS = {"D": ("2024-09-08", "2025-07-31"), "V": ("2025-09-01", "2026-04-11"), "M": ("2026-04-12", "2026-11-08")}
PATTERNS = {"A1": -1, "A2": +1, "F1": -1, "F2": +1}
SEED = 20261111


def load_ages():
    """(date, brand) -> age, from every meeting folder's racecards."""
    ages = {}
    for folder in ROOT.iterdir():
        m = re.match(r"(\d{4}-\d\d-\d\d)_(ShaTin|HappyValley)$", folder.name)
        if not m:
            continue
        for card in folder.glob("* Race * 排位表.md"):
            text = card.read_text(encoding="utf-8")
            for block in re.split(r"\n(?=馬號: )", text):
                brand = re.search(r"烙號: ([A-Z]\d{3})", block)
                age = re.search(r"馬齡: (\d+)", block)
                if brand and age:
                    ages[(m.group(1), brand.group(1))] = int(age.group(1))
    return ages


def scan(model_ranks, ages):
    days = load_days()
    horse_runs = defaultdict(list)
    rows, leaks = [], 0
    for day, races in days.items():
        today = date.fromisoformat(day)
        day_updates = []
        for race in races:
            race_key = (day, VENUE.get(race.get("venue"), race.get("venue")), int(race.get("race_no") or 0))
            ranks = model_ranks.get(race_key, {})
            for entry in race.get("results", []):
                pos = _int(entry.get("pos"))
                ident = re.search(r"\(([A-Z]\d{3})\)", str(entry.get("horse_name") or ""))
                if pos is None or not ident:
                    continue
                horse = ident.group(1)
                history = [h for h in horse_runs[horse] if h < today]
                leaks += len(horse_runs[horse]) - len(history)
                starts_60 = sum(1 for h in history if h >= today - timedelta(days=60))
                # Prep number: count starts since the last >= 60-day gap (today included).
                prep = None
                seq = history + [today]
                for i in range(len(seq) - 1, 0, -1):
                    if (seq[i] - seq[i - 1]).days >= 60:
                        prep = len(seq) - i
                        break
                age = ages.get((day, horse))
                rows.append({
                    "date": day, "placed": pos <= 3, "has_age": age is not None,
                    "odds_band": odds_band(_float(entry.get("win_odds"))),
                    "model_band": model_band(ranks.get(_int(entry.get("horse_no")))),
                    "A1": age is not None and age >= 8,
                    "A2": age is not None and age <= 4,
                    "F1": starts_60 >= 4,
                    "F2": prep in (3, 4),
                })
                day_updates.append(horse)
        for horse in day_updates:
            horse_runs[horse].append(today)
    return rows, leaks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-run", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    rng = random.Random(SEED)
    rows, leaks = scan(load_model_ranks(args.model_run), load_ages())
    period = {k: [r for r in rows if lo <= r["date"] <= hi] for k, (lo, hi) in PERIODS.items()}
    m_rows = [r for r in period["M"] if r["model_band"]]
    m_age = [r for r in m_rows if r["has_age"]]
    report = {"leak_rows": leaks, "runs": {k: len(v) for k, v in period.items()},
              "model_matched_M": len(m_rows), "age_matched_M": len(m_age),
              "age_match_rate": round(len(m_age) / len(m_rows), 4) if m_rows else None, "patterns": {}}
    pvalues = {}
    for p, sign in PATTERNS.items():
        entry = {"direction": "+" if sign > 0 else "−"}
        if p.startswith("F"):
            for lens, key in (("L1_D", "D"), ("L1_V", "V")):
                res = evaluate(period[key], p, "odds_band", rng)
                res.pop("draws")
                entry[lens] = res
        m = evaluate(m_age if p.startswith("A") else m_rows, p, "model_band", rng)
        draws = m.pop("draws")
        pvalues[p] = (sum(1 for x in draws if sign * x <= 0) + 1) / (len(draws) + 1) if draws else 1.0
        entry["L2_M"] = m
        entry["p_one_sided"] = round(pvalues[p], 4)
        report["patterns"][p] = entry
    adjusted = holm(pvalues)
    for p in PATTERNS:
        entry = report["patterns"][p]
        entry["p_holm"] = round(adjusted[p], 4)
        entry["overlay_candidate"] = adjusted[p] < 0.05 and entry["L2_M"]["n_pattern"] >= 80
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
