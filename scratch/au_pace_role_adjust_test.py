#!/usr/bin/env python3
"""Round-5 candidate: pace-role adjustment in predicted-fast races.

Audit finding (post-adoption archive): in races whose speed_map predicts 快
pace, leaders actually hit the top-3 at 35.2% but are model-picked at only
22.6% (+12.6pp underrated, n=159 horses), while closers are picked at 26.5%
vs 18.7% actual (−7.8pp overrated, n=257). The engine's fast-pace-favours-
closers tilt is backwards in this sample.

Candidate: in 快-pace races only, ability' = ability + δL·(leader) − δC·(closer),
(δL, δC) selected per fold on train positional+any-2 Good. Standard gate.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path("/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/shared_racing")

from au_cached_walkforward_ml import (  # noqa: E402
    as_float,
    date_folds,
    group_races,
    materialize_dataset,
    metrics_for_races,
)

ROOT = Path("/private/tmp/claude-501/-Users-imac-Antigravity-repo/b09ea7dc-ca6d-496d-af27-41b7787ee6ae/scratchpad/data/Wong Choi Horse Race Analysis/AU_Racing")
DELTAS = (0.0, 0.5, 1.0, 1.5)


def load_roles() -> dict:
    roles = {}
    for d in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        for lp in d.glob("Race_*_Logic.json"):
            try:
                data = json.loads(lp.read_text(encoding="utf-8"))
            except Exception:
                continue
            ra = data.get("race_analysis") or {}
            sm = ra.get("speed_map") or {}
            race_no = str(ra.get("race_number") or lp.stem.split("_")[1])
            roles[f"{d.name}|{race_no}"] = {
                "fast": str(sm.get("predicted_pace") or "") == "快",
                "leaders": {int(x) for x in (sm.get("leaders") or []) if str(x).isdigit()},
                "closers": {int(x) for x in (sm.get("closers") or []) if str(x).isdigit()},
            }
    return roles


def annotate(races, roles):
    for race in races:
        info = roles.get(f"{race[0]['meeting']}|{race[0]['race']}") or {}
        for r in race:
            num = int(r["horse_number"])
            r["_fastlead"] = bool(info.get("fast")) and num in info.get("leaders", set())
            r["_fastclose"] = bool(info.get("fast")) and num in info.get("closers", set())
    return races


def scored(races, dl, dc):
    return [[{**r, "_score": as_float(r["ability_score"], 60.0)
              + (dl if r["_fastlead"] else 0.0) - (dc if r["_fastclose"] else 0.0)}
             for r in race] for race in races]


def main() -> int:
    races = annotate(group_races(materialize_dataset()), load_roles())
    folds = date_folds(races)
    all_base, all_cand, non_worse = [], [], 0
    for idx, (train, valid) in enumerate(folds, 1):
        best, best_key = (0.0, 0.0), -1.0
        for dl in DELTAS:
            for dc in DELTAS:
                m = metrics_for_races(scored(train, dl, dc))
                key = (m["good_positional"] + m["good"]) / max(1, m["races"])
                if key > best_key:
                    best_key, best = key, (dl, dc)
        dl, dc = best
        vb = metrics_for_races(scored(valid, 0.0, 0.0))
        vc = metrics_for_races(scored(valid, dl, dc))
        non_worse += vc["top3_precision"] >= vb["top3_precision"]
        print(f"fold {idx}: δL={dl} δC={dc} | gp {vb['good_positional']}→{vc['good_positional']} "
              f"g2 {vb['good']}→{vc['good']} miss {vb['miss']}→{vc['miss']}")
        all_base.extend(scored(valid, 0.0, 0.0))
        all_cand.extend(scored(valid, dl, dc))

    base = metrics_for_races(all_base)
    cand = metrics_for_races(all_cand)

    def fmt(m):
        return (f"{m['races']}R {m['gold']}G/{m['good']}g2/{m['good_positional']}gp/{m['miss']}M "
                f"Top3 {m['top3_precision']*100:.1f}% WinT3 {m['winner_in_top3']*100:.1f}% Top1 {m['top1_win']*100:.1f}%")

    print(f"baseline : {fmt(base)}")
    print(f"candidate: {fmt(cand)}")
    gp = (cand["good_positional"] - base["good_positional"]) / base["races"] * 100
    g2 = (cand["good"] - base["good"]) / base["races"] * 100
    print(f"lift: gp {gp:+.2f}pp g2 {g2:+.2f}pp miss Δ {cand['miss']-base['miss']:+d} folds {non_worse}/{len(folds)}")
    passed = (max(gp, g2) >= 1.5 and min(gp, g2) >= -0.5 and cand["miss"] <= base["miss"] and non_worse >= 4
              and (base["top1_win"] - cand["top1_win"]) * 100 <= 0.5
              and (base["winner_in_top3"] - cand["winner_in_top3"]) * 100 <= 0.5
              and (base["gold"] - cand["gold"]) / base["races"] * 100 <= 0.5)
    print("DECISION:", "PASS" if passed else "FAIL / HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
