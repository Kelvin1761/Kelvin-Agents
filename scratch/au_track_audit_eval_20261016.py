#!/usr/bin/env python3
"""EXP-20261016-70：場地與地況適性六項。規格見 protocol —— 唔准喺度改。

    run --dump trk.json --outdir D   → describe.json + 候選 arm（base、T1x、T3x、T4x、T5x、T6x）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
sys.path.insert(0, str(HERE))
import au_jt_audit_eval_20261016 as ev  # noqa: E402
from au_racing_engine.engine_core import clip_score, parse_record_line  # noqa: E402
from au_racing_engine.scoring import TRACK_MICRO_WEIGHTS as W  # noqa: E402

EMPTY = {"starts": 0, "wins": 0, "seconds": 0, "thirds": 0, "places": 0}


def rec(text):
    return parse_record_line(text) or dict(EMPTY)


def going_stats(line):
    return {lab: rec(m.group(1).strip()) if (m := re.search(rf"{lab}:\s*([^|]+)", line or "")) else dict(EMPTY)
            for lab in ("好地", "軟地", "重地")}


def is_synth_today(t):
    return "synthetic" in f"{t['today_venue']} {t['today_going']}".lower()


def track_score(t, base=None, t1=False, t3=False, t4=False, t6=False, trace=None):
    score = W["base"] if base is None else base
    ts = rec(str(t["track_stats_line"] or "").split("|", 1)[0].strip())
    gs = going_stats(t["going_stats_line"])
    bucket = t["going_bucket"]
    sample = gs.get(bucket, dict(EMPTY))
    if t6 and is_synth_today(t) and t.get("synth"):
        s, w1, w2, w3 = t["synth"]
        sample, bucket = {"starts": s, "wins": w1, "places": w1 + w2 + w3}, "合成"
    if ts["places"] > 0:
        score += min(9, ts["places"] * W["same_track_place_bonus"] + ts["wins"] * W["same_track_win_bonus"])
    elif ts["starts"] >= 2:
        score += W["same_track_poor_pen2"] if t1 else W["same_track_poor_pen1"]
    elif ts["starts"] > 0:
        score += W["same_track_poor_pen2"]
    wet = bucket in {"軟地", "重地"}
    poor_applied = False
    if sample.get("starts", 0) > 0 and sample.get("places", 0) > 0:
        score += min(10, sample["places"] * W["going_place_bonus"])
        if trace is not None: trace["going_block"] = "place"
        if sample.get("wins", 0) > 0 and wet:
            score += W["going_win_bonus"]
    elif sample.get("starts", 0) >= 2:
        score += W["going_poor_pen1_wet"] if wet else W["going_poor_pen1_dry"]; poor_applied = True
        if trace is not None: trace["going_block"] = "poor"
    elif sample.get("starts", 0) > 0:
        score += W["going_poor_pen2_wet"] if wet else W["going_poor_pen2_dry"]; poor_applied = True
        if trace is not None: trace["going_block"] = "poor"
    if t["wet_state"] in {"soft7plus", "heavy"}:
        verified = gs["軟地"]["places"] > 0 or gs["重地"]["places"] > 0
        if not verified:
            if not (t3 and poor_applied):
                score += W["wet_unverified_pen"]
        elif t["wet_state"] == "heavy" and not t4:
            h = gs["重地"]
            if h["wins"] > 0:
                score += W["heavy_win_bonus"]
            elif h["places"] > 0:
                score += W["heavy_place_bonus"]
            elif h["starts"] >= 2:
                score += W["heavy_poor_pen"]
    return clip_score(score)


def rows_of(race, **kw):
    from au_racing_engine.scoring import MATRIX_WEIGHTS
    from au_walkforward_refit import exact_score
    out = []
    for x in race["rows"]:
        feats = {**x["features"], "track_score": round(track_score(x["trk"], **kw), 6)}
        r = {k: x[k] for k in ("n", "name", "pos", "sp", "wet", "proven_class", "full_time")}
        r["features"] = feats
        r["ability"] = exact_score(r, MATRIX_WEIGHTS)
        out.append(r)
    return out


def cell_add(cells, key, x, n):
    cells[key][0] += 1; cells[key][1] += ev.excess(x, n)


def fmt(cells):
    return {k: {"n": v[0], "excess": round(v[1] / v[0], 4)} for k, v in sorted(cells.items()) if v[0]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True); ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    out = Path(args.outdir); out.mkdir(parents=True, exist_ok=True)
    dump = json.loads(Path(args.dump).read_text(encoding="utf-8"))
    clean = [r for r in dump["races"] if r["date"] >= ev.CUT and sum(x["pos"] <= 3 for x in r["rows"]) >= 3
             and any(x["pos"] == 1 for x in r["rows"])]
    tg = ag = 0.0
    for r in clean:
        for x, y in zip(r["rows"], rows_of(r)):
            tg = max(tg, abs(y["features"]["track_score"] - x["features"]["track_score"]))
            ag = max(ag, abs(y["ability"] - x["ability"]))
    print("replica gaps track", tg, "ability", ag)
    if tg > 1e-3 or ag > 1e-3:
        raise SystemExit("replica does not reproduce the engine — stop")
    desc = {"races": len(clean), "replica_gaps": {"track": tg, "ability": ag}}
    t1, t2, t3 = defaultdict(lambda: [0, 0.0]), defaultdict(lambda: [0, 0.0]), defaultdict(lambda: [0, 0.0])
    good_block = defaultdict(int); synth_races = 0; synth_have = [0, 0]
    for r in clean:
        n = len(r["rows"])
        if any(is_synth_today(x["trk"]) for x in r["rows"]):
            synth_races += 1
        for x in r["rows"]:
            t = x["trk"]
            ts = rec(str(t["track_stats_line"] or "").split("|", 1)[0].strip())
            if ts["starts"] and not ts["places"]:
                cell_add(t1, f"0 places | {min(ts['starts'], 4)}{'+' if ts['starts'] >= 4 else ''} starts", x, n)
            if ts["places"]:
                band = "1-2" if ts["starts"] <= 2 else "3-5" if ts["starts"] <= 5 else "6+"
                cell_add(t2, f"starts {band} | places {min(ts['places'], 3)}{'+' if ts['places'] >= 3 else ''}", x, n)
            if t["wet_state"] in {"soft7plus", "heavy"}:
                gs = going_stats(t["going_stats_line"])
                wet_starts = gs["軟地"]["starts"] + gs["重地"]["starts"]
                wet_places = gs["軟地"]["places"] + gs["重地"]["places"]
                cell_add(t3, "no wet starts" if not wet_starts else "wet unplaced" if not wet_places else "wet placed", x, n)
            if t["going_bucket"] == "好地":
                tr = {}; track_score(t, trace=tr); good_block[tr.get("going_block", "none")] += 1
            if is_synth_today(t):
                synth_have[0] += 1; synth_have[1] += bool(t.get("synth") and t["synth"][0] > 0)
    desc.update({"T1": fmt(t1), "T2": fmt(t2), "T3": fmt(t3), "good_going_block": dict(good_block),
                 "T6": {"synthetic_races": synth_races, "runners": synth_have[0], "with_synth_record": synth_have[1]}})
    (out / "describe.json").write_text(json.dumps(desc, ensure_ascii=False, indent=1))
    print(json.dumps(desc, ensure_ascii=False, indent=1))
    arms = {"base": {}, "T1x": {"t1": True}, "T3x": {"t3": True}, "T4x": {"t4": True}, "T5x": {"base": 60.0}}
    if synth_races >= 100:
        arms["T6x"] = {"t6": True}
    for name, kw in arms.items():
        races = [{**{k: v for k, v in r.items() if k != "rows"}, "rows": rows_of(r, **kw)} for r in dump["races"]]
        (out / f"{name}.json").write_text(json.dumps({"races": races}))
        print("built", name, flush=True)


if __name__ == "__main__":
    main()
