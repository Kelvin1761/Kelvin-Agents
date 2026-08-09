#!/usr/bin/env python3
"""Round-6b: rebuild the draw modifier — relative barrier × distance × style.

Audit findings (post-adoption archive + 8.6k results rows):
- relative barrier (not absolute) carries the signal: inner 30.3% top3 vs
  outer 26.5% global;
- style interaction is decisive: on-speed horses are draw-immune
  (32.7/32.4/31.9% across bands) while mid-pack suffer −5.4pp and closers
  −3.8pp from wide gates. The current venue-cell modifier hits everyone
  equally — misallocated.

Candidate modifier = table(rel-barrier band × distance band) × style-mult,
where the table is estimated per fold from results rows dated BEFORE the
valid window (leak-free), shrunk n/(n+100), and converted to score points by
a scale s selected per fold on train. Style multipliers: on-speed m_on and
closer m_cl selected per fold from small grids; mid = 1.0.

Baseline = stored production ability (pre-shrinkage modifiers). Candidate =
ability − w·old_modifier + w·new_modifier (w = race_shape weight).
Standard gate.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "/Users/imac/Antigravity-repo/scratch")
import au_draw_bias_fix_test as fix  # reuses current_modifier reproduction

SCRIPTS = Path("/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))
sys.path.insert(0, "/Users/imac/Antigravity-repo")

from wongchoi_paths import AU_RACING  # noqa: E402
from au_cached_walkforward_ml import (  # noqa: E402
    as_float,
    date_folds,
    group_races,
    materialize_dataset,
    metrics_for_races,
)

SANDBOX = fix.SANDBOX
RACE_SHAPE_W = fix.RACE_SHAPE_W

BANDS = ("inner", "mid", "wide")
DIST_BANDS = ("sprint", "middle", "staying")
SCALES = (0.3, 0.6, 1.0)
ON_MULTS = (0.0, 0.5)
CL_MULTS = (0.5, 1.0)
SHRINK_N = 100.0


def rel_band(barrier: float, field: int) -> str:
    pct = (barrier - 1) / max(1, field - 1)
    return "inner" if pct <= 0.33 else ("mid" if pct <= 0.66 else "wide")


def dist_band(distance: str) -> str:
    try:
        d = int(distance)
    except (TypeError, ValueError):
        return "middle"
    return "sprint" if d < 1300 else ("middle" if d < 1800 else "staying")


def load_results_rows() -> list[dict]:
    rows = []
    for name in ("AU_Historical_Raw_Race_Results.csv", "AU_Backfill_Race_Results.csv"):
        p = AU_RACING / name
        if p.exists():
            with p.open(encoding="utf-8-sig") as handle:
                rows.extend(csv.DictReader(handle))
    races = defaultdict(list)
    for r in rows:
        races[(r["Date"], r["Track"], r["Race"])].append(r)
    out = []
    for (date, _track, _race), rs in races.items():
        field = len(rs)
        if field < 6:
            continue
        for r in rs:
            try:
                barrier = int(re.sub(r"[^0-9]", "", r.get("Barrier") or ""))
                pos = int(r["Pos"])
            except (ValueError, TypeError):
                continue
            if barrier < 1 or barrier > field + 4:
                continue
            out.append({"date": date, "band": rel_band(barrier, field),
                        "dist": dist_band(re.sub(r"[^0-9]", "", r.get("Distance") or "")),
                        "top3": pos <= 3})
    return out


def build_table(results_rows: list[dict], before_date: str) -> dict:
    """(dist_band, band) -> shrunk top3-rate delta vs that dist_band's mean, in pp."""
    counts = defaultdict(lambda: [0, 0])
    for r in results_rows:
        if r["date"] >= before_date:
            continue
        s = counts[(r["dist"], r["band"])]
        s[0] += 1
        s[1] += r["top3"]
    table = {}
    for db in DIST_BANDS:
        total_n = sum(counts[(db, b)][0] for b in BANDS)
        total_h = sum(counts[(db, b)][1] for b in BANDS)
        if total_n == 0:
            continue
        mean = total_h / total_n
        for b in BANDS:
            n, h = counts[(db, b)]
            if n == 0:
                continue
            delta_pp = (h / n - mean) * 100
            table[(db, b)] = delta_pp * (n / (n + SHRINK_N))
    return table


def load_horse_ctx() -> dict:
    ctx = {}
    for d in sorted(p for p in SANDBOX.iterdir() if p.is_dir()):
        for lp in d.glob("Race_*_Logic.json"):
            try:
                data = json.loads(lp.read_text(encoding="utf-8"))
            except Exception:
                continue
            ra = data.get("race_analysis") or {}
            sm = ra.get("speed_map") or {}
            race_no = str(ra.get("race_number") or lp.stem.split("_")[1])
            distance = re.sub(r"[^0-9]", "", str(ra.get("distance") or ""))
            role_of = {}
            for role in ("leaders", "pressers", "on_pace", "mid_pack", "closers"):
                for x in (sm.get(role) or []):
                    if str(x).isdigit():
                        role_of[int(x)] = role
            for num, h in (data.get("horses") or {}).items():
                try:
                    barrier = float(h.get("barrier"))
                except (TypeError, ValueError):
                    barrier = None
                style = {"leaders": "on", "pressers": "on", "on_pace": "on",
                         "closers": "cl"}.get(role_of.get(int(num) if str(num).isdigit() else -1), "mid")
                ctx[f"{d.name}|{race_no}|{num}"] = {"barrier": barrier, "distance": distance, "style": style}
    return ctx


def main() -> int:
    results_rows = load_results_rows()
    ctx = load_horse_ctx()
    races = group_races(materialize_dataset())
    folds = date_folds(races)

    def scored(subset, table, scale, m_on, m_cl, candidate: bool):
        out = []
        for race in subset:
            field = len(race)
            track = str(race[0].get("track") or "")
            rows = []
            for r in race:
                key = f"{r['meeting']}|{r['race']}|{int(r['horse_number'])}"
                info = ctx.get(key)
                delta = 0.0
                if candidate and info and info["barrier"] is not None:
                    old = fix.current_modifier(track, info["distance"], fix.bucket_of(info["barrier"]),
                                               field, info["barrier"])
                    band = rel_band(info["barrier"], field)
                    base_pp = table.get((dist_band(info["distance"]), band), 0.0)
                    mult = {"on": m_on, "cl": m_cl}.get(info["style"], 1.0)
                    new = max(-4.05, min(4.05, base_pp * scale * mult))
                    delta = new - old
                rows.append({**r, "_score": as_float(r["ability_score"], 60.0) + RACE_SHAPE_W * delta})
            out.append(rows)
        return out

    all_base, all_cand, non_worse = [], [], 0
    for idx, (train, valid) in enumerate(folds, 1):
        valid_start = min(str(r[0]["date"]) for r in valid)
        table = build_table(results_rows, valid_start)
        best, best_key = (0.6, 0.0, 1.0), -1.0
        for scale in SCALES:
            for m_on in ON_MULTS:
                for m_cl in CL_MULTS:
                    m = metrics_for_races(scored(train, table, scale, m_on, m_cl, True))
                    keyv = (m["good_positional"] + m["good"]) / max(1, m["races"])
                    if keyv > best_key:
                        best_key, best = keyv, (scale, m_on, m_cl)
        scale, m_on, m_cl = best
        vb = metrics_for_races(scored(valid, table, scale, m_on, m_cl, False))
        vc = metrics_for_races(scored(valid, table, scale, m_on, m_cl, True))
        non_worse += vc["top3_precision"] >= vb["top3_precision"]
        print(f"fold {idx}: scale={scale} m_on={m_on} m_cl={m_cl} | gp {vb['good_positional']}→{vc['good_positional']} "
              f"g2 {vb['good']}→{vc['good']} miss {vb['miss']}→{vc['miss']}")
        all_base.extend(scored(valid, table, scale, m_on, m_cl, False))
        all_cand.extend(scored(valid, table, scale, m_on, m_cl, True))

    base = metrics_for_races(all_base)
    cand = metrics_for_races(all_cand)
    gp = (cand["good_positional"] - base["good_positional"]) / base["races"] * 100
    g2 = (cand["good"] - base["good"]) / base["races"] * 100
    print(f"baseline : gp {base['good_positional']} g2 {base['good']} miss {base['miss']} "
          f"top1 {base['top1_win']*100:.1f}% wT3 {base['winner_in_top3']*100:.1f}%")
    print(f"candidate: gp {cand['good_positional']} g2 {cand['good']} miss {cand['miss']} "
          f"top1 {cand['top1_win']*100:.1f}% wT3 {cand['winner_in_top3']*100:.1f}%")
    print(f"lift: gp {gp:+.2f}pp g2 {g2:+.2f}pp gold {cand['gold']-base['gold']:+d} miss Δ {cand['miss']-base['miss']:+d} "
          f"folds {non_worse}/{len(folds)}")
    passed = (max(gp, g2) >= 1.5 and min(gp, g2) >= -0.5 and cand["miss"] <= base["miss"] and non_worse >= 4
              and (base["top1_win"] - cand["top1_win"]) * 100 <= 0.5
              and (base["winner_in_top3"] - cand["winner_in_top3"]) * 100 <= 0.5
              and (base["gold"] - cand["gold"]) / base["races"] * 100 <= 0.5)
    print("DECISION:", "PASS" if passed else "FAIL / HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
