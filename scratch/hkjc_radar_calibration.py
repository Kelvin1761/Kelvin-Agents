#!/usr/bin/env python3
"""Calibrate an HKJC confidence-tiered betting radar on HKJC's own gap distribution.

For each archived race, bucket by the top1-top3 ability_score gap, then measure
what each radar width actually catches: winner-in-top-N and >=2-placegetters-in-top-N.
This tells us honestly how wide the radar must open per tier for HKJC (the AU tiers
were calibrated on AU's 710-race archive; HKJC's tight cohort is 40% of races).
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wongchoi_paths import HK_RACING  # noqa: E402


def find_results(meeting: Path):
    f = sorted(meeting.glob("*全日賽果.json"))
    return f[0] if f else None


def load_results(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for k, race in data.items():
        try:
            rn = int(k)
        except (TypeError, ValueError):
            continue
        pos = {}
        for row in race.get("results", []):
            try:
                pos[int(row["horse_no"])] = int(row["pos"])
            except (KeyError, TypeError, ValueError):
                continue
        if pos:
            out[rn] = pos
    return out


def main():
    tiers = defaultdict(list)  # tier -> list of (ranked_horses, pos_map, top3)
    for meeting in sorted(HK_RACING.iterdir()):
        if not meeting.is_dir() or "(" in meeting.name or not meeting.name.startswith("2026"):
            continue
        rp = find_results(meeting)
        if rp is None or not list(meeting.glob("Race_*_Logic.json")):
            continue
        actual = load_results(rp)
        for lp in sorted(meeting.glob("Race_*_Logic.json")):
            m = re.search(r"Race_(\d+)_Logic\.json$", lp.name)
            rn = int(m.group(1)) if m else 0
            if rn not in actual:
                continue
            logic = json.loads(lp.read_text(encoding="utf-8"))
            scored = []
            for hn_t, horse in logic.get("horses", {}).items():
                try:
                    hn = int(hn_t)
                except ValueError:
                    continue
                auto = horse.get("python_auto", {})
                if not auto.get("feature_scores"):
                    continue
                scored.append((hn, float(auto.get("ability_score", 60.0))))
            if len(scored) < 5:
                continue
            pos = actual[rn]
            top3 = [h for h, p in pos.items() if p <= 3]
            if sum(1 for p in pos.values() if p <= 3) < 3 or not top3:
                continue
            ranked = [h for h, _ in sorted(scored, key=lambda kv: (-kv[1], kv[0]))]
            gaps = sorted((s for _, s in scored), reverse=True)
            gap = gaps[0] - gaps[2]
            tier = "tight (<2)" if gap < 2.0 else ("medium (2-5)" if gap < 5.0 else "clear (>=5)")
            tiers[tier].append((ranked, pos, set(top3)))

    print(f"{'tier':14} {'n':>4} {'win@2':>6} {'win@3':>6} {'win@4':>6} {'win@5':>6} "
          f"{'2pl@2':>6} {'2pl@4':>6} {'2pl@5':>6} {'2pl@6':>6}")
    for tier in ("tight (<2)", "medium (2-5)", "clear (>=5)"):
        races = tiers[tier]
        n = len(races)
        if not n:
            continue
        def win_at(k):
            return sum(1 for r, pos, t3 in races if any(pos.get(h) == 1 for h in r[:k])) / n
        def two_at(k):
            return sum(1 for r, pos, t3 in races if sum(1 for h in r[:k] if h in t3) >= 2) / n
        print(f"{tier:14} {n:>4} {win_at(2):>6.1%} {win_at(3):>6.1%} {win_at(4):>6.1%} {win_at(5):>6.1%} "
              f"{two_at(2):>6.1%} {two_at(4):>6.1%} {two_at(5):>6.1%} {two_at(6):>6.1%}")


if __name__ == "__main__":
    main()
