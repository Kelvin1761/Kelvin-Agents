#!/usr/bin/env python3
"""Development-only search + one-shot holdout check for post-spell returns.

The signal is reconstructed only from dated pre-race Facts rows:
current run <= N days after the latest official run, while that latest run came
after a >= M day gap and did not place.  No market field is used.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))

import au_eval  # noqa: E402


def parse_date(value: object):
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def official_runs(facts: str) -> list[dict]:
    runs = []
    for raw_line in str(facts or "").splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cols = [part.strip() for part in line.strip("|").split("|")]
        if len(cols) < 8 or not cols[0].isdigit():
            continue
        run_date = parse_date(cols[2])
        if not run_date:
            continue
        if "試閘" in cols[1] or "trial" in cols[1].lower() or "trial" in cols[3].lower():
            continue
        placing = cols[7]
        match = re.match(r"(\d+)", placing)
        finish = int(match.group(1)) if match else None
        # A dash in these pre-fix Facts means the horse was outside the top 3;
        # it is not missing outcome evidence.  EXP-20260822-01 documented this.
        unplaced = finish is None or finish > 3
        runs.append({"date": run_date, "finish": finish, "unplaced": unplaced})
    return sorted(runs, key=lambda item: item["date"], reverse=True)


def annotate(races):
    parsed = 0
    for race in races:
        target = parse_date(race.get("date") or (race.get("metadata") or {}).get("date"))
        base_order = sorted(
            race["rows"], key=au_eval.default_scorer, reverse=True
        )
        for rank, row in enumerate(base_order, 1):
            row["base_rank"] = rank
        for row in race["rows"]:
            facts = (row.get("raw_pre_race") or {}).get("facts_section", "")
            runs = [run for run in official_runs(facts) if not target or run["date"] < target]
            row["post_spell"] = None
            if target and len(runs) >= 2:
                since = (target - runs[0]["date"]).days
                gap = (runs[0]["date"] - runs[1]["date"]).days
                row["post_spell"] = {
                    "days_since_return": since,
                    "prior_spell_days": gap,
                    "return_unplaced": bool(runs[0]["unplaced"]),
                    "return_finish": runs[0]["finish"],
                }
                parsed += 1
    return parsed


def risk(row, spell_min: int, since_max: int) -> bool:
    info = row.get("post_spell") or {}
    return bool(
        info.get("prior_spell_days", 0) >= spell_min
        and 0 < info.get("days_since_return", 9999) <= since_max
        and info.get("return_unplaced")
    )


def scorer(spell_min: int, since_max: int, penalty: float):
    def score(row):
        value = au_eval.default_scorer(row)
        return value - penalty if risk(row, spell_min, since_max) else value
    return score


def auc_for(pairs, indices):
    return au_eval._auc_indices(pairs, indices)


def time_folds(races, indices, count=5):
    dates = sorted({races[index].get("date") for index in indices})
    chunks = []
    for fold in range(count):
        lo = math.floor(len(dates) * fold / count)
        hi = math.floor(len(dates) * (fold + 1) / count)
        chosen = set(dates[lo:hi])
        chunks.append([index for index in indices if races[index].get("date") in chosen])
    return chunks


def cohort(races, indices, spell_min, since_max):
    rows = [row for index in indices for row in races[index]["rows"]]
    hit = [row for row in rows if risk(row, spell_min, since_max)]
    top3 = [row for row in hit if row.get("base_rank", 99) <= 3]
    top1 = [row for row in hit if row.get("base_rank") == 1]

    def line(label, values):
        placed = sum((row.get("pos") or 999) <= 3 for row in values)
        rate = 100 * placed / len(values) if values else float("nan")
        return f"{label}: n={len(values)}, placed={placed}, place_rate={rate:.2f}%"

    return [line("all", hit), line("baseline_top3", top3), line("baseline_top1", top1)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    args = parser.parse_args()

    races = au_eval.load_races(args.dataset)
    parsed = annotate(races)
    dev, holdout = au_eval.date_partitions(races)
    folds = time_folds(races, dev)
    base_pairs = au_eval._pairs(races, au_eval.default_scorer, True)
    base_dev = auc_for(base_pairs, dev)

    candidates = []
    for spell_min in (60, 90, 120, 180):
        for since_max in (21, 30, 45):
            for penalty in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
                candidate = scorer(spell_min, since_max, penalty)
                pairs = au_eval._pairs(races, candidate, True)
                delta = auc_for(pairs, dev) - base_dev
                fold_delta = [auc_for(pairs, fold) - auc_for(base_pairs, fold) for fold in folds]
                candidates.append((delta, sum(value >= 0 for value in fold_delta),
                                   spell_min, since_max, penalty, fold_delta))

    # Select without looking at holdout: require >=4/5 non-negative dev folds,
    # then maximize the development point estimate; prefer the simpler/lower
    # magnitude candidate on exact ties.
    eligible = [item for item in candidates if item[1] >= 4]
    chosen = max(eligible or candidates, key=lambda item: (item[0], item[1], -item[4]))
    delta, wins, spell_min, since_max, penalty, fold_delta = chosen

    print(f"races={len(races)} parsed_rows={parsed} dev={len(dev)} holdout={len(holdout)}")
    print(f"base_dev_top5_auc={base_dev:.6f}")
    print("top development candidates:")
    for item in sorted(candidates, reverse=True)[:12]:
        d, w, sm, sx, p, fd = item
        print(f"  spell>={sm:3d} since<={sx:2d} penalty={p:.1f} "
              f"dev_delta={d:+.6f} folds={w}/5 "
              f"[{', '.join(f'{value:+.5f}' for value in fd)}]")

    print("\nchosen_on_development:")
    print(f"  spell>={spell_min}, since<={since_max}, latest_return_unplaced, "
          f"penalty={penalty:.1f}; dev_delta={delta:+.6f}; folds={wins}/5")
    print("development cohort:")
    for value in cohort(races, dev, spell_min, since_max):
        print("  " + value)

    print("\none-shot holdout evaluation:")
    result = au_eval.compare(
        races,
        au_eval.default_scorer,
        scorer(spell_min, since_max, penalty),
        label="post_spell_unplaced_return",
    )
    print(result)
    print("holdout cohort (reported after candidate lock):")
    for value in cohort(races, holdout, spell_min, since_max):
        print("  " + value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
