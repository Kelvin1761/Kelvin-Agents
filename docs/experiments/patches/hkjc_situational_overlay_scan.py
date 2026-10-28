#!/usr/bin/env python3
"""EXP-20261027-12 — HKJC situational overlay scan (pre-registered, frozen).

Builds ten point-in-time patterns from `HKJC_Race_Results_Database` and
measures each one's top-3 excess:

  L1 market lens (D, V)  stratified by final win-odds band
  L2 model lens  (M)     stratified by current-model rank band
                         (ranks from an `hkjc_eval_harness run` file)

History is updated only after a whole race day is processed, so nothing
from the same day or later can reach a feature.

    python3 hkjc_situational_overlay_scan.py --model-run model.jsonl --out result.json
"""
from __future__ import annotations

import argparse
import glob
import json
import random
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

DB = Path("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing/HKJC_Race_Results_Database")
PERIODS = {"D": ("2024-09-08", "2025-07-31"), "V": ("2025-09-01", "2026-04-11"), "M": ("2026-04-12", "2026-10-25")}
PATTERNS = ("P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10")
VENUE = {"沙田": "ShaTin", "跑馬地": "HappyValley"}
BOOT = 2000


def _int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _float(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def load_days():
    days = defaultdict(list)
    for path in glob.glob(str(DB / "hkjc results */*/*.json")):
        for race in json.loads(Path(path).read_text(encoding="utf-8")).values():
            if not isinstance(race, dict) or not race.get("racedate"):
                continue
            days[race["racedate"]].append(race)
    return dict(sorted(days.items()))


def odds_band(odds):
    if odds is None:
        return None
    for upper, label in ((3.0, "≤3"), (6.0, "3–6"), (12.0, "6–12"), (25.0, "12–25")):
        if odds <= upper:
            return label
    return ">25"


def model_band(rank):
    return None if rank is None else "1–3" if rank <= 3 else "4–6" if rank <= 6 else "7+"


def scan(model_ranks):
    days = load_days()
    jockey_runs, trainer_runs, combo_runs, horse_runs = [], [], defaultdict(list), defaultdict(list)
    rows, leaks = [], 0
    for day, races in days.items():
        today = date.fromisoformat(day)
        d365, d30 = today - timedelta(days=365), today - timedelta(days=30)
        recent_j = [r for r in jockey_runs if r[0] >= d365]
        wins = defaultdict(int)
        jplace, jn = defaultdict(int), defaultdict(int)
        for when, jockey, won, placed in recent_j:
            wins[jockey] += won
            jplace[jockey] += placed
            jn[jockey] += 1
        top_jockeys = {j for j, _w in sorted(wins.items(), key=lambda kv: -kv[1])[:6]}
        t365, t30 = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
        for when, trainer, placed in trainer_runs:
            if when >= d365:
                t365[trainer][0] += placed
                t365[trainer][1] += 1
            if when >= d30:
                t30[trainer][0] += placed
                t30[trainer][1] += 1
        day_updates = []
        for race in races:
            race_key = (day, VENUE.get(race.get("venue"), race.get("venue")), int(race.get("race_no") or 0))
            ranks = model_ranks.get(race_key, {})
            for entry in race.get("results", []):
                pos = _int(entry.get("pos"))
                ident = re.search(r"\(([A-Z]\d{3})\)", str(entry.get("horse_name") or ""))
                if pos is None or not ident:
                    continue
                horse, jockey, trainer = ident.group(1), entry.get("jockey"), entry.get("trainer")
                body = _int(entry.get("horse_wt") or entry.get("declared_weight"))
                carried = _int(entry.get("actual_wt") or entry.get("actual_weight"))
                history = [h for h in horse_runs[horse] if h["date"] < today]
                leaks += len(horse_runs[horse]) - len(history)
                last = history[-1] if history else None
                prev2 = history[-2:]
                pair = [p for p in combo_runs[(jockey, trainer)] if p[0] >= d365]
                pair_n, pair_place = len(pair), sum(p[1] for p in pair)
                j_rate = jplace[jockey] / jn[jockey] if jn[jockey] else None
                strong_combo = False
                if pair_n >= 15 and j_rate is not None:
                    shrunk = (pair_place + 20 * j_rate) / (pair_n + 20)
                    strong_combo = shrunk - j_rate >= 0.08
                poor_form = len(prev2) == 2 and all(h["pos"] >= 6 for h in prev2)
                gap = (today - last["date"]).days if last else None
                flags = {
                    "P1": bool(last) and jockey in top_jockeys and last["jockey"] not in top_jockeys,
                    "P2": bool(last) and last["jockey"] in top_jockeys and jockey not in top_jockeys,
                    "P3": strong_combo,
                    "P5": gap is not None and gap <= 14,
                    "P6": gap is not None and gap >= 60 and jockey in top_jockeys,
                    "P7": bool(last) and body is not None and last["body"] is not None and abs(body - last["body"]) >= 15,
                    "P8": bool(last) and carried is not None and last["carried"] is not None and last["carried"] - carried >= 6,
                }
                flags["P4"] = poor_form and flags["P1"]
                flags["P10"] = poor_form and strong_combo
                n30, n365 = t30[trainer], t365[trainer]
                flags["P9"] = (n30[1] >= 20 and n365[1] > 0
                               and n30[0] / n30[1] - n365[0] / n365[1] >= 0.10)
                rows.append({
                    "date": day, "race": race_key, "placed": pos <= 3,
                    "odds_band": odds_band(_float(entry.get("win_odds"))),
                    "model_band": model_band(ranks.get(_int(entry.get("horse_no")))),
                    **flags,
                })
                day_updates.append((horse, jockey, trainer, pos, body, carried))
        for horse, jockey, trainer, pos, body, carried in day_updates:
            jockey_runs.append((today, jockey, int(pos == 1), int(pos <= 3)))
            trainer_runs.append((today, trainer, int(pos <= 3)))
            combo_runs[(jockey, trainer)].append((today, int(pos <= 3)))
            horse_runs[horse].append({"date": today, "pos": pos, "jockey": jockey, "body": body, "carried": carried})
    return rows, leaks


def stratified_gap(rows, pattern, band_key):
    cells = defaultdict(lambda: [0, 0, 0, 0])
    for row in rows:
        band = row[band_key]
        if band is None:
            continue
        cell = cells[band]
        if row[pattern]:
            cell[0] += row["placed"]
            cell[1] += 1
        else:
            cell[2] += row["placed"]
            cell[3] += 1
    num = den = 0.0
    for y1, n1, y0, n0 in cells.values():
        if n1 and n0:
            weight = n1 * n0 / (n1 + n0)
            num += weight * (y1 / n1 - y0 / n0)
            den += weight
    return num / den if den else None


def evaluate(rows, pattern, band_key, rng):
    by_day = defaultdict(list)
    for row in rows:
        by_day[row["date"]].append(row)
    point = stratified_gap(rows, pattern, band_key)
    keys = list(by_day)
    draws = []
    for _ in range(BOOT):
        sample = [r for _k in keys for r in by_day[rng.choice(keys)]]
        value = stratified_gap(sample, pattern, band_key)
        if value is not None:
            draws.append(value)
    draws.sort()
    n = sum(1 for r in rows if r[pattern] and r[band_key] is not None)
    rate = (sum(r["placed"] for r in rows if r[pattern] and r[band_key] is not None) / n) if n else None
    return {"gap_pp": None if point is None else round(100 * point, 2),
            "ci_pp": [round(100 * draws[int(0.025 * len(draws))], 2), round(100 * draws[int(0.975 * len(draws)) - 1], 2)] if draws else None,
            "draws": draws, "n_pattern": n, "pattern_place_rate": None if rate is None else round(100 * rate, 1),
            "days": len(keys)}


def holm(pvalues):
    order = sorted(pvalues, key=pvalues.get)
    adjusted, running = {}, 0.0
    for i, key in enumerate(order):
        running = max(running, min(1.0, (len(order) - i) * pvalues[key]))
        adjusted[key] = running
    return adjusted


def load_model_ranks(path):
    ranks = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if "error" in row:
            continue
        day, venue = row["meeting"].split("_", 1)
        ranks[(day, venue, int(row["race"]))] = {h: i for i, h in enumerate(row["picks"], 1)}
    return ranks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-run", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    rng = random.Random(20261027)
    rows, leaks = scan(load_model_ranks(args.model_run))
    period = {k: [r for r in rows if lo <= r["date"] <= hi] for k, (lo, hi) in PERIODS.items()}
    report = {"leak_rows": leaks, "runs": {k: len(v) for k, v in period.items()},
              "model_matched_M": sum(1 for r in period["M"] if r["model_band"]), "patterns": {}}
    pvalues = {}
    for p in PATTERNS:
        d = evaluate(period["D"], p, "odds_band", rng)
        v = evaluate(period["V"], p, "odds_band", rng)
        m = evaluate([r for r in period["M"] if r["model_band"]], p, "model_band", rng)
        sign = 1 if (d["gap_pp"] or 0) >= 0 else -1
        draws = m.pop("draws")
        pvalues[p] = (sum(1 for x in draws if sign * x <= 0) + 1) / (len(draws) + 1) if draws else 1.0
        d.pop("draws"), v.pop("draws")
        report["patterns"][p] = {"direction_from_D": "+" if sign > 0 else "−", "L1_D": d, "L1_V": v, "L2_M": m,
                                 "p_one_sided": round(pvalues[p], 4)}
    adjusted = holm(pvalues)
    for p in PATTERNS:
        entry = report["patterns"][p]
        entry["p_holm"] = round(adjusted[p], 4)
        entry["overlay_candidate"] = adjusted[p] < 0.05 and entry["L2_M"]["n_pattern"] >= 80
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
