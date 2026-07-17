#!/usr/bin/env python3
"""Ordering-features Phase 1: retrodictive signal check (no engine code).

Within each race's model top-4, does each candidate feature separate actual
placegetters from non-placegetters — and does the separation hold on the
later half of dates (OOS) as well as the earlier half (train)?

F1 H2H net score: 賽績線 encounters vs today's top-4 rivals (win=+1/loss=-1,
   recency-decayed, margin-weighted).
F2 last-start quality: latest encounter (win → +, beaten margin → −, decayed).
F3 sectional differential: timing_600m_recent_speed minus top-4 median.
F4 franking rate: fraction of encounters whose rival won subsequently.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean, median

SCRIPTS = Path("/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))

from au_cached_walkforward_ml import as_float, group_races, materialize_dataset  # noqa: E402

RAW = json.load(open("/Users/imac/Antigravity-repo/scratch/au_ordering_features_raw.json"))
SANDBOX = Path("/private/tmp/claude-501/-Users-imac-Antigravity-repo/b09ea7dc-ca6d-496d-af27-41b7787ee6ae/scratchpad/data/Wong Choi Horse Race Analysis/AU_Racing")
SLOT_POS = {"頭馬": 1, "亞軍": 2, "季軍": 3}


def load_timing() -> dict:
    timing = {}
    for d in sorted(p for p in SANDBOX.iterdir() if p.is_dir()):
        for lp in d.glob("Race_*_Logic.json"):
            try:
                data = json.loads(lp.read_text(encoding="utf-8"))
            except Exception:
                continue
            race_no = str((data.get("race_analysis") or {}).get("race_number") or lp.stem.split("_")[1])
            for num, h in (data.get("horses") or {}).items():
                hd = h.get("_data") or {}
                value = hd.get("timing_600m_recent_speed")
                try:
                    timing[f"{d.name}|{race_no}|{num}"] = float(str(value).split()[0])
                except (TypeError, ValueError):
                    pass
    return timing


def days_ago(meeting_date: str, event_date: str | None) -> float:
    try:
        m = date.fromisoformat(meeting_date)
        e = date.fromisoformat(event_date)
        return max(1.0, (m - e).days)
    except (TypeError, ValueError):
        return 365.0


def decay(days: float) -> float:
    return 1.0 / (1.0 + days / 180.0)


def h2h_and_quality(key: str, meeting_date: str, rival_names: dict[str, str]) -> tuple[float, float, float]:
    info = RAW.get(key) or {}
    encounters = info.get("encounters") or []
    net = 0.0
    frank_hits = frank_total = 0
    last_quality = None
    for e in encounters:
        my_pos = e.get("my_pos")
        if my_pos is None:
            continue
        weight = decay(days_ago(meeting_date, e.get("date")))
        # F2: first (most recent) encounter row defines last-start quality
        if last_quality is None:
            margin = e.get("my_margin")
            if my_pos == 1:
                last_quality = 3.0 * weight
            elif margin is not None:
                last_quality = max(-6.0, margin) * weight  # margin is negative
            else:
                last_quality = -float(min(my_pos, 8)) / 2.0 * weight
        franking = str(e.get("franking") or "")
        if "勝" in franking or "出" in franking:
            frank_total += 1
            if re.search(r"[1-9]\s*勝", franking):
                frank_hits += 1
        rival = e.get("rival")
        if rival not in rival_names:
            continue
        rival_pos = SLOT_POS.get(str(e.get("rival_slot") or ""), None)
        if rival_pos is None:
            continue
        margin_mag = min(3.0, abs(e.get("my_margin") or 1.0))
        sign = 1.0 if my_pos < rival_pos else (-1.0 if my_pos > rival_pos else 0.0)
        net += sign * weight * (0.5 + margin_mag / 3.0)
    f4 = (frank_hits / frank_total) if frank_total else 0.0
    return net, (last_quality or 0.0), f4


def main() -> int:
    timing = load_timing()
    races = group_races(materialize_dataset())
    dates = sorted({str(r[0]["date"]) for r in races})
    split = dates[len(dates) // 2]

    deltas = {half: defaultdict(list) for half in ("train", "valid")}
    pair_wins = {half: defaultdict(lambda: [0, 0]) for half in ("train", "valid")}

    for race in races:
        meeting_date = str(race[0]["date"])
        half = "train" if meeting_date < split else "valid"
        ranked = sorted(race, key=lambda r: (-as_float(r["ability_score"], 60.0), int(r["horse_number"])))
        top4 = ranked[:4]
        keys = {id(r): f"{r['meeting']}|{r['race']}|{int(r['horse_number'])}" for r in top4}
        names = {}
        for r in top4:
            info = RAW.get(keys[id(r)]) or {}
            if info.get("name"):
                names[info["name"]] = r
        feats = {}
        speeds = [timing.get(keys[id(r)]) for r in top4]
        valid_speeds = [s for s in speeds if s is not None]
        med_speed = median(valid_speeds) if valid_speeds else None
        for r, s in zip(top4, speeds):
            f1, f2, f4 = h2h_and_quality(keys[id(r)], meeting_date, names)
            f3 = (s - med_speed) if (s is not None and med_speed is not None) else 0.0
            feats[id(r)] = {"F1_h2h": f1, "F2_last": f2, "F3_sect": f3, "F4_frank": f4}
        hit = [r for r in top4 if int(r["actual_pos"]) <= 3]
        non = [r for r in top4 if int(r["actual_pos"]) > 3]
        if not hit or not non:
            continue
        for fname in ("F1_h2h", "F2_last", "F3_sect", "F4_frank"):
            deltas[half][fname].append(
                mean(feats[id(r)][fname] for r in hit) - mean(feats[id(r)][fname] for r in non))
        # pairwise direction accuracy: for pairs with nonzero F1 evidence
        for a in hit:
            for b in non:
                d = feats[id(a)]["F1_h2h"] - feats[id(b)]["F1_h2h"]
                if abs(d) > 1e-9:
                    stats = pair_wins[half]["F1_h2h"]
                    stats[0] += d > 0
                    stats[1] += 1

    for fname in ("F1_h2h", "F2_last", "F3_sect", "F4_frank"):
        t, v = deltas["train"][fname], deltas["valid"][fname]
        print(f"{fname:<9} placegetter-minus-non delta | train {mean(t):+.4f} (n={len(t)}) | valid {mean(v):+.4f} (n={len(v)}) "
              f"| sign holds: {'YES' if mean(t) * mean(v) > 0 else 'no'}")
    for half in ("train", "valid"):
        w, n = pair_wins[half]["F1_h2h"]
        if n:
            print(f"F1 pairwise direction accuracy ({half}): {w}/{n} = {100*w/n:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
